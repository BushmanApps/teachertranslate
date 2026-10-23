"""Entity service layer — pure business logic, no FastAPI types.

Validates request bodies through the dynamic entity body-model
(`registry.body_model(name)`) and serializes outbound docs via the
dynamic response-model (`registry.response_model(name)`). Two model
variants per entity, both built at lifespan startup; see
`app.core.schema.registry`.

The User entity has special-case write logic (`data.<key>` Mongo routing,
phantom create, immutable field filtering, role-permission checks). The
body model is only used for non-User entities in this phase; User updates
still flow through `filter_user_update_fields` to preserve the existing
Mongo storage shape. PROBE_GAP: full Pydantic-coerced User-PUT validation
deferred — entities.md observed behavior (e.g. `lucky_number: "11"`
remains string) suggests Base44 also skips coercion on User custom fields.
"""

from __future__ import annotations

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import PydanticUndefined
from pymongo.errors import OperationFailure

from app.config import Settings
from app.core import db
from app.core.automations import dispatch as dispatch_automation
from app.core.errors import AppError, AppHTTPException, WrappedValidationError
from app.core.models import entities as entity_models
from app.core.models import users as users_models
from app.core.realtime import emit_entity_event
from app.core.responses import doc_to_entity_input, stamp_on_create, utcnow_naive
from app.core.schema import registry
from app.core.security import fls, rls
from app.core.security.pipeline import AuthedContext
from app.modules.auth.helpers import user_doc_to_userresource_input
from app.modules.entities import fields as field_kinds, helpers, reading
from app.modules.entities.helpers import (
    ALLOWED_UPDATE_OPERATORS,
    BULK_UPDATE_MAX,
    UPDATE_MANY_BATCH,
    RefusedQuery,
    apply_user_put_reorder,
    build_mongo_query,
    build_phantom_user,
    can_update_user_role,
    created_by_hidden,
    is_collaborator,
    raise_user_not_found,
    require_user_auth,
    resolve_schema,
    serialize_for_rls,
    validate_user_create_fields,
    validate_user_query,
)


def _validated_body(entity_name: str, body: dict, *, partial: bool, schema: dict) -> dict:
    """Validate a request body against the entity's body-model and return
    a dict of schema-only keys, ready to be passed to Mongo.

    Field-size check (F-020) runs BEFORE Pydantic validation so the
    same 20,000-char rejection applies to declared, orphan, nested-dict,
    and array-element string values — Base44 enforces on all of them.

    - `partial=False` (CREATE): uses the full body model — required fields
      enforced, defaults applied from schema. Output includes only:
      user-provided fields + fields with an explicit schema-level `default`.
      Optional fields with no explicit default are OMITTED if the user
      didn't provide them. Same-decisions: Base44 stores only what's
      either user-provided or carries an explicit schema default — probed
      2026-05-22 (M-013): POST `{"title":"x"}` on a schema with
      `secret_note: {"type":"string"}` (no default) produces a Mongo doc
      WITHOUT `secret_note`; ours was storing `secret_note: None` because
      the body model's `Optional[X] = None` dump always emitted it.
    - `partial=True` (UPDATE/PUT): uses the partial body model — every
      field is Optional[X] with default None, so the client may omit any
      field (including schema-required ones) and Pydantic still validates
      types on whichever keys ARE present. `exclude_unset=True` returns
      only user-provided keys. Base44 production probed 2026-05-22:
      partial PUT with missing required field returns 200 and merges the
      delta. Same-decisions: two models per entity, the canonical
      Pydantic pattern for partial-update endpoints (F-008).
    """
    helpers.assert_field_sizes_ok(body)
    body_cls = (
        registry.body_model_partial(entity_name)
        if partial
        else registry.body_model(entity_name)
    )
    if body_cls is None:
        raise AppError(404, f"Entity schema {entity_name} not found in app")
    try:
        instance = body_cls(**body)
    except ValidationError as exc:
        raise WrappedValidationError(exc.errors())
    schema_props = schema.get("properties") or {}
    schema_keys = set(schema_props.keys())
    if partial:
        dumped = instance.model_dump(exclude_unset=True)
        return {k: v for k, v in dumped.items() if k in schema_keys}

    # CREATE: store ONLY the fields the client actually provided (coerced).
    # Base44's create stores `exclude_unset` and FILLS schema defaults on
    # READ (not at write). Proven 2026-05-24 on the published ParityGym
    # fixture (F-048): a provided `count:50` round-trips as float `50.0`
    # (validated through the model), while an UNSET `count` (schema default
    # 0) reads back as raw int `0` — the raw-default-vs-coerced-provided
    # asymmetry only exists if defaults are filled on read, not stored. So
    # we persist only provided values; `serialize_for_rest` emits every
    # declared field by filling defaults from the response model
    # (`exclude_unset=False`, `validate_default=False`).
    dumped = instance.model_dump(exclude_unset=True)
    return {k: v for k, v in dumped.items() if k in schema_keys}


_SOCKET_STAMPS = ["app_delete_op_id", "environment"]


