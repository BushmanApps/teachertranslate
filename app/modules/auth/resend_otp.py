"""POST /api/apps/:appId/auth/resend-otp"""

from __future__ import annotations

from fastapi import Depends

from app.config import Settings
from app.core import db
from app.core.errors import AppHTTPException
from app.core.models import ResendOTPRequest, ResendOTPResponse
from app.core.providers.email.templates import otp_email_html
from app.deps import get_app_settings, get_email_provider, get_settings
from app.modules.auth.helpers import (
    OTP_EXPIRY_MINUTES,
    find_user_by_email,
    generate_otp,
    otp_expiry_time,
)


async def resend_otp(
    app_id: str,
    body: ResendOTPRequest,
    settings: Settings = Depends(get_settings),
    email_provider=Depends(get_email_provider),
    app_settings: dict = Depends(get_app_settings),
):
    email = body.email.lower().strip()
    app_name = app_settings.get("name", settings.APP_ID)

    user = await find_user_by_email(email, settings.APP_ID)
    if not user:
        # Re-measured 2026-09-28 (until 2026-09 a 500 ObjectNotFoundError).
        raise AppHTTPException(400, "User not found")

    if user.get("is_verified"):
        raise AppHTTPException(400, "User is already verified")

    otp = generate_otp()
    otp_exp = otp_expiry_time()

    await db.coll("_private_users").update_one(
        {"email": email, "app_id": settings.APP_ID},
        {"$set": {"otp_code": otp, "otp_expires_at": otp_exp, "otp_attempts": 0}},
    )

    if email_provider:
        try:
            await email_provider.send(
                to=email,
                subject=f"Verify your email for {app_name}",
                html=otp_email_html(app_name, email, otp, OTP_EXPIRY_MINUTES),
                from_name=app_name,
            )
        except Exception:
            pass

    return ResendOTPResponse(
        message="New verification code sent to your email.",
        otp_expires_in_minutes=OTP_EXPIRY_MINUTES,
    ).model_dump(mode="json")
