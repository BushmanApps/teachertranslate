"""GET /api/apps/:appId/entities/:entityName/:id — get single entity."""

from __future__ import annotations

from fastapi import Depends

from app.core.models import users as users_models
from app.core.security import fls
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.modules.auth.helpers import user_doc_to_userresource_input
from app.modules.entities import services
from app.modules.entities.helpers import created_by_hidden


async def get_entity(
    app_id: str,
    entity_name: str,
    id: str,
    ctx: AuthedContext = Depends(get_authed_context),
):
    doc = await services.get(app_id, entity_name, id, ctx)

    if entity_name == "User":
        return users_models.UserResource(**user_doc_to_userresource_input(doc)).model_dump(mode="json", by_alias=True, exclude_unset=True)

    hide = created_by_hidden(ctx.app_settings)
    row = services.serialize_for_rest(entity_name, doc, hide_created_by=hide)
    rows = fls.mask_read_fields(ctx, entity_name, [row])
    return rows[0]