def _build_response_input(
    entity_name: str,
    doc: dict,
    *,
    hide_created_by: bool,
    socket_stamps: bool,
) -> tuple[type[BaseModel], dict]:
    """Construct the input dict for the entity response model in Base44's
    canonical wire field order.

    Order produced:
      1. Schema fields (in `properties` declaration order)
      2. Extras — any non-stamp, non-schema fields on the doc, in storage
         insertion order. Surfaces $set-injected unknown fields between
         schema and stamps to match Base44 wire (probed 2026-05-21).
      3. Stamps in `ENTITY_STAMP_ORDER` (id, created_date, updated_date,
         created_by_id, created_by, is_sample), then `app_delete_op_id` and
         `environment` when `socket_stamps=True` — the two keys a Socket.IO
         event carries and REST strips (both null on a live row; measured
         2026-09-28).

    The response model declares only schema fields; stamps + extras enter
    via `extra="allow"` and Pydantic v2 emits declared first in declaration
    order then extras in input-insertion order — producing this exact wire
    layout by construction.
    """
    response_cls = registry.response_model(entity_name)
    if response_cls is None:
        raise AppError(404, f"Entity schema {entity_name} not found in app")

    schema = registry.get(entity_name) or {}
    schema_keys = list((schema.get("properties") or {}).keys())
    stamps_in_order = list(entity_models.ENTITY_STAMP_ORDER)
    if hide_created_by:
        stamps_in_order = [k for k in stamps_in_order if k != "created_by"]
    if socket_stamps:
        stamps_in_order += _SOCKET_STAMPS

    skip = set(schema_keys) | set(entity_models.ENTITY_STAMP_ORDER) | set(_SOCKET_STAMPS)
    doc_in = doc_to_entity_input(doc)

    ordered: dict = {}
    for key in schema_keys:
        if key in doc_in:
            ordered[key] = doc_in[key]
    for key, value in doc_in.items():
        if key in skip:
            continue
        ordered[key] = value
    for key in stamps_in_order:
        if key in doc_in:
            ordered[key] = doc_in[key]
        elif key in _SOCKET_STAMPS:
            ordered[key] = None

    return response_cls, ordered


def _dump_stored(response_cls: type[BaseModel], ordered: dict, *, mode: str) -> dict:
    """Serialize a STORED record the way Base44 reads it: values as stored,
    never re-validated against the CURRENT schema.

    Base44 coerces at WRITE time (a `number` field created with `5` is stored
    and read back as `5.0`) and reads back whatever is stored — measured
    2026-09-15 on a fixture whose schema changed under existing rows
    (`eb44 read-parity probe 0915`): after `cat` became an array, `num` a
    string, `flag` a boolean, `obj` an object and `txt` a number, the list
    answered 200 with `"cat":"ACT","num":5.0,"flag":"yes","obj":"plain",
    "txt":"hello"` — every stored value verbatim, no coercion, no error.
    Validating here instead 500'd an entire 131-row entity for one customer
    (AthleCore: 129 rows with `category` as a string predating the schema's
    change to a list).

    `model_construct` skips validation and keeps `fields_set` = the provided
    keys, so `exclude_unset=True` + `_fill_declared_defaults` produce the same
    wire as before for rows that DO match the schema (F-048's raw-default-vs-
    stored-coerced asymmetry is a write-time fact, not a read-time one).
    `warnings=False`: a stored value of another type would otherwise emit a
    serialization warning per row.
    """
    dumped = response_cls.model_construct(**ordered).model_dump(
        mode=mode, exclude_unset=True, warnings=False,
    )
    return _fill_declared_defaults(response_cls, dumped)


def _fill_declared_defaults(response_cls: type[BaseModel], dumped: dict) -> dict:
    """Fill declared schema fields absent from `dumped` with their RAW default.

    Base44's entity read emits EVERY declared field, but with a raw-default-
    vs-coerced-provided asymmetry (proven 2026-05-24 on published ParityGym,
    F-048):

      - a field the client PROVIDED was coerced at WRITE time (number
        `50`→`50.0`) and is emitted as stored; it's present in the
        `exclude_unset=True` dump already.
      - a field the client did NOT provide is emitted as its RAW schema
        default — `count` (default 0) → int `0` (NOT `0.0`), `status` →
        `"draft"`, an array field → `[]`, an optional-no-default field →
        `null`. The default never passes through the field's serializer, so
        a `number` default stays int.

    Replicating this with a single `model_dump` is impossible: `exclude_unset=
    False` would run the float serializer on the default (→`0.0`), and
    `mode="python"` would break the datetime `Z`/naive wire format. So we dump
    `exclude_unset=True` (provided fields coerced, datetimes correct) and fill
    the absent declared fields here from the model's own field defaults
    (`get_default` returns the raw default / `default_factory()` `[]` / `None`),
    inserting them in canonical field order BEFORE the extras + stamps that
    follow.
    """
    declared = response_cls.model_fields
    out: dict = {}
    for fname, finfo in declared.items():
        if fname in dumped:
            out[fname] = dumped[fname]
        else:
            default = finfo.get_default(call_default_factory=True)
            out[fname] = None if default is PydanticUndefined else default
    for key, value in dumped.items():
        if key not in declared:
            out[key] = value
    return out


def _serialize_user(doc: dict, *, mode: str) -> dict:
    """Serialize a `User` doc via `UserResource`, NOT the generic entity model.

    User customs are documentation-only on Base44 (F-050): the generic entity
    `"User"` response model (built from the `_entity_schemas` User doc) enforces
    schema-`required` customs — so serializing a stored User that lacks one
    (e.g. an existing user without ParityGym's required `department`/`bio`) threw
    `ValidationError` → 500 — and post-F-048 would FILL customs with defaults,
    whereas Base44 OMITS unset User customs. `UserResource` (built from
    `additional_user_data_schema`, customs typed `Optional[Any]`, none required)
    is the proven `/me` serializer; routing all User serialization through it
    fixes both. `mode` follows the caller: `"json"` (REST — `Z` datetimes) or
    `"python"` (automation — orjson isoformat).
    """
    return users_models.UserResource(**user_doc_to_userresource_input(doc)).model_dump(
        mode=mode, by_alias=True, exclude_unset=True,
    )


