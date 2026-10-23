"""Dynamic per-schema entity model factory.

Base44 builds one Pydantic class per entity at runtime by walking the entity's
JSON-Schema `properties` and mapping each field to a Pydantic type. Strictness:

- Most paths: `extra='ignore'` — unknown fields silently dropped (D-072).
- `PUT /entities/User/me` only: `extra='allow'` — extras are persisted as
  custom data on the User row, surfaced on the response wire (D-033, D-072).
  The handler partitions validated body keys via `model_extra` to route
  schema-declared fields to the top level and extras into `data.<key>` on
  the Mongo doc.

The factory is invoked once per entity at lifespan startup (after
`registry.load()`) and the resulting classes are cached. Hot-reloading entity
schemas (not currently supported) would invalidate the cache.

JSON Schema → Pydantic mapping (findings L757-768):

| JSON Schema                           | Pydantic |
|---------------------------------------|----------|
| `{"type": "string"}`                  | `str` (also for `enum: [...]` and `format: date-time`/`format: date` — see notes below) |
| `{"type": "integer"}`                 | `int`    |
| `{"type": "number"}`                  | `float` (Base44 emits `4.0` on wire for a `number` field regardless of input form) |
| `{"type": "boolean"}`                 | `bool`   |
| `{"type": "array", "items": {...}}`   | `list[<element>]` (items.type narrows the element type) |
| `{"type": "object"}`                  | recursive `NestedObject` model when it declares `properties` (else `dict`) |

Fields in `schema.required` become required Pydantic fields. Other fields
become `Optional[X] = None` unless they have a `default` in the schema.

`enum` on string fields is intentionally NOT narrowed to `Literal[...]`.
Probed against Base44 (data-core-lab Note.status, 2026-05-20): unknown
enum values (`status="unknown"`, case-mismatched `"DRAFT"`) persist with
HTTP 200; only non-string inputs (int, bool) are rejected by the string
type check. So enum is documentation-only on Base44 — not a runtime
constraint.

Arrays are typed by recursing into `items` — `{type: array, items: {type:
string}}` becomes `list[str]`, so Pydantic per-element rejects int/bool
inputs (probed: `tags: [1,2]` → 422 with `string_type` at `loc=tags.0`
and `tags.1`). Untyped arrays (`items: {}` or omitted) fall back to
`list` — accept anything.
"""

from __future__ import annotations

import typing
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model


# Canonical server-stamp wire order for the REST entity response — used by
# `entities/services.py:serialize_for_rest` to construct the input dict so
# `model_dump(mode="json")` emits in Base44's exact order (probed 2026-05-21
# on data-core-lab):
#
#   <schema fields in declaration order>,
#   <extras from the Mongo doc, in storage-insertion order>,   # e.g. $set-injected
#   id, created_date, updated_date, created_by_id, created_by, is_sample
#
# `environment` is stamped on storage but stripped from REST; realtime
# (Socket.IO event payloads) keeps it (D-061). Note `created_by_id` precedes
# `created_by` on the wire — opposite of the alphabetical / declaration-
# instinct order.
#
# These keys are NOT declared on the response model — the model only declares
# schema fields. Stamps + injected extras enter via `extra="allow"`; Pydantic
# v2 emits declared fields first (declaration order), then extras in input-
# insertion order, so the canonical wire order falls out of the input-dict
# construction in `serialize_for_rest`.
ENTITY_STAMP_ORDER: tuple[str, ...] = (
    "id",
    "created_date",
    "updated_date",
    "created_by_id",
    "created_by",
    "is_sample",
)


_JSON_TYPE_MAP = {
    "integer": int,
    # JSON Schema `"number"` → `float`. Base44 emits the float wire form
    # (`4.0`, not `4`) for a `number`-typed field regardless of whether the
    # stored value is an int or float — probed on `/entities/Note` against a
    # `score: type: number` row created with integer input. Pydantic V2's
    # bare `float` annotation matches by coercing to float on serialization.
    # `type: integer` stays `int` for fields that should preserve int form.
    "number": float,
    "boolean": bool,
    # "array"/"object" handled by _field_type directly (array narrows
    # list[<x>]; object builds a recursive NestedObject model).
}


def _build_nested_object_model(field_def: dict) -> type[BaseModel]:
    """Build the recursive Pydantic model for a JSON-Schema `object` field.

    Base44 compiles object-typed properties into a nested model it names
    `NestedObject` — leaked via the `model_type` error ctx.class_name
    ("Input should be a valid dictionary or instance of NestedObject",
    probed 2026-05-24 on ParityGym `CatalogItem.meta`). It uses
    `extra="ignore"` (unknown nested keys dropped) and recurses with the
    same field mapping + coercion as the top level, so a provided
    `meta: {label, score, junk}` is stored as `{label, score}` with `score`
    coerced to float and `junk` dropped; a non-dict value 422s with
    `model_type`. Reuses `_build_fields` so nested objects / arrays-of-object
    follow the identical mapping recursively.
    """
    fields = _build_fields(field_def)
    return create_model(
        "NestedObject",
        __config__=ConfigDict(extra="ignore"),
        **fields,
    )


