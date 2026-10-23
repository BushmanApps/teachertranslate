"""What a field IS, as the entity's schema declares it — the one judgment the
read routes share (the paged list's sort, the distinct values, the aggregate's
groups and measures, a bare query parameter's value).

Base44's answers name the kind in their own words (measured 2026-09-28/29,
the entity-pages chase): a declared scalar is `string`, `number`, `integer`
or `boolean`; `array` and `object` are declared and not scalar; the stamps
the platform keeps on every row are declared too — `id`, `created_date` and
`updated_date` count as a `date`, `created_by` and `created_by_id` as a
`string` — and `is_sample` is not a field a caller may name. A path walks an
object's own declared properties (`meta.n`); it does not walk into an array
(`tags.0` is undeclared).
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.core.errors import WrappedValidationError

STAMPS = {
    "id": "date",
    "created_date": "date",
    "updated_date": "date",
    "created_by": "string",
    "created_by_id": "string",
}
SCALARS = frozenset({"string", "number", "integer", "boolean", "date"})
NUMERIC = frozenset({"number", "integer"})
UNDECLARED = "undeclared"

_PYTHON = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}


def _declaration(schema: dict, path: str) -> dict | None:
    properties = schema.get("properties") or {}
    node: dict | None = None
    for part in path.split("."):
        node = properties.get(part) if isinstance(properties, dict) else None
        if not isinstance(node, dict):
            return None
        properties = node.get("properties") or {} if node.get("type") == "object" else {}
    return node


def kind(schema: dict, path: str) -> str:
    """The field's kind, or `UNDECLARED`."""
    if path in STAMPS:
        return STAMPS[path]
    declared = _declaration(schema, path) if path else None
    if declared is None:
        return UNDECLARED
    declared_type = declared.get("type")
    return declared_type if declared_type in _PYTHON else UNDECLARED


def python_type(schema: dict, path: str) -> type:
    """The Python type a declared field's values are read as."""
    return _PYTHON[kind(schema, path)]


def is_date(schema: dict, path: str) -> bool:
    """A field a date bucket may read: a stamp that is a date, or a string the
    schema formats as a date or a date-time."""
    if path in ("created_date", "updated_date"):
        return True
    declared = _declaration(schema, path) if path else None
    return bool(declared) and declared.get("type") == "string" and declared.get("format") in ("date", "date-time")


def mongo_path(path: str) -> str:
    """The stored name of a field a caller names (`id` is stored as `_id`)."""
    return "_id" if path == "id" else path


def as_declared(schema: dict, path: str, value: str) -> Any:
    """A query-string value read as the field's declared type, the way Base44
    reads a bare parameter (`qty=1` is the number 1, `paid=true` the boolean);
    a field nobody declared keeps the string. A value the type cannot take is
    Base44's 422 (`tags=b`: "Input should be a valid list")."""
    if path in STAMPS or kind(schema, path) not in _PYTHON:
        return value
    try:
        return TypeAdapter(python_type(schema, path)).validate_python(value)
    except ValidationError as err:
        raise WrappedValidationError(err.errors()) from None
