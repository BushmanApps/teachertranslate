"""PATCH /api/apps/:appId/entities/:entityName/update-many — update many entities.

Body validation is delegated to a Pydantic body model so FastAPI emits the
same 422 envelopes Base44 emits — multi-error reporting (both `query` and
`data` listed when both are missing), the `input` field carrying the partial
body, and `dict_type` / `model_attributes_type` / `json_invalid` type tags
for the matching invalid-shape cases. Probed against Base44 prod 2026-05-20.
"""

from __future__ import annotations

from fastapi import Depends
from pydantic import BaseModel

from app.core.security.pipeline import AuthedContext, get_authed_context
from app.modules.entities import services


class UpdateManyBody(BaseModel):
    query: dict
    data: dict


async def update_many(
    app_id: str,
    entity_name: str,
    body: UpdateManyBody,
    ctx: AuthedContext = Depends(get_authed_context),
):
    return await services.update_many(app_id, entity_name, body.query, body.data, ctx)
