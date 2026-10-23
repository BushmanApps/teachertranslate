"""Shared helpers for the entities module."""

from __future__ import annotations

import json

from bson import ObjectId
from fastapi import Request
from fastapi.exceptions import RequestValidationError

from app.core import db
from app.core.errors import AppError, AppHTTPException, WrappedValidationError
from app.core.responses import utcnow_naive
from app.core.schema import registry
from app.core.security.pipeline import AuthedContext

HARD_LIMIT_CAP = 5000
BULK_UPDATE_MAX = 500
UPDATE_MANY_BATCH = 500

# F-020: Base44 rejects any string field whose value exceeds 20,000 chars
# (inclusive of 20000, 20001 is the first rejection point — probed
# 2026-05-22 via binary search). The check applies recursively to every
# string value in the body — declared schema fields, orphans, items in
# arrays (path emitted as `field[i]`), and nested dict keys (path emitted
# as `field.subkey`). Error envelope: 400 bare-backend with message
# `"Field '<path>' exceeds the maximum allowed size. Please upload large
# content using the UploadPublicFile integration and store the returned URL
# instead."` (the integration it names was `UploadFile` until Base44 renamed
# it; measured again 2026-09-28/29 on a create and an upsert).
MAX_FIELD_VALUE_LEN = 20_000


def _check_field_size_recursive(value, path: str) -> None:
    """Walk a body subtree and raise on the first string field whose
    value length exceeds MAX_FIELD_VALUE_LEN. Mirrors Base44's exact
    path formatting: dotted for dict keys, bracketed for array indices.
    """
    if isinstance(value, str):
        if len(value) > MAX_FIELD_VALUE_LEN:
            raise AppError(
                400,
                f"Field '{path}' exceeds the maximum allowed size. "
                "Please upload large content using the UploadPublicFile integration "
                "and store the returned URL instead.",
            )
        return
    if isinstance(value, dict):
        for k, v in value.items():
            sub_path = f"{path}.{k}" if path else str(k)
            _check_field_size_recursive(v, sub_path)
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            _check_field_size_recursive(v, f"{path}[{i}]")
        return
    # Other types (int, float, bool, None, bytes) — no size enforcement.


def assert_field_sizes_ok(body: dict) -> None:
    """Top-level entry: walk a CREATE/UPDATE body dict and reject if any
    string value in any (possibly nested) position exceeds the field-size
    limit. Run before Pydantic validation — Pydantic's body model has
    `extra='ignore'` for some shapes, which would silently drop orphans
    we still want to size-check (Base44 enforces on orphans too).
    """
    if not isinstance(body, dict):
        return
    for k, v in body.items():
        _check_field_size_recursive(v, str(k))

# 11-op allowlist per D-082 (was 10; $currentDate added).
ALLOWED_UPDATE_OPERATORS = frozenset({
    "$set", "$inc", "$unset", "$mul", "$min", "$max",
    "$push", "$pull", "$addToSet", "$rename", "$currentDate",
})

# 17-op allowlist — applied to the user-supplied `q=` filter BEFORE RLS
# merge. Disallowed operators emit envelope #5 with the doubled "Invalid
# query: Invalid query" message (Base44 string-format bug — mirror verbatim).
#
# `$nor` is INCLUDED here. The earlier 16-op list (D-083) excluded `$nor`
# under the assumption it was internal-only (used by the RLS deny filter).
# Empirically wrong — probed 2026-05-21 against AuthRolesLab:
#   `q={"$nor":[{"title":"x"}]}` returns 200 with rows on Base44 prod.
# RLS still merges its own internal `$nor` afterward; the user-side `$nor`
# is a separate, allowed filter operator.
# `$all` and `$options` added 2026-08-02 after a paired sweep of 22 operators
# against Base44 prod: it accepts `{"tags": {"$all": [...]}}` (24 rows) and
# `{"title": {"$regex": "X", "$options": "i"}}` (120 rows) where we answered
# 500 `Invalid query: Invalid query`. Both are mainstream — `$all` is the
# "has all these tags" filter, `$options: "i"` is how every case-insensitive
# search box is written — so an app using either was broken against our fork.
# `$all` was confirmed rejected by us nested inside `$and`/`$or`/`$not` too,
# since `validate_user_query` recurses. Every other operator in the sweep
# agreed on both sides (see the write-surface chase, probes/08 + probes/10).
# `$text` and `$search` added 2026-09-29: Base44 lets a `$text` through to the
# database today, where it fails for want of a text index no app can create
# (500 "Query failed" — `reading.refused_by_database`); `$language`,
# `$caseSensitive` and the rest of `$text`'s own keys stay refused.
ALLOWED_QUERY_OPERATORS = frozenset({
    "$eq", "$ne", "$gt", "$gte", "$lt", "$lte",
    "$in", "$nin", "$exists", "$regex", "$options", "$all",
    "$or", "$and", "$nor", "$not",
    "$type", "$size", "$elemMatch",
    "$text", "$search",
})

