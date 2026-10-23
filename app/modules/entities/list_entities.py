"""GET /api/apps/:appId/entities/:entityName — list/filter entities."""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.errors import AppError
from app.core.models import users as users_models
from app.core.security import fls
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.modules.auth.helpers import user_doc_to_userresource_input
from app.modules.entities import reading, services
from app.modules.entities.helpers import (
    HARD_LIMIT_CAP,
    created_by_hidden,
    parse_sort,
    resolve_schema,
    validate_user_query,
)


async def list_entities(
    app_id: str,
    entity_name: str,
    request: Request,
    ctx: AuthedContext = Depends(get_authed_context),
):
    """The parameters are read as Base44 reads them today (re-measured
    2026-09-28/29; the May answers were 500s leaking Python's own errors, and
    `limit=0` meant "no limit"): a `q` that is not a JSON object, a `limit` or
    a `skip` that is not a whole number, a `limit` under 1 and a negative
    `skip` are each refused with a 400; `fields` cuts the rows down; every
    parameter that is none of the route's own is a filter on the field of
    that name (modules/entities/reading.py)."""
    schema = resolve_schema(entity_name)
    params = request.query_params

    # In the order Base44 answers two faults at once (probe 09 of the chase).
    user_query = reading.filter_of(params)
    limit = reading.whole_number(params["limit"]) if params.get("limit") is not None else HARD_LIMIT_CAP
    skip = reading.whole_number(params["skip"]) if params.get("skip") is not None else 0
    # Base44 accepts BOTH spellings and treats them identically (measured
    # 2026-08-02; `sort_by` is also the name its own per-app OpenAPI declares);
    # beside a `sort`, `sort_by` is a parameter like any other — a filter.
    sort_spec = parse_sort(reading.sort_of(params))
    bare = reading.bare_filters(schema, params, reading.LIST_PARAMETERS)
    if limit < 1:
        raise AppError(400, "limit must be between 1 and 10000")
    if skip < 0:
        raise AppError(400, "skip must be non-negative")
    limit = min(limit, HARD_LIMIT_CAP)
    if bare:
        validate_user_query(user_query)
        user_query = {**user_query, **bare}
    names = reading.fields_of(params)

    docs = await services.list_(app_id, entity_name, user_query, sort_spec, limit, skip, ctx)

    if entity_name == "User":
        user_cls = users_models.UserResource
        rows = [
            user_cls(**user_doc_to_userresource_input(d)).model_dump(mode="json", by_alias=True, exclude_unset=True)
            for d in docs
        ]
    else:
        hide = created_by_hidden(ctx.app_settings)
        rows = [services.serialize_for_rest(entity_name, d, hide_created_by=hide) for d in docs]
        rows = fls.mask_read_fields(ctx, entity_name, rows)
    return [reading.cut_to(row, names) for row in rows] if names else rows