def serialize_for_rest(entity_name: str, doc: dict, *, hide_created_by: bool = False) -> dict:
    """Build the REST wire shape for an entity record.

    Wire field order (probed against Base44 2026-05-21 on data-core-lab —
    OrderProbeA / Note / update-many-injected extras):

      schema fields → orphan extras → id, created_date, updated_date,
      created_by_id, created_by, is_sample

    `environment` is stripped (Base44 never emits it on REST).

    Datetime serialization is Pydantic v2 `mode="json"` — the same-decisions
    serializer Base44 uses. Emits `Z` for tz-aware UTC values (fresh
    `created_date`/`updated_date` on POST/create) and naive isoformat for
    naive values (Mongo BSON Date round-trip on GET/LIST, `utcnow_naive()`
    on PUT-stamped `updated_date`). FastAPI's `jsonable_encoder` is a no-op
    on the resulting strings, preserving Base44's exact wire format
    end-to-end.
    """
    if entity_name == "User":
        return _serialize_user(doc, mode="json")
    response_cls, ordered = _build_response_input(
        entity_name, doc,
        hide_created_by=hide_created_by,
        socket_stamps=False,
    )
    # mode="json": `Z` for fresh tz-aware stamps, naive isoformat on Mongo
    # round-trip. Stored fields emit as stored (write-time coercion already
    # applied — a provided `count:50` is stored `50.0`), declared fields the
    # doc lacks emit their RAW default (int `0`, F-048).
    return _dump_stored(response_cls, ordered, mode="json")


def serialize_for_automation(entity_name: str, doc: dict, *, hide_created_by: bool = False) -> dict:
    """Build the entity-automation wire shape — `data` / `old_data` bodies.

    Differs from `serialize_for_rest` in datetime handling: keeps datetimes
    as Python objects so the automation dispatcher's orjson default hook
    emits `.isoformat()` — `+00:00` for tz-aware (fresh `created_date` on
    create), naive isoformat for tz-naive (Mongo BSON round-trip on
    update/delete). Verified live 2026-05-21 against Base44 production
    automation invocations — Base44's automation body uses isoformat, not
    the REST `Z`-suffix form.

    `environment` is NOT included (Base44 automation bodies, like REST,
    strip it — only Socket.IO emits keep it).

    Wire field order is the same as REST: schema → extras → stamps.
    """
    if entity_name == "User":
        return _serialize_user(doc, mode="python")
    response_cls, ordered = _build_response_input(
        entity_name, doc,
        hide_created_by=hide_created_by,
        socket_stamps=False,
    )
    # mode="python" so datetimes stay as datetime objects; orjson in the
    # dispatcher invokes its default hook (isoformat) on them. REST goes
    # through mode="json" which emits `Z`; we deliberately diverge here.
    return _dump_stored(response_cls, ordered, mode="python")


def _serialize_for_emit(entity_name: str, doc: dict, *, hide_created_by: bool) -> dict:
    """Build the Socket.IO event payload shape — REST's, plus the socket's two
    stamps (`app_delete_op_id`, `environment` — D-061).

    Uses default `mode="python"` so the resulting dict holds `datetime`
    objects. `realtime._DateTimeEncoder` then calls `o.isoformat()` which
    emits `+00:00` for tz-aware UTC — Base44's realtime offset form
    (per the migrator's `dates.ts` comment: Socket.IO create events use
    `+00:00` even though REST uses `Z`). DO NOT switch to `mode="json"`
    here; that would emit `Z` and diverge from Base44 realtime.

    Field order matches REST (schema → extras → stamps, the socket's last);
    constructed identically via `_build_response_input`.
    """
    # User mutations never broadcast realtime (probed — no events on User
    # rooms), so this is defensive; route through UserResource for consistency.
    if entity_name == "User":
        return _serialize_user(doc, mode="python")
    response_cls, ordered = _build_response_input(
        entity_name, doc,
        hide_created_by=hide_created_by,
        socket_stamps=True,
    )
    return _dump_stored(response_cls, ordered, mode="python")


async def _broadcast(app_id: str, entity_name: str, op: str, record: dict) -> None:
    """The realtime event of a write. Each listener is a reader: it gets the
    row only if the entity's read rule lets it, and then as a REST read would
    hand it over — field rules masked, the creator hidden where the app hides
    it. The three decisions are REST's own, asked per listener (the contract:
    core/realtime.py)."""
    rls_row = serialize_for_rls(record)

    def view(ctx: AuthedContext) -> dict | None:
        if not rls.can_read(ctx, entity_name, rls_row):
            return None
        row = _serialize_for_emit(
            entity_name, record, hide_created_by=created_by_hidden(ctx.app_settings),
        )
        return fls.mask_read_fields(ctx, entity_name, [row])[0]

    await emit_entity_event(app_id, entity_name, op, str(record["_id"]), view)


async def create(app_id: str, entity_name: str, body: dict, ctx: AuthedContext, settings: Settings) -> dict:
    schema = resolve_schema(entity_name)

    if entity_name == "User":
        validate_user_create_fields(body)
        return build_phantom_user(body, ctx, settings)

    # The field rules are judged on the record as the caller sent it, before
    # the body's model fills in the defaults.
    fls.validate_write_fields(ctx, entity_name, body, "create")

    record = _validated_body(entity_name, body, partial=False, schema=schema)

    # Stamp BEFORE the RLS check: Base44 evaluates a create rule against the
    # record as it will be stored, so `created_by_id`/`created_by` conditions —
    # by far the most common shape its builder emits — must already be on the
    # record. Measured 2026-08-01: `created_by_id == {{user.id}}` allows,
    # `created_by_id == <other>` denies, so the fields are genuinely evaluated,
    # not skipped. Checking first made every such rule deny unconditionally.
    stamp_on_create(record, ctx)
    rls.assert_can_create(ctx, entity_name, serialize_for_rls(record))

    await db.coll(entity_name).insert_one(record)

    await _broadcast(app_id, entity_name, "create", record)

    await dispatch_automation(
        entity_name, "create", serialize_for_automation(entity_name, record), ctx,
    )

    return record