# What Base44's reader of a filter refuses about a regular expression before
# the database sees it (measured 2026-09-29): an option that is none of these
# four, options that are not a string, a pattern over 1,000 characters.
REGEX_OPTIONS = "imsx"
REGEX_LONGEST = 1000

# PUT /me / PUT /User/<id> body keys that are silently dropped on Base44 PROD —
# probe-verified individually on `auth-lab-core-2aa703c8.base44.app` (auth agent
# wave 2026-05-20). The blocklist exists because User has `extra=allow` for
# `additional_user_data_schema` custom fields + arbitrary keys, so we can't use
# an allowlist (would drop legitimate custom fields like `nickname`).
#
# Splits into:
#   - Identity/access:  `full_name`, `email`, `disabled`, `disabled_reason`,
#                       `is_verified`, `app_id`, `is_service`, `collaborator_role`
#   - Role semantics:   `_app_role` — `role` itself is gated separately by
#                       `can_update_user_role`; `_app_role` rides as a side
#                       effect of legitimate `role` writes in `services._update_user`
#                       (the legitimate-write happens AFTER this filter).
#   - Forced-reset gate: `force_password_reset` (server/admin-set)
#   - Server stamps:    `created_date`, `updated_date`, `created_by`,
#                       `created_by_id`, `is_sample` — handler overwrites
#                       `updated_date` anyway; the rest must not be user-mutable.
#   - Primary key:      `id`, `_id` — defensive; the handler's `update_one`
#                       targets `_id` explicitly so a body key wouldn't shift the
#                       row, but a stray `_id` in `$set` raises in MongoDB —
#                       blocking here keeps the wire response 200 instead of 500.
USER_IMMUTABLE_FIELDS = frozenset({
    "full_name", "email", "disabled", "disabled_reason", "is_verified",
    "app_id", "is_service", "collaborator_role",
    "_app_role",
    "force_password_reset",
    "created_date", "updated_date",
    "created_by", "created_by_id", "is_sample",
    "id", "_id",
})


def resolve_schema(entity_name: str) -> dict:
    schema = registry.get(entity_name)
    if not schema:
        raise AppError(404, f"Entity schema {entity_name} not found in app")
    return schema


def known_entity(entity_name: str) -> None:
    """A route's dependency: an entity the app does not have is answered
    before the request's body is held against the route's model."""
    resolve_schema(entity_name)


def require_user_auth(ctx: AuthedContext, action: str) -> None:
    if ctx.token_class in ("app_user", "preview", "service_role"):
        return
    raise AppError(
        401,
        f"Authentication required to {action}",
        detail="You must be logged in to perform this operation.",
    )


def raise_user_not_found():
    raise AppError(404, "User not found", detail="User not found")


def raise_missing_body():
    raise RequestValidationError([
        {"type": "missing", "loc": ("body",), "msg": "Field required", "input": None}
    ])


def raise_wrong_body_type(expected: str, actual, *, loc: tuple = ("body",)):
    """Raise the Pydantic-style wrong-body-type 422.

    Top-level mismatch (body itself wrong type) uses default `loc=("body",)`;
    per-item mismatch in a bulk op should pass `loc=("body", i)` to match
    Base44's Pydantic-emitted `["body", 0]` shape for non-dict items in a
    list body. Base44 likely uses `body: list[dict]` directly in their route
    signature — Pydantic auto-emits the per-item loc. We keep manual parsing
    for the missing-body case (FastAPI's auto-422 differs from Base44's wire)
    and thread the index through ourselves.
    """
    type_name = "dict_type" if expected == "dict" else "list_type"
    msg = f"Input should be a valid {'dictionary' if expected == 'dict' else 'list'}"
    raise RequestValidationError([
        {"type": type_name, "loc": loc, "msg": msg, "input": actual}
    ])


async def parse_json_body(request: Request):
    body_bytes = await request.body()
    if not body_bytes or body_bytes.strip() == b"":
        return None
    return json.loads(body_bytes)


