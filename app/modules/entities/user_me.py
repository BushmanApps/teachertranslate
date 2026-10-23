"""GET/PUT /api/apps/:appId/entities/User/me — current user endpoints."""

from __future__ import annotations

from fastapi import Body, Depends

from app.config import Settings
from app.core.models import users as users_models
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings
from app.modules.auth.helpers import user_doc_to_userresource_input
from app.modules.entities import services


async def get_me(
    app_id: str,
    ctx: AuthedContext = Depends(get_authed_context),
):
    doc = await services.get_me(ctx)
    return users_models.UserResource(**user_doc_to_userresource_input(doc)).model_dump(mode="json", by_alias=True, exclude_unset=True)


async def update_me(
    app_id: str,
    body: dict = Body(...),
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    doc = await services.update_me(app_id, body, ctx, settings)
    return users_models.UserResource(**user_doc_to_userresource_input(doc)).model_dump(mode="json", by_alias=True, exclude_unset=True)