def assert_may_read_users(ctx: AuthedContext, operation: str) -> None:
    """Who may read the app's users as a set — their list, their count: a
    signed-in collaborator (the owner, an invited collaborator) or the
    service role. D-058; the count follows the list (measured 2026-09-29)."""
    require_user_auth(ctx, f"{operation} users")
    if not is_collaborator(ctx):
        raise AppError(
            403,
            f"Permission denied for {operation} operation on User entity",
            detail="Only collaborators can view the list of users",
        )


async def list_(
    app_id: str,
    entity_name: str,
    query: dict,
    sort_spec: tuple[str, int] | None,
    limit: int,
    skip: int,
    ctx: AuthedContext,
) -> list[dict]:
    resolve_schema(entity_name)

    if entity_name == "User":
        assert_may_read_users(ctx, "list")

    validate_user_query(query)

    rls_filter = rls.filter_for_read(ctx, entity_name)
    mongo_query = build_mongo_query(query, rls_filter)

    # Base44 reads via MongoDB aggregation pipelines (probed F-019,
    # 2026-05-22): `sort=$natural` returns envelope #5 with
    # `error_type='OperationFailure'` carrying MongoDB's full error dict
    # — that's the aggregation `$sort` stage rejecting `$`-prefixed
    # field paths, which the lower-level `cursor.sort()` API silently
    # accepts. Same-decisions: switch the read path to aggregation so
    # invalid sort paths surface the OperationFailure naturally. Any
    # OperationFailure bubbles to the catchall handler which produces
    # the correct envelope #5 shape.
    #
    # Default sort (no `sort` param): ⚠️ BASE44 APPLIES NO SORT AT ALL, and
    # exact parity here is NOT ACHIEVABLE. Measured 2026-08-02 across three
    # apps; the evidence, because both previous readings of this line were
    # wrong and the next agent should not re-litigate it from scratch:
    #
    #   * On a purpose-built 120-row fixture and on MapTrack's 97 untouched
    #     production rows, the unsorted response is reproduced id-for-id by
    #     `sort=-created_date`. That looks conclusive, and it is a trap.
    #   * On a real customer app, the same comparison holds for 5 entities,
    #     is ASCENDING for one, and matches NEITHER direction for two more —
    #     including a 17-row entity with 17 DISTINCT timestamps returned in
    #     scrambled timestamp order. So it is not a created_date sort.
    #   * RLS filtering does not correlate with which entities behave which
    #     way, so it is not a filtered-vs-unfiltered query-plan split either.
    #
    # What fits every observation is MongoDB's NATURAL (physical) order: the
    # fixture's 3 timestamp groups are its 3 insert batches, returned in
    # reverse batch order but ascending within each batch. Natural order is a
    # property of how the rows were physically written, so a migrated
    # database — inserted by our migrator in its own order — cannot reproduce
    # it by any sort we could apply here.
    #
    # We therefore choose a STABLE, DETERMINISTIC default rather than chasing
    # an unreproducible one. `_id: 1` is that choice, kept as-is.
    # ⚠️ It is a CHOICE, not a measured parity fact — F-035 / commit 3107cd4
    # installed it citing a probe whose 5 rows shared a `created_date`, which
    # could not distinguish ascending from descending and proved nothing.
    # The honest summary: an unsorted list in a migrated app will not match
    # Base44's row order, and no available fix makes it match.
    # Full record: research/divergence-chasing/2026-08-02-entity-write-surface.
    sort_field, sort_dir = sort_spec if sort_spec else ("_id", 1)
    pipeline: list[dict] = [
        {"$match": mongo_query},
        {"$sort": {sort_field: sort_dir}},
    ]
    if skip:
        pipeline.append({"$skip": skip})
    pipeline.append({"$limit": limit})

    try:
        return await db.coll(entity_name).aggregate(pipeline).to_list(length=limit)
    except OperationFailure as failure:
        raise reading.refused_by_database(failure) from None


async def get(app_id: str, entity_name: str, id: str, ctx: AuthedContext) -> dict:
    resolve_schema(entity_name)

    if entity_name == "User":
        require_user_auth(ctx, "view users")
        # F-047: viewing ANOTHER user requires collaborator/owner. Self is always
        # allowed. Probed live against B44: non-collaborator GET other → 403
        # BEFORE existence (fake id also 403); GET self → 200.
        caller_id = (ctx.user or {}).get("id")
        if caller_id != id and not is_collaborator(ctx):
            raise AppError(
                403,
                "Permission denied for view operation on User entity",
                detail="only collaborators can view other users",
            )
        return await _get_user(id)

    return await _get_normal(entity_name, id, ctx)


async def _get_normal(entity_name: str, id: str, ctx: AuthedContext) -> dict:
    try:
        oid = ObjectId(id)
    except (InvalidId, Exception):
        raise AppError(404, f"Entity {entity_name} with ID {id} not found")

    doc = await db.coll(entity_name).find_one({"_id": oid})
    if not doc:
        raise AppError(404, f"Entity {entity_name} with ID {id} not found")

    rls_filter = rls.filter_for_read(ctx, entity_name)
    if rls_filter:
        mongo_rls = db.prepare_mongo_filter(rls_filter)
        check_doc = await db.coll(entity_name).find_one({"_id": oid, **mongo_rls})
        if not check_doc:
            raise AppError(404, f"Entity {entity_name} with ID {id} not found")

    return doc


async def _get_user(id: str) -> dict:
    try:
        oid = ObjectId(id)
    except (InvalidId, Exception):
        raise_user_not_found()

    doc = await db.coll("User").find_one({"_id": oid})
    if not doc:
        raise_user_not_found()

    return doc


async def update(
    app_id: str,
    entity_name: str,
    id: str,
    body: dict,
    ctx: AuthedContext,
    settings: Settings,
) -> dict:
    schema = resolve_schema(entity_name)

    if entity_name == "User":
        return await _update_user(app_id, id, body, schema, ctx, settings)

    return await _update_normal(app_id, entity_name, id, body, schema, ctx, settings)


