"""POST /api/apps/:appId/auth/change-password

NOT caller-authorized — anyone who knows the user_id and current password
can change it, even anonymously. This matches production behavior exactly.
"""

from __future__ import annotations

from bson import ObjectId
from fastapi import Depends

from app.config import Settings
from app.core import db
from app.core.errors import AppHTTPException
from app.core.models import ChangePasswordBody
from app.core.models import users as users_models
from app.deps import get_settings
from app.core.responses import utcnow_naive
from app.modules.auth.helpers import (
    find_private_user,
    hash_password,
    user_doc_to_userresource_input,
    verify_password,
)


async def change_password(
    app_id: str,
    body: ChangePasswordBody,
    settings: Settings = Depends(get_settings),
):
    # An id that does not parse and an id nobody has answer the same 404
    # (re-measured 2026-09-28; until 2026-09 both leaked as a 500
    # ObjectNotFoundError).
    try:
        oid = ObjectId(body.user_id)
    except Exception:
        raise AppHTTPException(404, "User not found")

    user = await db.coll("User").find_one({"_id": oid, "app_id": settings.APP_ID})
    if not user:
        raise AppHTTPException(404, "User not found")

    email = user["email"]
    private = await find_private_user({"email": email, "app_id": settings.APP_ID})
    if not private or not private.get("hashed_password"):
        raise AppHTTPException(400, "Current password is incorrect")

    if not verify_password(body.current_password, private["hashed_password"]):
        raise AppHTTPException(400, "Current password is incorrect")

    new_hash = hash_password(body.new_password)

    await db.coll("_private_users").update_one(
        {"email": email, "app_id": settings.APP_ID},
        {"$set": {"hashed_password": new_hash}},
    )

    # Base44 bumps User.updated_date on password change (probed 2026-05-21
    # session 4 — M-004). Stamp + reflect in response so callers see fresh
    # `updated_date` matching Base44 wire byte-for-byte. Naive datetime to
    # match Base44 (their wire emits "...939754" with no Z suffix).
    now = utcnow_naive()
    await db.coll("User").update_one(
        {"_id": user["_id"]},
        {"$set": {"updated_date": now}},
    )
    user["updated_date"] = now

    return users_models.UserResource(
        **user_doc_to_userresource_input(user),
    ).model_dump(mode="json", by_alias=True, exclude_unset=True)
