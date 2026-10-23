"""GET /api/apps/:appId/entities/:entityName/v2/list — one page of rows, or of
one field's distinct values, and the cursor of the next.

The route `list(options)` and `filter(query, options)` call since @base44/sdk
0.8.49 (2026-09-22). A migrated frontend installs the newest 0.8.x at every
build, so an app that hands `list()` an object reaches this route whatever
SDK it was written against.

The contract is Base44's, measured on the entity-pages fixture (2026-09-28/29:
`research/divergence-chasing/2026-09-28-entity-pages-count-aggregate-upsert`).
ONE thing cannot be theirs: the order of rows that TIE on the sort. Base44's
changes with the page size; here ties follow the row's id in the sort's own
direction — which is also where Base44 draws the line between two pages.
"""

from __future__ import annotations

import datetime

from bson import ObjectId
from fastapi import Depends, Request
from pymongo.errors import OperationFailure

from app.core import db
from app.core.errors import AppError
from app.core.security import fls, rls
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.modules.entities import cursor, fields as field_kinds, reading, services
from app.modules.entities.helpers import (
    RefusedQuery,
    build_mongo_query,
    created_by_hidden,
    resolve_schema,
    validate_user_query,
)

DEFAULT_SORT = "-created_date"


def _direction(sort: str) -> tuple[str, int]:
    return (sort[1:], -1) if sort.startswith("-") else (sort, 1)


def _wire(value):
    """A stored value as the rows' own serializer writes it."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return value


def _stored(doc: dict, path: str):
    value = doc
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


async def list_page(
    app_id: str,
    entity_name: str,
    request: Request,
    ctx: AuthedContext = Depends(get_authed_context),
):
    """The checks come in Base44's order (every neighbouring pair of faults
    was asked of it — probes 06 and 09 of the chase): the parameters are read
    (`q`, the whole numbers, the parameters that are filters), the cursor is
    opened, `skip` is refused, the limit is held to its floor, the cursor is
    held against what the request names, and only then is what the request
    names judged — the distinct field, the sort, the filter's operators."""
    schema = resolve_schema(entity_name)
    if entity_name == "User":
        raise AppError(400, "Not available for the User entity; use the app users endpoints")
    params = request.query_params

    given_filter = reading.filter_of(params)
    limit = reading.whole_number(params["limit"]) if params.get("limit") is not None else reading.PAGE_DEFAULT
    if params.get("skip") is not None:
        reading.whole_number(params["skip"])
    given_sort = reading.sort_of(params)
    bare = reading.bare_filters(schema, params, reading.PAGE_PARAMETERS)
    given = {**given_filter, **bare}

    place = issued = None
    if params.get("cursor"):
        try:
            issued, place = cursor.open_(params["cursor"])
            if issued.get("entity") != entity_name:
                raise cursor.InvalidCursor()
        except cursor.InvalidCursor as refused:
            return cursor.refusal(refused)
    if params.get("skip") is not None:
        raise AppError(400, "Use either skip or cursor, not both")
    if limit < 1:
        raise AppError(400, "limit must be at least 1")

    distinct = params.get("distinct") or None
    given_fields = reading.fields_of(params)
    if issued is not None:
        # What the request names must be the cursor's; what it leaves out is.
        try:
            if distinct and distinct != issued["distinct"]:
                raise cursor.InvalidCursor("Cursor was issued for a different distinct field")
            if given_sort and not issued["distinct"] and _direction(given_sort) != _direction(issued["sort"]):
                raise cursor.InvalidCursor("Cursor was issued for a different sort")
            if (params.get("q") or bare) and cursor.filter_mark(given) != cursor.filter_mark(issued["filter"]):
                raise cursor.InvalidCursor("Cursor was issued for a different query")
            if given_fields is not None and set(given_fields) != set(issued["fields"] or []):
                raise cursor.InvalidCursor("Cursor was issued for different fields")
        except cursor.InvalidCursor as refused:
            return cursor.refusal(refused)
        given, distinct = issued["filter"], issued["distinct"]
        given_sort, given_fields = issued["sort"], issued["fields"]
        read = issued
    else:
        if distinct and (given_sort or given_fields):
            raise AppError(400, "distinct values come in ascending order; sort and fields do not apply")
        read = {"entity": entity_name, "filter": given, "sort": given_sort or DEFAULT_SORT, "fields": given_fields, "distinct": distinct}

    limit = min(limit, reading.DISTINCT_CAP if distinct else reading.ROWS_CAP)
    if distinct:
        return await _distinct_page(entity_name, schema, read, limit, place, ctx)

    sort_field, direction = _direction(read["sort"])
    declared = field_kinds.kind(schema, sort_field)
    if declared not in field_kinds.SCALARS:
        raise AppError(400, f"cursor paging sorts by '{sort_field}', which has no declared scalar type ({declared})")
    validate_user_query(given)

    match = build_mongo_query(given, rls.filter_for_read(ctx, entity_name))
    stored_field = field_kinds.mongo_path(sort_field)
    if place is not None:
        match = {"$and": [match, _after(stored_field, direction, place)]} if match else _after(stored_field, direction, place)
    order = {"_id": direction} if stored_field == "_id" else {stored_field: direction, "_id": direction}
    try:
        docs = await db.coll(entity_name).aggregate(
            [{"$match": match}, {"$sort": order}, {"$limit": limit + 1}]
        ).to_list(length=limit + 1)
    except OperationFailure as failure:
        raise reading.refused_by_database(failure) from None
    has_more = len(docs) > limit
    docs = docs[:limit]

    hide = created_by_hidden(ctx.app_settings)
    rows = fls.mask_read_fields(ctx, entity_name, [services.serialize_for_rest(entity_name, d, hide_created_by=hide) for d in docs])
    if given_fields:
        rows = [reading.cut_to(row, given_fields) for row in rows]
    last = docs[-1] if docs else None
    return {
        "items": rows,
        "next_cursor": cursor.issue(read, {"value": _stored(last, stored_field), "id": last["_id"]}) if has_more else None,
        "has_more": has_more,
    }


