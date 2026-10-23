"""POST /api/apps/:appId/auth/login"""

from __future__ import annotations

import httpx
from fastapi import Depends, Request

from app.config import Settings
from app.core import db
from app.core.errors import AppHTTPException
from app.core.models import LoginRequest, LoginResponse
from app.core.models import users as users_models
from app.core.security.tokens import encode_app_token
from app.deps import get_settings
from app.modules.auth.helpers import (
    find_private_user,
    find_user_by_email,
    get_country_code_from_request,
    hash_password,
    user_doc_to_userresource_input,
    verify_password,
)


async def login(
    app_id: str,
    body: LoginRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    email = body.email.lower().strip()
    password = body.password

    # Bcrypt rejects passwords longer than 72 bytes with a ValueError. Base44's
    # login path silently absorbs this and emits the standard
    # "Invalid email or password" 400 (privacy-preserving — over-limit is
    # indistinguishable from just-wrong-credentials). Pre-check here so the
    # later verify_password() never sees an over-limit input. (Register, reset,
    # change-password paths intentionally do NOT pre-check — prod has the same
    # bug there and we replicate it; see Owner B finding B-1.)
    if len(password.encode("utf-8")) > 72:
        raise AppHTTPException(400, "Invalid email or password")

    user = await find_user_by_email(email, settings.APP_ID)
    if not user:
        raise AppHTTPException(400, "Invalid email or password")

    private = await find_private_user({"email": email, "app_id": settings.APP_ID})
    if not private:
        raise AppHTTPException(400, "Invalid email or password")

    if not private.get("hashed_password"):
        if not await _try_forward_to_base44(email, password, settings):
            raise AppHTTPException(400, "Invalid email or password")
        private = await find_private_user({"email": email, "app_id": settings.APP_ID})

    if not verify_password(password, private["hashed_password"]):
        raise AppHTTPException(400, "Invalid email or password")

    if not user.get("is_verified"):
        raise AppHTTPException(
            400,
            "Please verify your email before logging in. Check your email for the verification code.",
        )

    # Workflows: each successful login fires `login` (H §14.9).
    from app.core.workflows.dispatch import dispatch_auth
    try:
        await dispatch_auth("login", user)
    except Exception:
        pass  # a workflow must never fail the auth path

    access_token = encode_app_token(email, settings)
    country_code = get_country_code_from_request(request)

    user_dict = users_models.UserResource(
        **user_doc_to_userresource_input(user),
    ).model_dump(mode="json", by_alias=True, exclude_unset=True)

    return LoginResponse(
        user=user_dict,
        success=True,
        access_token=access_token,
        country_code=country_code,
    ).model_dump(mode="json")


# Built-in User fields we mirror from Base44's `/auth/login` response on the
# first forwarded login. These cover the canonical 14 minus `id` (never
# changes), `email` (the lookup key), `app_id` (per-deploy constant), and
# `created_date` (immutable). The rest can drift between Base44 and our copy
# during the migration's eventual-consistency window — see
# research/testing-server/auth/findings/0002-stale-is-verified-on-migration.md.
_MIRRORED_BUILTIN_USER_FIELDS = frozenset({
    "role", "_app_role", "full_name",
    "disabled", "disabled_reason",
    "is_verified", "force_password_reset",
    "is_service", "collaborator_role",
    "updated_date",
})


async def _try_forward_to_base44(email: str, password: str, settings: Settings) -> bool:
    """Forward credentials to Base44 for migrated users with no local password.

    On success: cache the bcrypt hash locally AND mirror Base44's
    authoritative built-in User fields (`is_verified`, `_app_role`, etc.)
    back onto our local row. The mirror exists because the migrator can
    capture stale User docs from Base44 — e.g. a verify-otp written on
    Base44 a few seconds before the migrator's entity GET may not be
    reflected in that read. A user in that state can't log in here
    (`is_verified: false` on our copy) until they either (a) re-verify
    via /resend-otp + /verify-otp, or (b) get their state reconciled —
    which is what this mirror does. Subsequent logins don't forward
    (hashed_password is now set), so the mirror only fires once.

    Custom `additional_user_data_schema` fields are mirrored too, on
    the conservative assumption that Base44 also might know newer
    values than our extract. After this first sync, the local row is
    authoritative.
    """
    original_app_id = settings.BASE44_ORIGINAL_APP_ID
    if not original_app_id or not settings.BASE44_FALLBACK_URL:
        return False

    url = f"{settings.BASE44_FALLBACK_URL}/api/apps/{original_app_id}/auth/login"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"email": email, "password": password})
    except Exception:
        return False

    if resp.status_code != 200:
        return False

    await db.coll("_private_users").update_one(
        {"email": email, "app_id": settings.APP_ID},
        {"$set": {"hashed_password": hash_password(password)}},
    )

    # Best-effort mirror — never fail the login because the response shape
    # wasn't what we expected. Base44 contract today: `{"user": {…}, "success",
    # "access_token", "country_code"}`. If the shape ever changes, the cached
    # hash still works and we degrade to the old behavior (stale local fields).
    try:
        body = resp.json()
        base44_user = body.get("user") if isinstance(body, dict) else None
        if isinstance(base44_user, dict):
            await _mirror_base44_user(base44_user, settings.APP_ID)
    except Exception:
        pass

    return True


async def _mirror_base44_user(base44_user: dict, app_id: str) -> None:
    """Copy authoritative built-in + custom user fields from Base44's login
    response onto our local User row. See `_MIRRORED_BUILTIN_USER_FIELDS`.

    Custom-schema fields are mirrored when present on the response — Base44
    surfaces them top-level on the normalized object (probe-verified). We
    fetch the per-app custom-field set from `_app_settings.
    additional_user_data_schema.properties` at mirror time so we never write a
    field that isn't part of the running app's User schema.
    """
    user_email = base44_user.get("email")
    if not isinstance(user_email, str) or not user_email:
        return

    # Built-ins
    update_set: dict = {}
    for key in _MIRRORED_BUILTIN_USER_FIELDS:
        if key in base44_user:
            update_set[key] = base44_user[key]

    # Custom schema fields (top-level on Base44's normalized response)
    app_settings = await db.app_settings()
    aux = app_settings.get("additional_user_data_schema") or {}
    custom_field_names = set((aux.get("properties") or {}).keys())
    for key in custom_field_names:
        if key in base44_user:
            update_set[key] = base44_user[key]

    if not update_set:
        return

    await db.coll("User").update_one(
        {"email": user_email.lower().strip(), "app_id": app_id},
        {"$set": update_set},
    )