def parse_sort(sort_str: str | None) -> tuple[str, int] | None:
    """The list's sort column (one column — `reading.sort_of` has refused
    two) as the stored field and a direction."""
    if not sort_str:
        return None
    field, direction = (sort_str[1:], -1) if sort_str.startswith("-") else (sort_str, 1)
    # Base44 sorts on the SERIALIZED field names, where the record identifier
    # is `id` — measured 2026-08-02: `sort=id` orders ascending and `sort=-id`
    # descending there, while our documents store it as Mongo's `_id`, so an
    # app sorting by `id` got an unsorted list from us. Translate.
    # (Their `sort=_id` behaves like a nonexistent field; ours still sorts by
    # it. Left alone deliberately — an app relying on that is relying on
    # undefined behaviour on Base44, and matching their arbitrary tie order
    # for an all-null sort key is not reproducible anyway.)
    if field == "id":
        field = "_id"
    return (field, direction)


class RefusedQuery(AppHTTPException):
    """A filter this backend's own reader refuses, before the database is
    asked. A READ answers it as it is raised — 500, `error_type: ValueError`;
    the two writes that take a filter (deleteMany, updateMany) answer the
    same sentence as a plain 400 (`as_write_refusal`). Measured 2026-09-29 on
    the list, the pages, the count and both writes."""

    def __init__(self, reason: str = "Invalid query"):
        # "Invalid query: Invalid query" — the doubled text is Base44's own.
        super().__init__(500, f"Invalid query: {reason}", error_type="ValueError")

    def as_write_refusal(self) -> AppError:
        return AppError(400, self.message)


def validate_user_query(q: dict) -> None:
    """Recursively walk a user-supplied `q=` filter and refuse what Base44's
    reader refuses: an operator not in ALLOWED_QUERY_OPERATORS, a regular
    expression's options that are not a string of `imsx`, a pattern over
    1,000 characters. Runs BEFORE RLS merge so the RLS-internal `$nor` (deny
    filter) is not subject to this allowlist (user `$nor` is allowed in its
    own right — see ALLOWED_QUERY_OPERATORS).
    """
    if not isinstance(q, dict):
        return
    for key, value in q.items():
        if isinstance(key, str) and key.startswith("$"):
            if key not in ALLOWED_QUERY_OPERATORS:
                raise RefusedQuery()
            if key == "$options":
                if not isinstance(value, str):
                    raise RefusedQuery("$options must be a string")
                for option in value:
                    if option not in REGEX_OPTIONS:
                        raise RefusedQuery(f"Invalid regex option: {option}")
            elif key == "$regex" and isinstance(value, str) and len(value) > REGEX_LONGEST:
                raise RefusedQuery()
            elif key in ("$and", "$or", "$nor") and isinstance(value, list):
                for sub in value:
                    validate_user_query(sub)
            elif key in ("$not", "$elemMatch", "$text") and isinstance(value, dict):
                validate_user_query(value)
        elif isinstance(value, dict):
            validate_user_query(value)


def is_collaborator(ctx: AuthedContext) -> bool:
    """True if the auth context can manage the User dataset (list/view-other/
    update-other/delete-other users).

    F-047 (probed live 2026-05-24 against B44 ParityGym): Base44 gates ALL
    User-management ops on **collaborator / owner** status, NOT on the live-app
    `_app_role`. An app-role admin who is not a collaborator (n001:
    `_app_role:"admin"`, `collaborator_role:None`) is denied list/view/update/
    delete of OTHER users — only the owner / invited collaborators (who carry
    `collaborator_role`, e.g. owner→"editor") pass. Base44 docs confirm: "Admin/
    User roles do not give access to the Users dataset; only collaborators and
    the app owner can." This corrects the earlier D-058/D-059 assumption that
    `_app_role:admin` granted user-management rights — it does not.

    `collaborator_role` is the migrated signal (owner + invited collaborators
    carry it); service-role is admin-level by construction.
    """
    if ctx.token_class == "service_role":
        return True
    if not ctx.user:
        return False
    if ctx.user.get("collaborator_role") is not None:
        return True
    return False


