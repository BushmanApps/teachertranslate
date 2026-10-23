"""How a read names what it wants: the query parameters the list routes share
(the list, the paged list, the count), read the way Base44 reads them today
(measured 2026-09-28/29, the entity-pages chase).

- `q` is a JSON object; anything else is refused before the database is asked.
- `limit` and `skip` are whole numbers.
- `sort` names one column (`sort_by` is its other spelling, read only when
  `sort` is not given).
- `fields` names the fields a row is cut down to; the row's `id` always stays.
- EVERY OTHER PARAMETER IS A FILTER on the field of that name, its value read
  as the field's declared type — `?agent=ana&qty=1` — and a name that is no
  field of the entity matches no row.
"""

from __future__ import annotations

import json

from pymongo.errors import OperationFailure
from starlette.datastructures import QueryParams

from app.core.errors import AppError, AppHTTPException
from app.modules.entities import fields as field_kinds

PAGE_DEFAULT = 100
ROWS_CAP = 5000
DISTINCT_CAP = 1000

LIST_PARAMETERS = frozenset({"q", "sort", "sort_by", "limit", "skip", "fields"})
PAGE_PARAMETERS = LIST_PARAMETERS | {"cursor", "distinct"}


# The database's own codes for a filter it cannot PARSE (MongoDB 7, read on
# the queries Base44 was asked — probe 09 of the entity-pages chase).
_UNPARSED = {
    2: "BadValue",          # `$in` that is no list, `$size: "x"`, an unknown type name, `$regex: 1`, …
    14: "TypeMismatch",     # `$text: {$search: 1}`
    51091: "a regular expression that does not compile",
}


def refused_by_database(failure: OperationFailure) -> AppError:
    """How a query the DATABASE refuses is answered — on every route that
    takes a filter, reads and writes alike (measured 2026-09-29; in May the
    answer carried the database's own error): a filter it cannot parse is the
    caller's fault, 400 "Invalid query"; a query it parses and cannot run —
    a `$text` with no text index, a sort by `$natural` — is 500 "Query
    failed"."""
    if failure.code in _UNPARSED:
        return AppError(400, "Invalid query")
    return AppError(500, "Query failed")


def filter_of(params: QueryParams) -> dict:
    """The `q` of a list or a page."""
    text = params.get("q")
    if not text:
        return {}
    try:
        query = json.loads(text)
    except json.JSONDecodeError as err:
        raise AppHTTPException(400, f"Invalid q parameter: {err}") from None
    if not isinstance(query, dict):
        raise AppHTTPException(400, "Invalid q parameter: q must be a JSON object")
    return query


def count_filter_of(params: QueryParams) -> dict:
    """The `q` of a count: the same filter, refused in the count's own words."""
    text = params.get("q")
    if not text:
        return {}
    try:
        query = json.loads(text)
    except json.JSONDecodeError:
        query = None
    if not isinstance(query, dict):
        raise AppError(400, "q must be a JSON object")
    return query


def whole_number(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise AppHTTPException(400, "limit and skip must be integers") from None


def sort_of(params: QueryParams) -> str | None:
    """The column a read is sorted by, as written (`-qty`), or None."""
    text = params.get("sort") or params.get("sort_by")
    if not text:
        return None
    if "," in text or text.startswith("["):
        raise AppHTTPException(
            400,
            "sort parameter must be a single column name or a single column name prefixed with '-' for descending order",
        )
    return text


def bare_filters(schema: dict, params: QueryParams, known: frozenset[str]) -> dict:
    """The parameters that are none of the route's own, as a filter."""
    names = [name for name in dict.fromkeys(params.keys()) if name not in known]
    # `sort_by` is the sort's other spelling only while `sort` is not given;
    # beside a `sort` it is a parameter like any other.
    if "sort_by" in params and params.get("sort"):
        names.append("sort_by")
    # the last value of a repeated parameter is the one that counts
    return {name: field_kinds.as_declared(schema, name, params.getlist(name)[-1]) for name in names}


def fields_of(params: QueryParams) -> list[str] | None:
    names = [name.strip() for text in params.getlist("fields") for name in text.split(",")]
    names = list(dict.fromkeys(name for name in names if name))
    return names or None


def cut_to(row: dict, names: list[str]) -> dict:
    """A row cut down to the named fields, in the order they were named; a
    nested name keeps its parent with that child alone; a name the row does
    not have is dropped; the row's `id` closes it."""
    cut: dict = {}
    for name in names:
        if name != "id" and _has(row, name):
            _put(cut, name, _get(row, name))
    if "id" in row:
        cut["id"] = row["id"]
    return cut


def _has(source, path: str) -> bool:
    for part in path.split("."):
        if not isinstance(source, dict) or part not in source:
            return False
        source = source[part]
    return True


def _get(source, path: str):
    for part in path.split("."):
        source = source[part]
    return source


def _put(target: dict, path: str, value) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value
