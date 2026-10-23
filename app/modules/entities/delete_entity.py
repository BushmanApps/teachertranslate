"""DELETE /api/apps/:appId/entities/:entityName/:id — delete single entity."""

from __future__ import annotations

from fastapi import Depends

from app.config import Settings
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings
from app.modules.entities import services


async def delete_entity(
    app_id: str,
    entity_name: str,
    id: str,
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    await services.delete(app_id, entity_name, id, ctx, settings)
    return {"success": True}
