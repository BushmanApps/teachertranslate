"""SSO accesstoken endpoint.

Vends the OAuth `access_token` stored at login time on `_private_users.login_oauth_tokens`
to service-role callers. Refreshes via the OAuth helper when the stored token is at or
near expiry, and persists a rotated refresh_token if the provider issued one.

Live-API spec: see agent_prompts/REST OF MODULES/sso/IMPLEMENTOR_PROMPT.md.
All non-(401, 404) failures collapse into a single generic 500 with message
"Failed to retrieve SSO access token" — matching Base44 production behavior.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import Depends

from app.config import Settings
from app.core import db
from app.core import addresses
from app.core.errors import AppHTTPException
from app.core.models import SSOAccessTokenResponse
from app.core.oauth import refresh_access_token
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings
from app.modules.auth.google_oauth import (
    build_google_provider_config,
    resolve_google_oauth_credentials,
)
from app.modules.auth.microsoft_oauth import (
    build_microsoft_provider_config,
    resolve_microsoft_oauth,
)
from app.modules.auth.oauth_post_login import (
    build_login_oauth_tokens,
    parse_expires_at,
)

REFRESH_MARGIN_SECONDS = 60
GENERIC_FAILURE_MESSAGE = "Failed to retrieve SSO access token"

logger = logging.getLogger(__name__)


class _SSOFailure(Exception):
    """Internal sentinel — caught and converted to the generic 500 catchall."""


async def get_access_token(
    app_id: str,
    user_id: str,
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    if ctx.token_class != "service_role":
        raise AppHTTPException(
            status_code=401,
            message="Service user not authenticated,to use this method you need to use asServiceRole from base44.asServiceRole",
        )

    try:
        if app_id != settings.APP_ID:
            raise _SSOFailure(f"app_id mismatch: {app_id} != {settings.APP_ID}")

        private = await db.coll("_private_users").find_one(
            {"user_id": user_id, "app_id": settings.APP_ID}
        )
        if not private:
            raise _SSOFailure(f"_private_users not found for user_id={user_id}")

        tokens = private.get("login_oauth_tokens")
        if not tokens or not tokens.get("access_token"):
            raise _SSOFailure(f"login_oauth_tokens missing for user_id={user_id}")

        access_token = await _vend_access_token(private, tokens, settings)
        return SSOAccessTokenResponse(access_token=access_token).model_dump(mode="json")
    except Exception as exc:
        logger.warning("SSO access token retrieval failed: %s", exc)
        raise AppHTTPException(500, GENERIC_FAILURE_MESSAGE)


async def _vend_access_token(private: dict, tokens: dict, settings: Settings) -> str:
    expires_at = parse_expires_at(tokens.get("expires_at"))
    refresh_token = tokens.get("refresh_token")

    if expires_at is None:
        return tokens["access_token"]

    if datetime.utcnow() < expires_at - timedelta(seconds=REFRESH_MARGIN_SECONDS):
        return tokens["access_token"]

    if not refresh_token:
        raise _SSOFailure("token expired and no refresh_token available")

    new_token = await _refresh_for_provider(tokens["provider"], refresh_token, settings)

    rotated = build_login_oauth_tokens(tokens["provider"], new_token)
    if rotated["refresh_token"] is None:
        rotated["refresh_token"] = refresh_token

    await db.coll("_private_users").update_one(
        {"_id": private["_id"]},
        {"$set": {"login_oauth_tokens": rotated}},
    )
    return rotated["access_token"]


async def _refresh_for_provider(
    provider: str, refresh_token: str, settings: Settings
) -> dict:
    if provider == "google":
        client_id, client_secret = await resolve_google_oauth_credentials(settings)
        callback_url = f"{await addresses.canonical_base_url()}/api/apps/auth/callback"
        config = build_google_provider_config(client_id, client_secret, callback_url)
        return await refresh_access_token(config, refresh_token)

    if provider == "microsoft":
        # Microsoft logins carry no refresh_token today (no offline_access
        # scope, matching Base44's own flow), so _vend_access_token normally
        # fails before reaching here — the branch exists so a refresh-carrying
        # token, should the scope ever grow, refreshes instead of 500ing on
        # "unsupported oauth provider".
        client_id, client_secret, callback_url = await resolve_microsoft_oauth(settings)
        config = build_microsoft_provider_config(client_id, client_secret, callback_url)
        return await refresh_access_token(config, refresh_token)

    raise _SSOFailure(f"unsupported oauth provider: {provider}")