def _after(stored_field: str, direction: int, place: dict) -> dict:
    """The rows that come after a place in the read's order. The comparison is
    the sort's own (values of different types compare as the sort orders
    them, and a row without the field sorts as one holding null)."""
    beyond = "$gt" if direction == 1 else "$lt"
    if stored_field == "_id":
        return {"_id": {beyond: place["id"]}}
    value = {"$ifNull": [f"${stored_field}", None]}
    return {"$expr": {"$or": [
        {beyond: [value, place["value"]]},
        {"$and": [{"$eq": [value, place["value"]]}, {beyond: ["$_id", place["id"]]}]},
    ]}}


async def _distinct_page(entity_name, schema, read, limit, place, ctx):
    field = read["distinct"]
    declared = field_kinds.kind(schema, field)
    if declared == field_kinds.UNDECLARED:
        raise AppError(400, f"Unknown fields for {entity_name}: ['{field}']")
    if declared == "object":
        raise AppError(400, f"distinct reads '{field}', which has no declared scalar type (object)")
    # Distinct values are an aggregation on Base44, and answer in an
    # aggregation's words: the filter's refusal, the entities it is not served
    # on, and a failure of the database (which is left to the handler of
    # every unexpected one: the database's own message).
    try:
        validate_user_query(read["filter"])
    except RefusedQuery as refused:
        reason = refused.message.removeprefix("Invalid query: ")
        raise AppError(400, f"Invalid aggregation pipeline: $match rejected: {reason}") from None
    if fls.has_read_rules(entity_name):
        raise AppError(
            400,
            "Invalid aggregation pipeline: aggregation is not supported for entities "
            "with field-level read rules; use read_entities instead",
        )
    if field == "created_by" and created_by_hidden(ctx.app_settings):
        return {"items": [], "next_cursor": None, "has_more": False}

    # The rows the caller may read, THEN the rows the filter asks for — two
    # stages, as Base44's pipeline has them (a `$text` is refused by the
    # database for standing second, where a read's is for want of an index).
    stages: list[dict] = [
        {"$match": build_mongo_query({}, rls.filter_for_read(ctx, entity_name))},
        {"$match": build_mongo_query(read["filter"], {})},
        {"$project": {"_id": 0, "v": f"${field_kinds.mongo_path(field)}"}},
    ]
    if declared == "array":
        stages.append({"$unwind": "$v"})
    stages += [{"$match": {"v": {"$ne": None}}}, {"$group": {"_id": "$v"}}, {"$sort": {"_id": 1}}]
    if place is not None:
        stages.append({"$match": {"$expr": {"$gt": ["$_id", place["value"]]}}})
    stages.append({"$limit": limit + 1})
    found = await db.coll(entity_name).aggregate(stages).to_list(length=limit + 1)
    has_more = len(found) > limit
    found = found[:limit]
    return {
        "items": [_wire(group["_id"]) for group in found],
        "next_cursor": cursor.issue(read, {"value": found[-1]["_id"]}) if has_more else None,
        "has_more": has_more,
    }
