"""Web Sign in with Apple routes."""

from __future__ import annotations

import json
import logging
import time

import jwt
from fastapi import Depends, Query, Request
from fastapi.responses import RedirectResponse
from jwt import PyJWKClient

from app.config import Settings
from app.core import addresses
from app.core.errors import AppHTTPException
from app.core.oauth import ProviderConfig, build_authorize_url, exchange_code_for_token
from app.deps import get_settings
from app.modules.auth.google_oauth import _url_encode, is_mobile_shell, oauth_start_response
from app.modules.auth.oauth_post_login import post_oauth_login

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_AUTHORIZE_URL = f"{APPLE_ISSUER}/auth/authorize"
APPLE_TOKEN_URL = f"{APPLE_ISSUER}/auth/token"
APPLE_KEYS_URL = f"{APPLE_ISSUER}/auth/keys"

logger = logging.getLogger(__name__)
_apple_keys = PyJWKClient(APPLE_KEYS_URL, cache_keys=True, lifespan=3600)


def _client_secret(settings: Settings) -> str:
    client_id = settings.APPLE_WEB_CLIENT_ID
    team_id = settings.APPLE_WEB_TEAM_ID
    key_id = settings.APPLE_WEB_KEY_ID
    private_key = (settings.APPLE_WEB_PRIVATE_KEY_P8 or "").replace("\\n", "\n").strip()
    if not client_id or not team_id or not key_id or not private_key:
        raise AppHTTPException(500, "Apple login is not configured")
    now = int(time.time())
    return jwt.encode(
        {"iss": team_id, "iat": now, "exp": now + 15552000, "aud": APPLE_ISSUER, "sub": client_id},
        private_key,
        algorithm="ES256",
        headers={"kid": key_id},
    )


async def _callback_url() -> str:
    return f"{await addresses.canonical_base_url()}/api/apps/auth/apple/callback"


def _provider_config(settings: Settings, callback_url: str) -> ProviderConfig:
    client_id = settings.APPLE_WEB_CLIENT_ID
    if not client_id:
        raise AppHTTPException(500, "Apple login is not configured")
    return ProviderConfig(
        client_id=client_id,
        client_secret=_client_secret(settings),
        redirect_uri=callback_url,
        scope="name email",
        authorization_endpoint=APPLE_AUTHORIZE_URL,
        token_endpoint=APPLE_TOKEN_URL,
        token_request_auth_method="body",
        authorize_params={"response_mode": "form_post"},
    )


def _claims(identity_token: str, client_id: str) -> dict:
    key = _apple_keys.get_signing_key_from_jwt(identity_token)
    return jwt.decode(identity_token, key.key, algorithms=["RS256"], audience=client_id, issuer=APPLE_ISSUER)


async def apple_login(
    request: Request,
    app_id: str | None = Query(None),
    from_url: str | None = Query(None),
    settings: Settings = Depends(get_settings),
):
    if not app_id:
        raise AppHTTPException(400, "app_id is required")
    if is_mobile_shell(request):
        from_url = f"eb44-{settings.APP_ID}://oauth"

    callback_url = await _callback_url()
    config = _provider_config(settings, callback_url)
    state = json.dumps({
        "domain": await addresses.arrival_base_url(request),
        "from_url": from_url,
        "app_id": app_id,
    })
    return oauth_start_response(request, build_authorize_url(config, state=state), status_code=302)


async def apple_callback(
    request: Request,
    state: str | None = Query(None),
    code: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    settings: Settings = Depends(get_settings),
):
    form = await request.form() if request.method == "POST" else {}
    state = state or form.get("state")
    code = code or form.get("code")
    error = error or form.get("error")
    error_description = error_description or form.get("error_description")
    if not state:
        raise AppHTTPException(400, "app_id is required")
    try:
        state_data = json.loads(state)
    except (json.JSONDecodeError, TypeError):
        raise AppHTTPException(400, "app_id is required")
    if not state_data.get("app_id"):
        raise AppHTTPException(400, "app_id is required")
    if error:
        return RedirectResponse(
            url="/api/apps/auth/auth-error?error_type=OAuthError&error_message="
            + _url_encode(f"{error}: {error_description or ''}"),
            status_code=307,
        )
    if not code:
        return RedirectResponse(
            url="/api/apps/auth/auth-error?error_type=OAuthError&error_message="
            + _url_encode("Apple did not return an authorization code"),
            status_code=307,
        )

    try:
        callback_url = await _callback_url()
        config = _provider_config(settings, callback_url)
        token = await exchange_code_for_token(config, code)
        claims = _claims(token["id_token"], config.client_id)
        email = (claims.get("email") or "").lower().strip()
        if not email:
            raise ValueError("Apple did not provide an email address")
        user_payload = form.get("user")
        name = ""
        if user_payload:
            user = json.loads(user_payload)
            name_data = user.get("name") or {}
            name = " ".join(part for part in (name_data.get("firstName"), name_data.get("lastName")) if part)
    except Exception as exc:
        logger.warning("Apple web login failed: %s", exc)
        return RedirectResponse(
            url="/api/apps/auth/auth-error?error_type=OAuthError&error_message="
            + _url_encode("Failed to complete Apple authentication"),
            status_code=307,
        )

    return await post_oauth_login(
        email=email,
        name=name,
        provider="apple",
        oauth_tokens=token,
        from_url=state_data.get("from_url"),
        fallback_base_url=await addresses.arrival_base_url(request),
        settings=settings,
    )