async def _update_normal(
    app_id: str,
    entity_name: str,
    id: str,
    body: dict,
    schema: dict,
    ctx: AuthedContext,
    settings: Settings,
) -> dict:
    try:
        oid = ObjectId(id)
    except (InvalidId, Exception):
        raise AppError(404, f"Entity {entity_name} with ID {id} not found")

    existing = await db.coll(entity_name).find_one({"_id": oid})
    if not existing:
        raise AppError(404, f"Entity {entity_name} with ID {id} not found")

    rls.assert_can_update(ctx, entity_name, serialize_for_rls(existing))
    old_data = serialize_for_automation(entity_name, existing)

    fls.validate_write_fields(ctx, entity_name, body, "update", held=serialize_for_rest(entity_name, existing))

    update_data = _validated_body(entity_name, body, partial=True, schema=schema)

    update_data["updated_date"] = utcnow_naive()

    await db.coll(entity_name).update_one({"_id": oid}, {"$set": update_data})

    updated = {**existing, **update_data}

    await _broadcast(app_id, entity_name, "update", updated)

    await dispatch_automation(
        entity_name, "update", serialize_for_automation(entity_name, updated), ctx, old_data=old_data,
    )

    return updated


async def _update_user(
    app_id: str,
    id: str,
    body: dict,
    schema: dict,
    ctx: AuthedContext,
    settings: Settings,
) -> dict:
    helpers.assert_field_sizes_ok(body)

    try:
        oid = ObjectId(id)
    except (InvalidId, Exception):
        raise_user_not_found()

    existing = await db.coll("User").find_one({"_id": oid})
    if not existing:
        raise_user_not_found()

    old_data = serialize_for_automation("User", existing)

    # F-023 — Base44 prod probe 2026-05-22:
    #
    #   pmm9 (non-admin) PUT /entities/User/<a1_id> {orphan: 'x'}
    #     → 403 bare-backend "You are not authorized to update this user"
    #
    # Non-admin users cannot PUT *any* field on another user's record —
    # not just role. Our previous gate only checked `role` differences,
    # which silently allowed non-admin to mutate orphans + custom fields
    # on other users. Same-decisions: gate the entire operation on
    # "caller-is-target OR caller-can-update-users".
    caller_id = (ctx.user or {}).get("id")
    if caller_id != id and not can_update_user_role(ctx):
        raise AppError(403, "You are not authorized to update this user")

    if "role" in body:
        if body["role"] != old_data.get("role") and not can_update_user_role(ctx):
            raise AppHTTPException(403, "Only platform users can update user roles")

    updated = apply_user_put_reorder(existing, body, ctx, schema)

    await db.coll("User").replace_one({"_id": oid}, updated)

    # Base44 prod does NOT emit realtime events for User entity mutations
    # (probed 2026-05-21: PUT /User/me and PUT /User/<id> produced zero
    # events across 6 listened rooms; an OrderProbeA control fired
    # correctly on the same connection). The SDK's only User subscription
    # path is `base44.entities.User.subscribe(cb)` → joins
    # `entities:<appId>:User`, which Base44 simply doesn't broadcast to.

    await dispatch_automation(
        "User", "update", serialize_for_automation("User", updated), ctx, old_data=old_data,
    )

    return updated


async def delete(
    app_id: str,
    entity_name: str,
    id: str,
    ctx: AuthedContext,
    settings: Settings,
) -> dict:
    resolve_schema(entity_name)

    if entity_name == "User":
        return await _delete_user(app_id, id, ctx, settings)

    return await _delete_normal(app_id, entity_name, id, ctx, settings)


async def _delete_normal(
    app_id: str,
    entity_name: str,
    id: str,
    ctx: AuthedContext,
    settings: Settings,
) -> dict:
    try:
        oid = ObjectId(id)
    except (InvalidId, Exception):
        raise AppError(404, f"Entity {entity_name} with ID {id} not found")

    existing = await db.coll(entity_name).find_one({"_id": oid})
    if not existing:
        raise AppError(404, f"Entity {entity_name} with ID {id} not found")

    rls.assert_can_delete(ctx, entity_name, serialize_for_rls(existing))

    await db.coll(entity_name).delete_one({"_id": oid})

    # The delete-event payload mirrors the deleted record but with a freshly
    # stamped `updated_date` (matches D-053: Base44 stamps a new updated_date
    # on the delete event, not the doc's last stored updated_date).
    await _broadcast(app_id, entity_name, "delete", {**existing, "updated_date": utcnow_naive()})

    await dispatch_automation(
        entity_name, "delete", serialize_for_automation(entity_name, existing), ctx,
    )

    return existing


async def _delete_user(
    app_id: str,
    id: str,
    ctx: AuthedContext,
    settings: Settings,
) -> dict:
    require_user_auth(ctx, "delete users")

    try:
        oid = ObjectId(id)
    except (InvalidId, Exception):
        raise AppError(404, f"Entity User with ID {id} not found")

    existing = await db.coll("User").find_one({"_id": oid})
    if not existing:
        raise AppError(404, f"Entity User with ID {id} not found")

    # F-047: deleting ANOTHER user requires collaborator/owner. Probed live
    # against B44: non-collaborator (incl. app-role admin n001) DELETE other →
    # 403 AFTER existence (fake id → 404, real other → 403). Self-delete passes
    # this gate (consistent with get/update self-allowance).
    caller_id = (ctx.user or {}).get("id")
    if caller_id != id and not is_collaborator(ctx):
        raise AppError(
            403,
            "You don't have permission to delete this user. Only admins can delete other users.",
            detail="You don't have permission to delete this user. Only admins can delete other users.",
        )

    # MIGRATOR_NOTE: _app_settings.owner_id must be set (24-char hex string
    # of the owning User's _id) so this guard can identify the app owner.
    app_settings = ctx.app_settings
    owner_id = app_settings.get("owner_id") or app_settings.get("created_by")
    if owner_id and str(existing["_id"]) == str(owner_id):
        raise AppError(
            403,
            "You cannot delete the owner of the app",
            detail="You cannot delete the owner of the app",
        )

    await db.coll("User").delete_one({"_id": oid})

    # Same Base44-prod-parity reasoning as `_update_user` — no realtime
    # broadcast on User mutations.

    await dispatch_automation(
        "User", "delete", serialize_for_automation("User", existing), ctx,
    )

    return existing


