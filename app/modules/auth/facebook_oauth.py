"""Facebook OAuth login routes."""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.core import addresses
from app.core.errors import AppHTTPException
from app.core.oauth import ProviderConfig, build_authorize_url, exchange_code_for_token
from app.deps import get_settings
from app.modules.auth.google_oauth import _url_encode, is_mobile_shell, oauth_start_response
from app.modules.auth.oauth_post_login import post_oauth_login

FACEBOOK_AUTHORIZE_URL = "https://www.facebook.com/dialog/oauth"
FACEBOOK_TOKEN_URL = "https://graph.facebook.com/oauth/access_token"
FACEBOOK_PROFILE_URL = "https://graph.facebook.com/me"

logger = logging.getLogger(__name__)


def _provider_config(settings: Settings, callback_url: str) -> ProviderConfig:
    if not settings.FACEBOOK_CLIENT_ID or not settings.FACEBOOK_CLIENT_SECRET:
        raise AppHTTPException(500, "Facebook login is not configured")
    return ProviderConfig(
        client_id=settings.FACEBOOK_CLIENT_ID,
        client_secret=settings.FACEBOOK_CLIENT_SECRET,
        redirect_uri=callback_url,
        scope="email,public_profile",
        scope_separator=",",
        authorization_endpoint=FACEBOOK_AUTHORIZE_URL,
        token_endpoint=FACEBOOK_TOKEN_URL,
        token_request_auth_method="body",
    )


async def _callback_url() -> str:
    return f"{await addresses.canonical_base_url()}/api/apps/auth/facebook/callback"


async def facebook_login(
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


async def facebook_callback(
    request: Request,
    state: str | None = Query(None),
    code: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    settings: Settings = Depends(get_settings),
):
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
            + _url_encode("Facebook did not return an authorization code"),
            status_code=307,
        )

    try:
        callback_url = await _callback_url()
        config = _provider_config(settings, callback_url)
        token = await exchange_code_for_token(config, code)
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                FACEBOOK_PROFILE_URL,
                params={"fields": "id,name,email", "access_token": token["access_token"]},
            )
            response.raise_for_status()
            profile = response.json()
        email = (profile.get("email") or "").lower().strip()
        if not email:
            raise ValueError("Facebook did not provide an email address")
    except Exception as exc:
        logger.warning("Facebook login failed: %s", exc)
        return RedirectResponse(
            url="/api/apps/auth/auth-error?error_type=OAuthError&error_message="
            + _url_encode("Failed to complete Facebook authentication"),
            status_code=307,
        )

    return await post_oauth_login(
        email=email,
        name=profile.get("name") or "",
        provider="facebook",
        oauth_tokens=token,
        from_url=state_data.get("from_url"),
        fallback_base_url=await addresses.arrival_base_url(request),
        settings=settings,
    )
