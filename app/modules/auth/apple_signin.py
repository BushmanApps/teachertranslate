"""Sign in with Apple, inside the wrapped iPhone app.

Apple's App Store review asks an iPhone app that offers Google or Microsoft
sign-in to offer Sign in with Apple beside them. That is the whole reason
this module exists, and the iPhone app is the only place it runs: the login
page shows the button only when the app itself says it carries it.

  GET  /api/apps/{app_id}/auth/apple/nonce   — a one-time nonce for the request
  POST /api/apps/{app_id}/auth/apple/native  — the identity token Apple handed
                                                the app → the app's own token

Nothing to set up: the app asks Apple directly (the App ID's capability and
the entitlement ride every build), and the identity token is verified here
against Apple's published keys with `aud` = the app's iOS bundle id.

Both routes are ours. Base44's Apple login is a web OAuth flow on Base44's
own Services ID; a migrated app does not carry it (the seed switches
`enable_apple_login` off).
"""

from __future__ import annotations

import asyncio
import logging
import secrets

import jwt
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from jwt import PyJWKClient

from app.config import Settings
from app.core import addresses, db
from app.core.errors import AppHTTPException
from app.core.mobile_identity import ios_bundle_id
from app.core.models import AppleNativeLoginRequest
from app.core.responses import utcnow
from app.deps import get_settings
from app.modules.auth.oauth_post_login import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    complete_oauth_login,
)

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"

FAILURE_MESSAGE = "Apple sign-in failed"

# Apple's signing keys, cached; each token names its key by `kid`.
_apple_keys = PyJWKClient(APPLE_KEYS_URL, cache_keys=True, lifespan=3600)

NONCE_COLLECTION = "_auth_nonces"
NONCE_TTL_SECONDS = 600

logger = logging.getLogger(__name__)


class _AppleFailure(Exception):
    """Internal sentinel — every refusal answers the same 401."""


# ── the verifier ────────────────────────────────────────────────────────────


async def verify_identity_token(token: str, *, audience: str, nonce: str) -> dict:
    """Apple's identity token → its claims, or _AppleFailure.

    Signature against Apple's keys, `iss`, `aud` (the app's iOS bundle id),
    `exp`, and the `nonce` this side issued.
    """
    try:
        key = await asyncio.to_thread(_apple_keys.get_signing_key_from_jwt, token)
        claims = jwt.decode(
            token, key.key, algorithms=["RS256"], audience=audience, issuer=APPLE_ISSUER
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise _AppleFailure(f"identity token rejected: {exc}")
    if claims.get("nonce") != nonce:
        raise _AppleFailure("nonce mismatch")
    if not (claims.get("email") or "").strip():
        raise _AppleFailure("no email in the identity token")
    return claims


# ── the routes ──────────────────────────────────────────────────────────────


async def ensure_nonce_indexes() -> None:
    coll = db.coll(NONCE_COLLECTION)
    await coll.create_index([("nonce", 1)], unique=True)
    await coll.create_index([("created_date", 1)], expireAfterSeconds=NONCE_TTL_SECONDS)


async def apple_nonce(app_id: str, settings: Settings = Depends(get_settings)):
    if app_id != settings.APP_ID:
        raise AppHTTPException(404, "App not found")
    nonce = secrets.token_urlsafe(24)
    await db.coll(NONCE_COLLECTION).insert_one({"nonce": nonce, "created_date": utcnow()})
    return {"nonce": nonce}


async def _consume_nonce(nonce: str) -> bool:
    result = await db.coll(NONCE_COLLECTION).delete_one({"nonce": nonce})
    return result.deleted_count == 1


async def apple_native_login(
    app_id: str,
    body: AppleNativeLoginRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    if app_id != settings.APP_ID:
        raise AppHTTPException(404, "App not found")
    token = (body.identity_token or "").strip()
    nonce = (body.nonce or "").strip()
    if not token or not nonce:
        raise AppHTTPException(400, "identity_token and nonce are required")
    try:
        if not await _consume_nonce(nonce):
            raise _AppleFailure("unknown or used nonce")
        claims = await verify_identity_token(token, audience=ios_bundle_id(settings), nonce=nonce)
    except _AppleFailure as exc:
        logger.warning("Apple native login failed: %s", exc)
        raise AppHTTPException(401, FAILURE_MESSAGE)

    # Apple hands the person's name to the APP, once, on the first sign-in —
    # never inside the token.
    name = " ".join(p for p in [(body.given_name or "").strip(), (body.family_name or "").strip()] if p)
    login = await complete_oauth_login(
        email=claims["email"],
        name=name,
        provider="apple",
        # The identity token is the credential Apple handed the app; there is
        # no separate access token.
        oauth_tokens={"access_token": token, "token_type": "Bearer"},
        fallback_base_url=await addresses.arrival_base_url(request),
        settings=settings,
    )
    if login.access_request_url:
        return JSONResponse({"redirect": login.access_request_url})
    response = JSONResponse({"access_token": login.access_token, "is_new_user": login.is_new_user})
    response.set_cookie(SESSION_COOKIE_NAME, login.access_token, max_age=SESSION_MAX_AGE, path="/", samesite="lax")
    return response
