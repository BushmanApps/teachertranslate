"""GET /api/apps/:appId/entities/:entityName/count — how many rows a filter
matches, among the rows the caller may read.

`count(query)` of @base44/sdk 0.8.49. Base44's contract (measured 2026-09-28/29):
`{"count": n}`; `q` is the list's filter, refused in the count's own words;
every other parameter — `limit`, `skip`, `sort`, a bare field — is ignored.

The app's USERS are counted for whoever may list them, and counted whole: a
`q` on `User/count` is not read at all (a filter, a refused operator and a
`q` that is no JSON all answer the number of users).
"""

from __future__ import annotations

from fastapi import Depends, Request
from pymongo.errors import OperationFailure

from app.core import db
from app.core.security import rls
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.modules.entities import reading, services
from app.modules.entities.helpers import build_mongo_query, resolve_schema, validate_user_query


async def count_entities(
    app_id: str,
    entity_name: str,
    request: Request,
    ctx: AuthedContext = Depends(get_authed_context),
):
    resolve_schema(entity_name)
    if entity_name == "User":
        services.assert_may_read_users(ctx, "count")
        return {"count": await db.coll("User").count_documents({})}
    query = reading.count_filter_of(request.query_params)
    validate_user_query(query)
    match = build_mongo_query(query, rls.filter_for_read(ctx, entity_name))
    try:
        return {"count": await db.coll(entity_name).count_documents(match)}
    except OperationFailure as failure:
        raise reading.refused_by_database(failure) from None
