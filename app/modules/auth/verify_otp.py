"""POST /api/apps/:appId/auth/verify-otp"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Request

from app.config import Settings
from app.core import db
from app.core.errors import AppHTTPException, ObjectNotFoundError
from app.core.models import VerifyOTPRequest, VerifyOTPResponse
from app.core.responses import utcnow_naive
from app.core.security.tokens import encode_app_token
from app.deps import get_settings
from app.modules.auth.helpers import (
    OTP_MAX_ATTEMPTS,
    find_private_user,
    find_user_by_email,
    get_country_code_from_request,
)


async def verify_otp(
    app_id: str,
    body: VerifyOTPRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    email = body.email.lower().strip()

    user = await find_user_by_email(email, settings.APP_ID)
    if not user:
        raise ObjectNotFoundError({"email": email, "app_id": settings.APP_ID})

    if user.get("is_verified"):
        raise AppHTTPException(400, "User is already verified")

    private = await find_private_user({"email": email, "app_id": settings.APP_ID})
    if not private:
        raise ObjectNotFoundError({"email": email, "app_id": settings.APP_ID})

    stored_otp = private.get("otp_code")
    otp_attempts = private.get("otp_attempts", 0)
    otp_expires_at = private.get("otp_expires_at")

    if otp_expires_at:
        try:
            expiry = datetime.strptime(otp_expires_at, "%Y-%m-%dT%H:%M:%S.%f").replace(
                tzinfo=timezone.utc
            )
            if datetime.now(timezone.utc) > expiry:
                # Base44 distinguishes expired-OTP wording from max-attempts
                # wording (probed 2026-05-21 session 4 — M-010). Expired
                # message says "Verification code has expired. Please request
                # a new one."; max-attempts keeps the "Too many failed attempts"
                # message below.
                raise AppHTTPException(
                    400,
                    "Verification code has expired. Please request a new one.",
                )
        except ValueError:
            pass

    if otp_attempts >= OTP_MAX_ATTEMPTS:
        raise AppHTTPException(
            400,
            "Too many failed attempts. Please request a new verification code.",
        )

    if stored_otp != body.otp_code:
        new_attempts = otp_attempts + 1
        await db.coll("_private_users").update_one(
            {"email": email, "app_id": settings.APP_ID},
            {"$set": {"otp_attempts": new_attempts}},
        )
        remaining = OTP_MAX_ATTEMPTS - new_attempts
        if remaining <= 0:
            raise AppHTTPException(
                400,
                "Too many failed attempts. Please request a new verification code.",
            )
        raise AppHTTPException(
            400,
            f"Invalid verification code. {remaining} attempts remaining.",
        )

    user_id = str(user["_id"])

    await db.coll("User").update_one(
        {"_id": user["_id"]},
        {"$set": {"is_verified": True, "updated_date": utcnow_naive()}},
    )

    await db.coll("_private_users").update_one(
        {"email": email, "app_id": settings.APP_ID},
        {"$set": {"otp_code": None, "otp_expires_at": None, "otp_attempts": 0}},
    )

    # Workflows: `signup` fires HERE, at OTP verification — when the user
    # actually exists — not at register (measured: register → 0 runs,
    # verify → 1, login → 2; workflows H §14.9).
    from app.core.workflows.dispatch import dispatch_auth
    try:
        await dispatch_auth("signup", {**user, "is_verified": True})
    except Exception:
        pass  # a workflow must never fail the auth path

    access_token = encode_app_token(email, settings)
    country_code = get_country_code_from_request(request)

    return VerifyOTPResponse(
        id=user_id,
        success=True,
        access_token=access_token,
        message="Email verified successfully. You are now logged in.",
        country_code=country_code,
    ).model_dump(mode="json")