def _field_type(field_def: dict) -> Any:
    """Map a single JSON-Schema property to a Pydantic type."""
    jt = field_def.get("type")

    # Probed against Base44 prod 2026-06-02 (NullableProbe app): non-scalar
    # `type` — e.g. the array-form `["string", "null"]` Pydantic 2 emits for
    # nullable fields, observed in production on Casey Security's
    # `QARepository.organization_id` — falls through to `Any` in Base44's
    # runtime: no value validation, only required-vs-optional presence
    # enforcement. Without this guard, the `_JSON_TYPE_MAP.get(jt, Any)`
    # lookup below TypeErrors on unhashable list before the `Any` fallback
    # fires.
    if not isinstance(jt, str):
        return Any

    if jt == "string":
        # Base44 treats `format: date-time` and `format: date` schema fields
        # as plain str on user write/read: empirically POSTing
        # `{published_at: "banana"}` against a `format: date-time` field
        # returns 200 and persists the literal "banana" (BSON String in
        # Mongo, round-trips byte-exact on read). Only non-string scalars
        # (int/float/bool/array/object) are 422'd. The `format` annotation
        # is informational only — same-decisions per probe 2026-05-21.
        # Server-stamped `created_date`/`updated_date` go through a
        # different path (stamp_on_create assigns a datetime object
        # directly; they're not declared via `_field_type`) and keep
        # their BSON Date storage.
        return str

    if jt == "array":
        items = field_def.get("items") or {}
        if items:
            return list[_field_type(items)]  # type: ignore[valid-type]
        return list

    if jt == "object":
        # Object WITH declared properties → recursive NestedObject model
        # (Base44's exact construction — strips unknown keys, coerces nested
        # values). Untyped object (no properties) → plain `dict`: accepts any
        # shape, no coercion.
        if field_def.get("properties"):
            return _build_nested_object_model(field_def)
        return dict

    return _JSON_TYPE_MAP.get(jt, Any)


def _field_descriptor(
    field_name: str,
    field_def: dict,
    is_required: bool,
) -> tuple[Any, Any]:
    """Build the (type, FieldInfo-or-default) tuple for `create_model`.

    Nullability rule probed against Base44 (data-core-lab Note, 2026-05-20):
    every NON-REQUIRED field accepts explicit `null` input regardless of
    whether the schema declares a `default` — `{"title":"a","status":null}`
    persists `status: null` (200), even though `status` has a default of
    `"draft"`. So the type annotation is `Optional[py_type]` for any
    non-required field; only required fields keep the strict type.
    """
    py_type = _field_type(field_def)
    origin = typing.get_origin(py_type)
    annotated_type = py_type if is_required else Optional[py_type]

    if "default" in field_def:
        default = field_def["default"]
        if (py_type is list or origin is list) and isinstance(default, list):
            return (annotated_type, Field(default_factory=lambda: list(default)))
        if (py_type is dict or origin is dict) and isinstance(default, dict):
            return (annotated_type, Field(default_factory=lambda: dict(default)))
        return (annotated_type, default)

    if is_required:
        return (py_type, ...)

    # Array fields default to `[]` even with no explicit schema default.
    # Probed 2026-05-24 (ParityGym `CatalogItem.tags`/`attachments`): an UNSET
    # array field emits `[]` on read, while an explicit `null` still persists
    # as null — so the field stays `Optional[list[...]]` but carries a
    # default_factory. Scalars and objects keep the plain `None` default
    # (unset → null on read).
    if py_type is list or origin is list:
        return (annotated_type, Field(default_factory=list))

    return (annotated_type, None)


def _build_fields(schema: dict) -> dict[str, tuple[Any, Any]]:
    """Build field descriptors with Base44's canonical declaration order:
    required fields in declaration order, then optional fields sorted
    alphabetically.

    Probed 2026-05-22 against AuthRolesLab Task (post-`/coding/write`):
    schema declares `properties: {title, status, secret_note}` with
    `required: [title]`. Base44's wire emits `title, secret_note, status`
    — required first, then optional fields in alphabetical order
    (`secret_note` < `status`). Holds across POST / GET / list regardless
    of body order.

    Pydantic v2 preserves field declaration order on `model_dump`, so
    declaring fields in this order produces Base44's exact wire layout
    by construction.
    """
    properties: dict = schema.get("properties", {}) or {}
    required: set[str] = set(schema.get("required", []) or [])
    for field_name, field_def in properties.items():
        if field_def.get("required") is True:
            required.add(field_name)

    required_in_decl_order = [k for k in properties if k in required]
    optional_alphabetical = sorted(k for k in properties if k not in required)
    canonical_order = required_in_decl_order + optional_alphabetical

    fields: dict[str, tuple[Any, Any]] = {}
    for field_name in canonical_order:
        fields[field_name] = _field_descriptor(field_name, properties[field_name], field_name in required)
    return fields