async def bulk_create(
    app_id: str,
    entity_name: str,
    items: list,
    ctx: AuthedContext,
    settings: Settings,
) -> list[dict]:
    schema = resolve_schema(entity_name)

    if entity_name == "User":
        return _bulk_create_user_phantom(items, ctx, settings)

    if not items:
        raise AppHTTPException(500, "documents must be a non-empty list", error_type="TypeError")

    records = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            from app.modules.entities.helpers import raise_wrong_body_type
            raise_wrong_body_type("dict", item, loc=("body", i))

        fls.validate_write_fields(ctx, entity_name, item, "create")

        record = _validated_body(entity_name, item, partial=False, schema=schema)

        # Stamp before the check — see create() for why.
        stamp_on_create(record, ctx)
        rls.assert_can_create(ctx, entity_name, serialize_for_rls(record), one_of_many=True)
        records.append(record)

    await db.coll(entity_name).insert_many(records)

    return records


def _within_reach(ctx: AuthedContext, entity_name: str) -> dict:
    """The rows a caller may read AND update, as a filter: where a write that
    LOOKS for its row looks (a bulk update by id, an upsert by key)."""
    rules = [f for f in (rls.filter_for_read(ctx, entity_name), rls.filter_for_update(ctx, entity_name)) if f]
    return db.prepare_mongo_filter({"$and": rules}) if rules else {}


UPSERT_MAX = 500


def _upsert_key(entity_name: str, schema: dict, key: str | list[str]) -> list[str]:
    """The fields an upsert's key names. A key is made of the entity's OWN
    scalar fields: not a stamp of the platform's, not a path into an object."""
    names = list(dict.fromkeys([key] if isinstance(key, str) else key))
    if not names or any(not name or name in field_kinds.STAMPS or "." in name for name in names):
        raise AppError(400, "key must name one or more custom fields of the entity")
    unknown = [name for name in names if field_kinds.kind(schema, name) == field_kinds.UNDECLARED]
    if unknown:
        raise AppError(400, f"Unknown fields for {entity_name}: {unknown}")
    for name in names:
        declared = field_kinds.kind(schema, name)
        if declared not in field_kinds.SCALARS:
            raise AppError(400, f"upsert keys need '{name}', which has no declared scalar type ({declared})")
    return names


def _upsert_key_of(schema: dict, record: dict, names: list[str]) -> tuple:
    """A record's key, each value read as its field's declared type (the
    number 7 and the string "7" are one key on a number field)."""
    values = []
    for name in names:
        try:
            values.append(TypeAdapter(field_kinds.python_type(schema, name)).validate_python(record[name]))
        except ValidationError as err:
            raise AppError(400, f"Key field '{name}': {err.errors()[0]['msg']}") from None
    return tuple(values)


async def upsert(
    app_id: str,
    entity_name: str,
    records: list[dict],
    key: str | list[str],
    ctx: AuthedContext,
) -> tuple[list[dict], list[dict]]:
    """The rows created and the rows updated, each in the order their records
    came. What Base44 does (measured at its apps' host, 2026-09-29):

    - a record whose key matches a row its caller may READ AND UPDATE updates
      that row — the fields it names, the rest kept; any other record creates
      one. A row the caller may not read, or may read and not update, is no
      match: the record creates a second row of that key. Of two stored rows
      of one key the newer is the match;
    - of two records of one key in one call the LAST is written, whole — the
      earlier is not read at all;
    - nothing is written unless every record can be: one record refused — a
      type, a required field, a rule — refuses the call;
    - every row written is told to the app's listeners, as a single create or
      update is; the app's entity TRIGGERS are not fired, as a bulk create's
      are not (probe 10 of the chase: an upsert is heard and sets nothing off).
    """
    schema = resolve_schema(entity_name)
    if entity_name == "User":
        raise AppError(400, "Not available for the User entity; use the app users endpoints")
    if not records:
        raise AppError(400, "records must not be empty")
    if len(records) > UPSERT_MAX:
        raise AppError(400, f"Too many records. Maximum is {UPSERT_MAX}, got {len(records)}")
    names = _upsert_key(entity_name, schema, key)
    for record in records:
        if any(record.get(name) is None or isinstance(record.get(name), (list, dict)) for name in names):
            raise AppError(400, f"Every record needs scalar values for the key fields {names}")

    last: dict[tuple, dict] = {}
    for record in records:
        last[_upsert_key_of(schema, record, names)] = record
    for record in last.values():
        helpers.assert_field_sizes_ok(record)

    created: list[dict] = []
    changes: list[tuple[dict, dict]] = []  # (the row as it is stored, the fields to set)
    for key_values, record in last.items():
        existing = await db.coll(entity_name).find_one(
            {"$and": [dict(zip(names, key_values)), _within_reach(ctx, entity_name)]}, sort=[("_id", -1)],
        )
        if existing is None:
            fls.validate_write_fields(ctx, entity_name, record, "create")
            row = _validated_body(entity_name, record, partial=False, schema=schema)
            stamp_on_create(row, ctx)
            rls.assert_can_create(ctx, entity_name, serialize_for_rls(row), one_of_many=True)
            created.append(row)
        else:
            fls.validate_write_fields(ctx, entity_name, record, "update", held=serialize_for_rest(entity_name, existing))
            fields = _validated_body(entity_name, record, partial=True, schema=schema)
            fields["updated_date"] = utcnow_naive()
            changes.append((existing, fields))

    if created:
        await db.coll(entity_name).insert_many(created)
    for existing, fields in changes:
        await db.coll(entity_name).update_one({"_id": existing["_id"]}, {"$set": fields})
    updated = [{**existing, **fields} for existing, fields in changes]

    for row in created:
        await _broadcast(app_id, entity_name, "create", row)
    for row in updated:
        await _broadcast(app_id, entity_name, "update", row)
    return created, updated


