"""PUT /api/apps/:appId/entities/:entityName/:id — update single entity."""

from __future__ import annotations

from fastapi import Body, Depends

from app.config import Settings
from app.core.models import users as users_models
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings
from app.modules.auth.helpers import user_doc_to_userresource_input
from app.modules.entities import services
from app.modules.entities.helpers import created_by_hidden


async def update_entity(
    app_id: str,
    entity_name: str,
    id: str,
    body: dict = Body(...),
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    doc = await services.update(app_id, entity_name, id, body, ctx, settings)

    if entity_name == "User":
        return users_models.UserResource(**user_doc_to_userresource_input(doc)).model_dump(mode="json", by_alias=True, exclude_unset=True)

    hide = created_by_hidden(ctx.app_settings)
    return services.serialize_for_rest(entity_name, doc, hide_created_by=hide)