def build_entity_model(
    name: str,
    schema: dict,
    *,
    extra_mode: Literal["ignore", "allow"] = "ignore",
) -> type[BaseModel]:
    """Build the **response** model for an entity.

    Declares ONLY schema fields. Server stamps (id, created_date,
    updated_date, created_by_id, created_by, is_sample, environment) are
    NOT declared — they enter via `extra="allow"` so their wire position
    is dictated by input-dict insertion order, which
    `entities/services.py:serialize_for_rest` builds in Base44's canonical
    wire order:

      <schema fields in declaration order>,
      <orphan extras from $set-injected unknown fields, in doc storage order>,
      id, created_date, updated_date, created_by_id, created_by, is_sample

    Probed 2026-05-21 on data-core-lab: extras inserted via
    `update-many $set` surface BETWEEN schema fields and the canonical
    stamps on Base44's wire. Declaring stamps on this model would push
    extras to the END (Pydantic v2 default), diverging from Base44 in
    that edge case. Same architectural pattern as `build_user_resource`
    in `core/models/users.py`.
    """
    fields = _build_fields(schema)
    config = ConfigDict(extra=extra_mode)
    return create_model(  # type: ignore[call-overload]
        name,
        __config__=config,
        **fields,
    )


def build_entity_body_model(
    name: str,
    schema: dict,
    *,
    extra_mode: Literal["ignore", "allow"] = "ignore",
) -> type[BaseModel]:
    """Build the **body-validation** model for an entity — schema fields only.

    Schema fields only — no server-stamp fields. The body validator must
    not require `id`/`created_date`/etc. (clients never send them on
    CREATE; UPDATE only sends partials). Use this on `EntityModel(**body)`
    calls; catch `ValidationError` and raise `WrappedValidationError` for
    envelope #2.

    For `User` on `PUT /entities/User/me`, pass `extra_mode='allow'` so
    custom `additional_user_data_schema` fields are surfaced via
    `instance.model_extra` and the handler can route them into `data.<key>`
    on the Mongo doc (D-033, D-072).
    """
    fields = _build_fields(schema)
    config = ConfigDict(extra=extra_mode)
    return create_model(  # type: ignore[call-overload]
        f"{name}Body",
        __config__=config,
        **fields,
    )


def _build_partial_fields(schema: dict) -> dict[str, tuple[Any, Any]]:
    """Per-field type rules for the partial-body model used on PUT paths.

    - **Required fields**: strict type (e.g. `str`), omittable via
      `Field(default=None, validate_default=False)`. Probed against Base44:
      a PUT body that OMITS `title` → 200 with merge; PUT with `title=None`
      → 422 ValidationError "Input should be a valid string"; PUT with
      `title=42` → 422 same. `validate_default=False` is the
      Pydantic-2 escape that lets the field be omittable (no required-
      marker) WITHOUT validating the synthetic None default against the
      strict type.
    - **Non-required fields**: `Optional[X] = None`. Probed: Base44
      accepts explicit `null` on a non-required schema field and persists
      it. Our serializer renders the null on read.

    The shape difference exists because Base44 enforces type-strictness on
    required schema fields even on partial update — they're the load-
    bearing identity fields and can't be cleared by client request.
    """
    properties: dict = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    for k, v in properties.items():
        if isinstance(v, dict) and v.get("required") is True:
            required.add(k)

    # Same canonical ordering as `_build_fields`: required first
    # (declaration order), then optional alphabetical.
    required_in_decl_order = [k for k in properties if k in required]
    optional_alphabetical = sorted(k for k in properties if k not in required)
    canonical_order = required_in_decl_order + optional_alphabetical

    fields: dict[str, tuple[Any, Any]] = {}
    for field_name in canonical_order:
        field_def = properties[field_name]
        py_type = _field_type(field_def)
        if field_name in required:
            # Strict type — None/wrong-type rejected. Field is omittable
            # because the default is None AND validate_default=False, so
            # Pydantic skips validating the (invalid-for-str) None default
            # when the client omits the key. When the client SENDS the key
            # (including with value None), normal type-validation fires.
            fields[field_name] = (py_type, Field(default=None, validate_default=False))
        else:
            # Non-required → Optional, accepts None explicitly.
            fields[field_name] = (Optional[py_type], None)
    return fields


def build_entity_body_model_partial(
    name: str,
    schema: dict,
    *,
    extra_mode: Literal["ignore", "allow"] = "ignore",
) -> type[BaseModel]:
    """Build the **partial-body-validation** model — every field Optional.

    Used by PUT / `update_many` paths where the client may omit any field
    including schema-required ones. Per-field type checks still apply
    when a field is present (e.g. `{"title": 42}` still 422s on type).
    Base44 production verified: partial PUT with `{"status":"done"}`
    against a Task entity that requires `title` returns 200 and merges
    the partial into the existing row (probed 2026-05-22 against
    `positive-flow-state-labs.base44.app`). Same-decisions: the canonical
    Pydantic pattern for partial-update endpoints is a separate model
    with all fields Optional + default None.
    """
    fields = _build_partial_fields(schema)
    config = ConfigDict(extra=extra_mode)
    return create_model(  # type: ignore[call-overload]
        f"{name}BodyPartial",
        __config__=config,
        **fields,
    )