def created_by_hidden(app_settings: dict) -> bool:
    """Whether the app hides `created_by` (the creator's email) on every row
    it hands out — REST and realtime alike. Two switches on Base44's app
    record, either one hides it: `hide_entity_created_by` (the owner's own
    setting) and `hide_entity_created_by_locked` (apps created since summer
    2026 are locked to hiding, whatever the first switch says — measured
    2026-09-28: 218 of 387 apps). The field stays stored, and rules and `q`
    filters keep reading it."""
    return bool(
        app_settings.get("hide_entity_created_by")
        or app_settings.get("hide_entity_created_by_locked")
    )


def serialize_for_rls(doc: dict) -> dict:
    """RLS-input shape: `_id` -> `id` (str), `environment` preserved.

    Unlike the REST-output models, the RLS input dict must retain the
    `environment` field — RLS rules may key off it. `serialize_entity`
    strips environment, so RLS gets its own minimal mapper here.
    """
    out: dict = {}
    for key, value in doc.items():
        if key == "_id":
            out["id"] = str(value)
        else:
            out[key] = value
    if "environment" not in out:
        out["environment"] = None
    return out


def build_mongo_query(user_query: dict, rls_filter: dict) -> dict:
    """Combine the user-supplied `q=` filter with the RLS filter.

    Both branches go through `prepare_mongo_filter` so the wire-level key
    `id` (24-char hex) translates to Mongo's `_id` (ObjectId). Probed against
    Base44: `GET /entities/Note?q={"id":"<hex>"}` returns the matching row,
    so the same-decisions equivalent on our side is to perform the
    `id` → `_id` rewrite on user queries too. `prepare_mongo_filter` is a
    no-op on any key other than `id` and the logical `$and/$or/$nor` branches.
    """
    parts = []
    if rls_filter:
        parts.append(db.prepare_mongo_filter(rls_filter))
    if user_query:
        parts.append(db.prepare_mongo_filter(user_query))
    if not parts:
        return {}
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}


def build_phantom_user(body: dict, ctx: AuthedContext, settings) -> dict:
    """Construct the phantom-user response for POST /entities/User.

    Base44 does not persist `User` POSTs at all (probed 2026-05-22 via
    `?api_key=...&X-Bypass-RLS:true` over the User collection — zero rows
    with `created_by_id=anonymous` after dozens of anonymous POSTs). The
    handler validates input, generates an id + timestamps, and echoes a
    fixed 9-field shape:

      email → full_name → role → id → created_date → updated_date →
      created_by_id → created_by → is_sample

    Orphan/custom fields from the body are NOT echoed; non-required
    built-ins (`disabled`, `is_verified`, `app_id`, `is_service`,
    `collaborator_role`, `_app_role`, `force_password_reset`) are NOT
    emitted.
    """
    from app.core.responses import utcnow

    if ctx.user:
        created_by_id = ctx.user.get("id", "anonymous")
        created_by = ctx.user.get("email", "anonymous")
    else:
        created_by_id = "anonymous"
        created_by = "anonymous"

    now = utcnow()
    return {
        "email": body.get("email", ""),
        "full_name": body.get("full_name", ""),
        "role": body.get("role", "user"),
        "id": str(ObjectId()),
        "created_date": now,
        "updated_date": now,
        "created_by_id": created_by_id,
        "created_by": created_by,
        "is_sample": False,
    }


def validate_user_create_fields(body: dict) -> None:
    """Raise WrappedValidationError on missing/non-string required fields.

    Base44 hard-codes `email`, `full_name`, `role` as required strings on
    User creates (D-073), regardless of the User entity's schema. The
    error envelope is #2 (wrapped ValidationError); errors mirror what
    Pydantic 2.12 emits when validating a model with the three fields
    declared `str`:

    - **Missing key** → `type=missing`, no `url`, `input` is the whole body.
    - **Wrong type / null** → `type=string_type`,
      `url='https://errors.pydantic.dev/2.12/v/string_type'`, `input` is
      the actual offending value.

    Both forms are emitted in one envelope when multiple fields fail.
    Probed against Base44 2026-05-22 — exact field-order, msg strings,
    and `url` value confirmed.
    """
    errors: list[dict] = []
    for field in ("email", "full_name", "role"):
        if field not in body:
            errors.append({
                "type": "missing",
                "loc": (field,),
                "msg": "Field required",
                "input": body,
                "url": "https://errors.pydantic.dev/2.12/v/missing",
            })
            continue
        value = body[field]
        if not isinstance(value, str):
            errors.append({
                "type": "string_type",
                "loc": (field,),
                "msg": "Input should be a valid string",
                "input": value,
                "url": "https://errors.pydantic.dev/2.12/v/string_type",
            })
    if errors:
        raise WrappedValidationError(errors)