def _bulk_create_user_phantom(items: list, ctx: AuthedContext, settings: Settings) -> list[dict]:
    if not items:
        raise AppHTTPException(500, "documents must be a non-empty list", error_type="TypeError")

    results = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            from app.modules.entities.helpers import raise_wrong_body_type
            raise_wrong_body_type("dict", item, loc=("body", i))
        validate_user_create_fields(item)
        results.append(build_phantom_user(item, ctx, settings))

    return results


async def bulk_update(
    app_id: str,
    entity_name: str,
    items: list,
    ctx: AuthedContext,
    settings: Settings,
) -> list[dict]:
    schema = resolve_schema(entity_name)

    if not items:
        raise AppError(400, "Items list must not be empty")

    if len(items) > BULK_UPDATE_MAX:
        raise AppError(400, f"Too many items. Maximum is {BULK_UPDATE_MAX}, got {len(items)}")

    lookups = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            from app.modules.entities.helpers import raise_wrong_body_type
            raise_wrong_body_type("dict", item, loc=("body", i))

        item_id = item.get("id")
        if not item_id:
            raise AppError(400, "Each item must have an 'id' field")

        try:
            oid = ObjectId(item_id)
        except (InvalidId, Exception):
            raise AppHTTPException(
                500,
                f"'{item_id}' is not a valid ObjectId, it must be a 12-byte input or a 24-character hex string",
                error_type="InvalidId",
            )

        # A row is looked for among the rows the caller may read and update:
        # one they may not is "not found" here (measured 2026-09-29; the
        # update by id of the same row is a 403).
        existing = await db.coll(entity_name).find_one({"$and": [{"_id": oid}, _within_reach(ctx, entity_name)]})
        if not existing:
            raise AppError(404, f"Entity {entity_name} with ID {item_id} not found")
        lookups.append((oid, item, existing))

    # Base44 prod stamps `updated_date` once per bulk batch, not per row
    # (probed 2026-05-21: a 3-row bulkUpdate produced 3 events with
    # identical μs `updated_date` — only achievable by reusing a single
    # `now()` across the loop; sequential Mongo writes would otherwise
    # diverge by hundreds of μs). Same decision here: capture the
    # timestamp once before the row loop.
    batch_updated_date = utcnow_naive()

    updated_rows = []
    for oid, item, existing in lookups:
        update_fields = {k: v for k, v in item.items() if k != "id"}

        fls.validate_write_fields(ctx, entity_name, update_fields, "update", held=serialize_for_rest(entity_name, existing))
        update_data = _validated_body(entity_name, update_fields, partial=True, schema=schema)
        update_data["updated_date"] = batch_updated_date

        await db.coll(entity_name).update_one({"_id": oid}, {"$set": update_data})

        updated = {**existing, **update_data}
        updated_rows.append(updated)

        await _broadcast(app_id, entity_name, "update", updated)

    return updated_rows


async def update_many(
    app_id: str,
    entity_name: str,
    query: dict,
    data: dict,
    ctx: AuthedContext,
) -> dict:
    resolve_schema(entity_name)

    if entity_name == "User":
        raise AppError(405, "Bulk user update not allowed")

    # Probed against Base44: `data: {}` → `400 "Update data must not be empty."`
    # in the bare-backend envelope (envelope #6). Without this check the empty
    # dict would reach Motor and bubble as a 500 ValueError.
    if not data:
        raise AppError(400, "Update data must not be empty.")

    # Probed 2026-05-21 against Base44 (AuthRolesLab):
    #   PATCH update-many {"data": {"status": "done"}}  →  400
    #     {"message": "Unsupported update operator: status", ...}
    # Base44 rejects EAGERLY (before matching docs) when any data key is
    # not a recognized $-operator. Same applies to unknown $-operators.
    # Our previous gate (`op.startswith("$") and op not in ALLOWED`) would
    # let literal field-name keys through; Mongo's update_many would then
    # error only if rows matched, otherwise we'd silently return 200 with
    # updated:0 — a parity divergence.
    for op in data:
        if not op.startswith("$") or op not in ALLOWED_UPDATE_OPERATORS:
            raise AppError(400, f"Unsupported update operator: {op}")

    # F-021: the two writes that take a filter (update-many, delete-many)
    # answer a filter the reader refuses as a plain 400; the reads keep the
    # 500 ValueError shape. Probed 2026-05-22, again 2026-09-29.
    try:
        validate_user_query(query)
    except RefusedQuery as refused:
        raise refused.as_write_refusal() from None

    rls_filter = rls.filter_for_read(ctx, entity_name)
    mongo_query = build_mongo_query(query, rls_filter)

    matching_ids = []
    try:
        cursor = db.coll(entity_name).find(mongo_query, {"_id": 1}).limit(UPDATE_MANY_BATCH + 1)
        async for doc in cursor:
            matching_ids.append(doc["_id"])
    except OperationFailure as failure:
        raise reading.refused_by_database(failure) from None

    has_more = len(matching_ids) > UPDATE_MANY_BATCH
    batch_ids = matching_ids[:UPDATE_MANY_BATCH]

    if not batch_ids:
        return {"success": True, "updated": 0, "has_more": False}

    # Judged once there is a row to write (an update that matches nothing
    # answers `updated: 0` whatever it names).
    fls.validate_update_many(ctx, entity_name, data)

    try:
        result = await db.coll(entity_name).update_many(
            {"_id": {"$in": batch_ids}},
            data,
        )
    except OperationFailure:
        raise AppError(400, "Unsupported update operator")

    return {
        "success": True,
        "updated": result.modified_count,
        "has_more": has_more,
    }


