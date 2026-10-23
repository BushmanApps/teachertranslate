"""POST /api/apps/:appId/auth/reset-password-request"""

from __future__ import annotations

import logging

from fastapi import Depends, Request

from app.config import Settings
from app.core import db
from app.core import addresses
from app.core.models import ResetPasswordRequestBody, ResetPasswordRequestResponse
from app.core.providers.email.templates import reset_password_email_html
from app.deps import get_app_settings, get_email_provider, get_settings
from app.modules.auth.helpers import (
    find_private_user,
    find_user_by_email,
    generate_reset_token,
)

logger = logging.getLogger(__name__)


async def reset_password_request(
    request: Request,
    app_id: str,
    body: ResetPasswordRequestBody,
    settings: Settings = Depends(get_settings),
    email_provider=Depends(get_email_provider),
    app_settings: dict = Depends(get_app_settings),
):
    email = body.email.lower().strip()
    app_name = app_settings.get("name", settings.APP_ID)

    generic_response = ResetPasswordRequestResponse(
        message="If an account exists with this email, you will receive a password reset link.",
    ).model_dump(mode="json")

    user = await find_user_by_email(email, settings.APP_ID)
    if not user:
        return generic_response

    private = await find_private_user({"email": email, "app_id": settings.APP_ID})
    if not private:
        return generic_response

    token = generate_reset_token()

    await db.coll("_private_users").update_one(
        {"email": email, "app_id": settings.APP_ID},
        {"$set": {"hashed_reset_token": token}},
    )

    if email_provider:
        reset_url = f"{await addresses.arrival_base_url(request)}/reset-password?token={token}"
        try:
            await email_provider.send(
                to=email,
                subject=f"Reset your password for {app_name}",
                html=reset_password_email_html(app_name, email, reset_url),
                from_name=app_name,
            )
        except Exception as exc:
            # The response stays generic (no account enumeration); the failure
            # is the operator's to see, never the caller's.
            logger.warning("reset-password email to %s failed: %s", email, exc)

    return generic_response