def can_update_user_role(ctx: AuthedContext) -> bool:
    # F-047: updating another user (any field, incl. role) requires collaborator/
    # owner status — NOT live-app `_app_role:admin`. Same gate as every other
    # User-management op (probed live: n001 app-admin non-collaborator → 403 on
    # PUT other user). Delegates to the canonical collaborator check.
    return is_collaborator(ctx)


def filter_user_update_fields(body: dict, ctx: AuthedContext, schema: dict) -> dict:
    """Filter a User update body to fields we'll actually write to Mongo.

    User docs are stored flat — built-ins AND `additional_user_data_schema`
    custom fields all at the top level (matches Base44; see A2-DEEP-DIVE.md).
    No path rewriting; we just drop the immutable keys.

    DEPRECATED — kept only for legacy callers. New User PUT flow uses
    `apply_user_put_reorder` which models Base44's M-009 storage-reorder
    mechanism explicitly. This filter dropped every non-customs body key
    and used `$set`, which produced wire-shape divergences once the user
    had been PUT-touched on Base44 (Base44 records touch even on
    silently-rejected value changes, moving the field's storage
    position).
    """
    return {k: v for k, v in body.items() if k not in USER_IMMUTABLE_FIELDS}


# Anchored User fields: their storage position never moves on PUT touch,
# AND their value is immutable for non-admin self-PUT (silently rejected).
# Probed 2026-05-22 on AuthRolesLab Daniel-side: PUT `email: "x@y.com"`,
# `full_name: "X"`, `role: "user"` against +pmS6 (fresh-registered)
# returned 200 with no position change and no value change.
# Anchored fields — never reorder, value never updated by non-admin PUT.
# `role` is the pre-id slot-1 anchor (admin-mutable, see below); the
# others are simply silently dropped on PUT. `collaborator_role` was
# moved here from the movable set per F-024 (probed 2026-05-22 across
# 5 paired PUT cases on +pmM9: value-mutation cases sending viewer/
# editor/admin/null/"" all silently dropped AND never moved out of the
# post-id zone, even though prior M-009 modeling placed it among the
# movable canonicals).
_USER_ANCHORED_FIELDS = frozenset({
    "role", "email", "full_name", "id", "collaborator_role",
})

# Canonical post-id fields with value-immutable semantics on user PUT
# (server-controlled). Touching them via PUT registers a "touch" that
# moves the field's storage position to the end of the pre-id extras
# zone, but the value itself is silently preserved (matches Base44 probe
# 2026-05-22 — confirmed for the remaining 7 fields on non-admin PUT;
# `collaborator_role` moved to anchored per F-024).
_USER_VALUE_IMMUTABLE_FIELDS = frozenset({
    "_app_role", "is_verified", "force_password_reset", "disabled",
    "is_service", "app_id", "disabled_reason",
    "created_date", "updated_date", "id", "_id",
})