async def delete_many(app_id: str, entity_name: str, query: dict, ctx: AuthedContext) -> dict:
    resolve_schema(entity_name)

    if entity_name == "User":
        raise AppHTTPException(404, "Cant bulk delete users")

    # F-021: same as update-many.
    try:
        validate_user_query(query)
    except RefusedQuery as refused:
        raise refused.as_write_refusal() from None

    rls_filter = rls.filter_for_read(ctx, entity_name)
    mongo_query = build_mongo_query(query, rls_filter)

    try:
        result = await db.coll(entity_name).delete_many(mongo_query)
    except OperationFailure as failure:
        raise reading.refused_by_database(failure) from None

    return {"success": True, "deleted": result.deleted_count}


async def import_entities(
    app_id: str,
    entity_name: str,
    raw_bytes: bytes,
    ctx: AuthedContext,
    settings: Settings,
) -> dict:
    schema = resolve_schema(entity_name)

    from app.modules.entities.import_entities import (
        _DuckDBEncodingError,
        _DuckDBParseError,
        MAX_PARSE_ATTEMPTS,
        _first_other_field,
        _parse_csv_duckdb,
    )

    try:
        rows = _parse_csv_duckdb(raw_bytes, schema)
    except _DuckDBEncodingError as e:
        raise AppHTTPException(500, str(e), error_type="InvalidInputException")
    except _DuckDBParseError as e:
        return {
            "status": "error",
            "details": f"Failed to extract records after {MAX_PARSE_ATTEMPTS} attempts. Last error: {e}",
            "output": None,
        }

    if entity_name == "User":
        return _import_user_phantom(rows, ctx, settings, _first_other_field)

    records = []
    for row in rows:
        try:
            record = _validated_body(entity_name, row, partial=False, schema=schema)
        except WrappedValidationError:
            # Import path is lenient — coercion failure falls through to the
            # raw row, mirroring the existing best-effort import behavior.
            record = dict(row)

        # Stamp before the check — see create() for why.
        stamp_on_create(record, ctx)
        rls.assert_can_create(ctx, entity_name, serialize_for_rls(record))
        records.append(record)

    if records:
        await db.coll(entity_name).insert_many(records)

    output = [serialize_for_rest(entity_name, r) for r in records]
    return {
        "status": "success",
        "details": f"Successfully imported {len(output)} entities with RLS enforcement",
        "output": output,
    }


def _import_user_phantom(rows: list[dict], ctx: AuthedContext, settings: Settings, _first_other_field) -> dict:
    from app.modules.entities.import_entities import MAX_PARSE_ATTEMPTS

    for row in rows:
        missing = _first_missing_user_field(row)
        if missing is not None:
            return {
                "status": "error",
                "details": (
                    f"Failed to extract records after {MAX_PARSE_ATTEMPTS} attempts. "
                    f"Last error: Binder Error: Referenced column \"{missing}\" not found "
                    f"in FROM clause!\nCandidate bindings: \"{_first_other_field(row, missing)}\""
                ),
                "output": None,
            }

    results = [build_phantom_user(row, ctx, settings) for row in rows]
    output = [serialize_for_rest("User", r) for r in results]
    return {
        "status": "success",
        "details": f"Successfully imported {len(output)} entities with RLS enforcement",
        "output": output,
    }


def _first_missing_user_field(row: dict) -> str | None:
    for field in ("email", "full_name", "role"):
        if field not in row:
            return field
    return None


async def get_me(ctx: AuthedContext) -> dict:
    require_user_auth(ctx, "view users")

    if ctx.token_class == "service_role" and ctx.service_principal:
        sp = ctx.service_principal
        return {
            "role": sp["role"],
            "id": sp["id"],
            "created_date": sp["created_date"],
            "updated_date": sp["updated_date"],
            "email": sp["email"],
            "full_name": sp["full_name"],
            "disabled": sp["disabled"],
            "is_verified": sp["is_verified"],
            "force_password_reset": sp["force_password_reset"],
            "app_id": sp["app_id"],
            "is_service": sp["is_service"],
            "collaborator_role": sp["collaborator_role"],
            "_app_role": sp["_app_role"],
        }

    if not ctx.user:
        raise_user_not_found()

    return dict(ctx.user)


async def update_me(
    app_id: str,
    body: dict,
    ctx: AuthedContext,
    settings: Settings,
) -> dict:
    require_user_auth(ctx, "update your user")

    helpers.assert_field_sizes_ok(body)

    if not ctx.user or not ctx.user.get("id"):
        raise_user_not_found()

    user_id = ctx.user["id"]
    old_data = dict(ctx.user)

    schema = resolve_schema("User")

    if "role" in body:
        if body["role"] != old_data.get("role") and not can_update_user_role(ctx):
            raise AppHTTPException(403, "Only platform users can update user roles")

    oid = ObjectId(user_id)
    existing = await db.coll("User").find_one({"_id": oid})
    if not existing:
        raise_user_not_found()

    updated = apply_user_put_reorder(existing, body, ctx, schema)

    await db.coll("User").replace_one({"_id": oid}, updated)

    # Same Base44-prod-parity reasoning as `_update_user` — no realtime
    # broadcast on User mutations (including PUT `/User/me`).

    await dispatch_automation(
        "User", "update", serialize_for_automation("User", updated), ctx, old_data=old_data,
    )

    return updated
