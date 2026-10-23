"""POST /api/apps/:appId/auth/register"""

from __future__ import annotations

from fastapi import Depends, Request
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.config import Settings
from app.core import db
from app.core.errors import AppHTTPException, WrappedValidationError
from app.core.models import RegisterRequest, RegisterResponse

# Built once and reused; cheaper than re-constructing per request.
_EMAIL_VALIDATOR = TypeAdapter(EmailStr)
from app.core.providers.email.templates import otp_email_html
from app.deps import get_app_settings, get_email_provider, get_settings
from app.modules.auth.helpers import (
    OTP_EXPIRY_MINUTES,
    build_new_user_doc,
    build_private_user_doc,
    derive_full_name,
    find_user_by_email,
    generate_otp,
    get_app_visibility_mode,
    get_country_code_from_request,
    hash_password,
    is_user_invited,
    otp_expiry_time,
)


async def register(
    app_id: str,
    body: RegisterRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    email_provider=Depends(get_email_provider),
    app_settings: dict = Depends(get_app_settings),
):
    email = body.email.lower().strip()
    password = body.password

    # Password-length first, then email format. Order matters: when both are
    # invalid, prod emits the 400 password-length error before the 422 email
    # validation. Swapped to match (Owner B finding B-2).
    if len(password) < 8:
        raise AppHTTPException(400, "Password must be at least 8 characters long")

    # Manual email-format validation so failure produces envelope #2
    # (WrappedValidationError) instead of envelope #1. Base44 wire-verified:
    # bad email on register emits `{"error_type":"ValidationError",
    # "message":"Error in field email: ...","detail":"[{...}]",...}`. Missing
    # `email` field is already caught by FastAPI's auto-Pydantic before this
    # runs and produces envelope #1, also matching Base44.
    try:
        _EMAIL_VALIDATOR.validate_python(email)
    except ValidationError as e:
        # Prepend "email" to each error's `loc` so the message renders as
        # "Error in field email: ..." matching Base44.
        errors = [{**err, "loc": ("email",) + tuple(err["loc"])} for err in e.errors()]
        raise WrappedValidationError(errors)

    visibility_mode = await get_app_visibility_mode()
    invited = await is_user_invited(email, settings.APP_ID)

    is_restricted = visibility_mode in ("private_with_login", "workspace_with_login")

    if is_restricted and not invited:
        return await _access_request_branch(email, settings.APP_ID, app_settings, email_provider)

    return await _create_user_branch(
        email, password, settings, email_provider, request, app_settings,
    )


async def _access_request_branch(
    email: str,
    app_id: str,
    app_settings: dict,
    email_provider,
) -> dict:
    owner_email = app_settings.get("created_by")
    app_name = app_settings.get("name") or app_id

    if owner_email and email_provider:
        try:
            await email_provider.send(
                to=owner_email,
                subject=f"Access request for {app_name}",
                text=(
                    f"{email} requested access to {app_name}.\n\n"
                    f"To grant access, invite them through the app's invite flow."
                ),
                html=(
                    f"<p><strong>{email}</strong> requested access to "
                    f"<strong>{app_name}</strong>.</p>"
                    f"<p>To grant access, invite them through the app's invite flow.</p>"
                ),
                from_name=app_name,
            )
        except Exception:
            pass

    return {
        "success": True,
        "access_request_created": True,
        "status": "pending",
        "message": "Access requested! You'll receive an email when the app admin approves your request.",
    }


async def _create_user_branch(
    email: str,
    password: str,
    settings: Settings,
    email_provider,
    request: Request,
    app_settings: dict,
) -> dict:
    app_id = settings.APP_ID
    app_name = app_settings.get("name", app_id)
    existing = await find_user_by_email(email, app_id)

    if existing:
        if existing.get("is_verified"):
            raise AppHTTPException(400, "A user with this email already exists")

        user_id = str(existing["_id"])
        otp = generate_otp()
        otp_exp = otp_expiry_time()

        # Register-replay on an EXISTING UNVERIFIED user: refresh the OTP
        # only. Base44 does NOT overwrite the password on register-replay
        # (probed 2026-05-22 against AuthRolesLab Daniel-side — register
        # with `FirstPw1!`, register again same email with `SecondPw1!`,
        # then login: `FirstPw1!` → 400 "verify your email" wording
        # (password matched, verify gate failed); `SecondPw1!` → 400
        # "Invalid email or password" (password mismatch). The original
        # password is authoritative for the unverified account; the
        # second register just resends OTP).
        await db.coll("_private_users").update_one(
            {"email": email, "app_id": app_id},
            {"$set": {
                "otp_code": otp,
                "otp_expires_at": otp_exp,
                "otp_attempts": 0,
            }},
        )

        await _send_otp_email(email_provider, email, otp, app_name)

        country_code = get_country_code_from_request(request)
        return RegisterResponse(
            id=user_id,
            message="Registration successful. Please check your email for the verification code.",
            otp_expires_in_minutes=OTP_EXPIRY_MINUTES,
            country_code=country_code,
        ).model_dump(mode="json")

    full_name = derive_full_name(email)
    otp = generate_otp()
    otp_exp = otp_expiry_time()

    user_doc = build_new_user_doc(email, full_name, app_id)
    user_id = user_doc["_id"]
    await db.coll("User").insert_one(user_doc)

    private_doc = build_private_user_doc(email, app_id, str(user_id), hash_password(password))
    private_doc["otp_code"] = otp
    private_doc["otp_expires_at"] = otp_exp
    await db.coll("_private_users").insert_one(private_doc)

    await _send_otp_email(email_provider, email, otp, app_name)

    country_code = get_country_code_from_request(request)
    return RegisterResponse(
        id=str(user_id),
        message="Registration successful. Please check your email for the verification code.",
        otp_expires_in_minutes=OTP_EXPIRY_MINUTES,
        country_code=country_code,
    ).model_dump(mode="json")


async def _send_otp_email(email_provider, email: str, otp: str, app_name: str):
    if not email_provider:
        return
    try:
        await email_provider.send(
            to=email,
            subject=f"Verify your email for {app_name}",
            html=otp_email_html(app_name, email, otp, OTP_EXPIRY_MINUTES),
            from_name=app_name,
        )
    except Exception:
        pass