def apply_user_put_reorder(
    existing: dict,
    body: dict,
    ctx: AuthedContext,
    schema: dict,
) -> dict:
    """Apply a User PUT body to the existing Mongo doc, replicating
    Base44's M-009 storage-reorder mechanism.

    Empirical mechanism (probed 2026-05-22 against +pmS6 fresh user on
    AuthRolesLab Daniel-side; see auth-x-entities/findings/M-009 docs):

    - **Anchored** (`role`, `email`, `full_name`, `id`): never reorder.
      Value updated only when the caller is authorized AND the field is
      writable (currently only `role`, gated by `can_update_user_role`).
    - **Value-immutable canonicals** (`_app_role, is_verified,
      force_password_reset, disabled, is_service, collaborator_role,
      app_id, disabled_reason, created_date, updated_date`): touch
      registers a reorder (remove from current storage position,
      re-insert at end of pre-id extras zone right before stored `id`),
      but value is silently preserved.
    - **Orphans / customs / `_id` literal extras**: both reorder and
      value-update. New keys land at end of pre-id; existing pre-id keys
      keep their position with the new value.

    The `pre-id zone` is the region of storage between `role` (position
    2) and the stored `id` field. The `post-id zone` is everything
    after `id` — populated initially at register-time with the canonical
    12, depleted as user PUTs move fields into the pre-id zone.

    On `role` change (admin-only — non-admin gets 403 before this
    function runs), Base44 also propagates the new value to `_app_role`.
    We replicate that — but `_app_role` propagation does NOT register a
    separate touch (i.e., `_app_role`'s storage position stays put even
    when role changes; if `_app_role` is in pre-id from a prior touch,
    it stays; if it's in post-id, it stays). Probe-verified.

    The returned dict is a fresh OrderedDict suitable for
    `coll.replace_one({_id: ...}, returned)`.
    """
    from collections import OrderedDict

    # Plan: walk `body` in insertion order to determine (a) which keys
    # update values, (b) which keys trigger reorder.
    value_updates: dict[str, object] = {}
    touched_order: list[str] = []
    for key, value in body.items():
        if key == "_id":
            # Mongo's `_id` is structurally protected — `replace_one` enforces
            # the existing `_id`. Base44 probe accepts `_id` PUT as a pre-id
            # extra (storing the value as a separate doc field), but our
            # Mongo storage can't carry both an ObjectId `_id` and a string
            # `_id` extra. Silently drop (no reorder, no value change).
            continue
        if key in _USER_ANCHORED_FIELDS:
            # Anchored — no reorder. Value updated only if writable.
            if key == "role":
                value_updates["role"] = value
                # Base44 propagates role → _app_role on admin role change;
                # this propagation does NOT trigger a separate _app_role
                # touch (i.e., _app_role's storage position doesn't move
                # solely because role changed).
                value_updates["_app_role"] = value
            # email, full_name, id: silently dropped value (admin scenarios
            # not yet probed; same-decisions when probed will live here).
            continue
        # Movable — touch always registers reorder.
        touched_order.append(key)
        if key in _USER_VALUE_IMMUTABLE_FIELDS:
            # Touch but no value update.
            continue
        # Writable: custom-schema field or orphan.
        # Base44 probe-confirmed: orphans + customs persist user-PUT values.
        value_updates[key] = value

    # `updated_date` always bumps on PUT (server-stamped, anchored). The
    # bump is NOT a user-driven touch — it doesn't move `updated_date`'s
    # storage position even though we're writing it.
    value_updates["updated_date"] = utcnow_naive()

    touched_set = set(touched_order)

    # Reconstruct the doc with reorder semantics.
    new_doc: OrderedDict = OrderedDict()
    new_doc["_id"] = existing["_id"]
    if "role" in existing:
        new_doc["role"] = value_updates.get("role", existing["role"])

    seen_id = False
    for key, value in existing.items():
        if key in ("_id", "role"):
            continue
        if key == "id":
            # At the id position: emit all touched-not-yet-in-new_doc keys
            # in body order, then emit id itself.
            for tk in touched_order:
                if tk in new_doc:
                    continue
                # Use updated value if writable, else preserve existing
                # value (or None if it's a brand-new key with no prior
                # existing value — Base44 stamps None for new movable
                # canonicals that didn't exist; for orphans we use the
                # provided body value via value_updates).
                if tk in value_updates:
                    new_doc[tk] = value_updates[tk]
                elif tk in existing:
                    new_doc[tk] = existing[tk]
                else:
                    new_doc[tk] = None
            new_doc["id"] = existing.get("id") or str(existing["_id"])
            seen_id = True
            continue
        if key in touched_set and not seen_id:
            # Touched key already in pre-id zone — keep current position,
            # apply value update if any.
            new_doc[key] = value_updates.get(key, value)
            # Mark as already-emitted so the id-boundary block won't dup it.
            touched_set.discard(key)
            continue
        if key in touched_set and seen_id:
            # Touched key in post-id zone — skip (will be re-emitted at
            # end of pre-id in a future iteration, but since we already
            # passed id we've also missed the chance for that. Means the
            # touch logic above placed them before id correctly).
            continue
        # Untouched canonical / orphan — preserve at current position
        # with possibly-updated value (e.g., `updated_date`).
        new_doc[key] = value_updates.get(key, value)

    if not seen_id:
        # Legacy: existing doc has no stored `id` field. Emit
        # remaining-touched keys at end of pre-id, then id.
        for tk in touched_order:
            if tk in new_doc:
                continue
            if tk in value_updates:
                new_doc[tk] = value_updates[tk]
            elif tk in existing:
                new_doc[tk] = existing[tk]
            else:
                new_doc[tk] = None
        new_doc["id"] = str(existing["_id"])

    return new_doc


# normalize_user_row removed in Phase 10; the data-subobject flatten branch
# in user_doc_to_userresource_input was removed alongside the flat-storage
# migrator change (see A2-DEEP-DIVE.md §5).
