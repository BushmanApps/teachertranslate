"""POST /api/apps/:appId/entities/:entityName — create single entity."""

from __future__ import annotations

from fastapi import Body, Depends

from app.config import Settings
from app.core.models import users as users_models
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings
from app.modules.auth.helpers import user_doc_to_userresource_input
from app.modules.entities import services
from app.modules.entities.helpers import created_by_hidden


async def create_entity(
    app_id: str,
    entity_name: str,
    body: dict = Body(...),
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    doc = await services.create(app_id, entity_name, body, ctx, settings)

    if entity_name == "User":
        # Phantom user — POST /entities/User never persists (probed 2026-05-22:
        # zero anonymous-created rows in B44 User collection despite repeated
        # anon POSTs). `build_phantom_user` constructs the dict in B44's exact
        # wire shape (9 fixed fields: email, full_name, role, id, created_date,
        # updated_date, created_by_id, created_by, is_sample), so we return it
        # verbatim — no UserResource wrapping (which would put declared `role`
        # first, breaking the email/full_name/role ordering B44 emits).
        if "_id" not in doc:
            return doc
        return users_models.UserResource(**user_doc_to_userresource_input(doc)).model_dump(mode="json", by_alias=True, exclude_unset=True)

    hide = created_by_hidden(ctx.app_settings)
    return services.serialize_for_rest(entity_name, doc, hide_created_by=hide)
