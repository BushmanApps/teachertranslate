"""POST /api/apps/:appId/auth/reset-password"""

from __future__ import annotations

from fastapi import Depends

from app.config import Settings
from app.core import db
from app.core.errors import ObjectNotFoundError
from app.core.models import ResetPasswordBody
from app.core.models import users as users_models

from app.deps import get_settings
from app.modules.auth.helpers import (
    find_private_user,
    hash_password,
    user_doc_to_userresource_input,
)


async def reset_password(
    app_id: str,
    body: ResetPasswordBody,
    settings: Settings = Depends(get_settings),
):
    private = await find_private_user({
        "hashed_reset_token": body.reset_token,
        "app_id": settings.APP_ID,
    })
    if not private:
        raise ObjectNotFoundError({
            "hashed_reset_token": body.reset_token,
            "app_id": settings.APP_ID,
        })

    email = private["email"]
    new_hash = hash_password(body.new_password)

    await db.coll("_private_users").update_one(
        {"email": email, "app_id": settings.APP_ID},
        {"$set": {
            "hashed_password": new_hash,
            "hashed_reset_token": None,
        }},
    )

    user = await db.coll("User").find_one({"email": email, "app_id": settings.APP_ID})
    if not user:
        raise ObjectNotFoundError({"email": email, "app_id": settings.APP_ID})

    return users_models.UserResource(
        **user_doc_to_userresource_input(user),
    ).model_dump(mode="json", by_alias=True, exclude_unset=True)
