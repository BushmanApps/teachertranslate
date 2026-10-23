"""Microsoft social-login routes — mounted under /api/apps/auth/microsoft/.

GET /api/apps/auth/microsoft/login       — start Microsoft sign-in
GET /api/apps/auth/microsoft/callback    — handle Microsoft callback

This is `auth_config.enable_microsoft_login` — the social-login sibling of
`enable_google_login`, NOT the Elite `enable_sso_login` OIDC feature (Base44's
own error message names it `microsoft_built_in`). On Base44 it runs
exclusively on Base44's own Entra client (their CLI docs: custom OAuth
credentials "are currently supported for Google only. Other providers use
Base44-managed credentials"), so there is no custom mode here: the migrated
equivalent is EB44's shared Entra client, seeded by the migrator as
MICROSOFT_CLIENT_ID/SECRET with MICROSOFT_OAUTH_CALLBACK_URL pointing the
dance at the auth.eb44.app forwarder (state.domain routes the callback back
to this deployment — the same mechanism as Google's shared mode).

Wire contract probed against app.base44.com 2026-08-17:
  login    — 302 (Google's is 307) to login.microsoftonline.com/common/
             oauth2/v2.0/authorize, scope "openid email profile",
             prompt=select_account, JSON state {"from_url", "app_id"?}
             (app_id key omitted when the query didn't carry one — app_id is
             NOT required, unlike the Google login). No offline_access scope
             — no refresh token. Their URL also carries `access_type=offline`
             (a Google-only param Microsoft ignores — copy-pasted from their
             Google flow; we don't cargo-cult it) and PKCE, which is optional
             for a confidential client and invisible to the app, so we skip
             it and stay stateless across the two legs.
  callback — `error` param present → 400 "OAuth authentication failed:
             {error}" (checked BEFORE state, error_description not included);
             every other failure — missing/malformed state, failed exchange —
             → 401 "microsoft_built_in authentication failed" (one catch-all,
             no auth-error redirect — unlike the Google callback).
"""

from __future__ import annotations

import json
import logging
import secrets

import jwt
from fastapi import Depends, Query, Request

from app.config import Settings
from app.core import addresses
from app.core.errors import AppHTTPException
from app.core.oauth import (
    ProviderConfig,
    build_authorize_url,
    exchange_code_for_token,
    fetch_userinfo,
)
from app.deps import get_settings
from app.modules.auth.google_oauth import is_mobile_shell, oauth_start_response
from app.modules.auth.oauth_post_login import post_oauth_login

MICROSOFT_AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_USERINFO_URL = "https://graph.microsoft.com/oidc/userinfo"

GENERIC_FAILURE_MESSAGE = "microsoft_built_in authentication failed"

logger = logging.getLogger(__name__)


def build_microsoft_provider_config(
    client_id: str, client_secret: str, redirect_uri: str
) -> ProviderConfig:
    return ProviderConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="openid email profile",
        authorization_endpoint=MICROSOFT_AUTHORIZE_URL,
        token_endpoint=MICROSOFT_TOKEN_URL,
        userinfo_endpoint=MICROSOFT_USERINFO_URL,
    )


async def resolve_microsoft_oauth(settings: Settings) -> tuple[str, str, str]:
    """(client_id, client_secret, callback_url) for Microsoft sign-in."""
    client_id = settings.MICROSOFT_CLIENT_ID
    client_secret = settings.MICROSOFT_CLIENT_SECRET
    if not client_id or not client_secret:
        raise AppHTTPException(500, "Microsoft login is not configured")

    callback_url = (
        settings.MICROSOFT_OAUTH_CALLBACK_URL
        or f"{await addresses.canonical_base_url()}/api/apps/auth/microsoft/callback"
    )
    return client_id, client_secret, callback_url


async def microsoft_login(
    request: Request,
    app_id: str | None = Query(None),
    from_url: str | None = Query(None),
    settings: Settings = Depends(get_settings),
):
    if is_mobile_shell(request):
        from_url = f"eb44-{settings.APP_ID}://oauth"

    client_id, client_secret, callback_url = await resolve_microsoft_oauth(settings)

    # `domain` routes the shared-client forwarder back here (state is parsed
    # by nobody but us and the forwarder); from_url/app_id mirror Base44's
    # state shape — app_id rides along only when the SDK sent one.
    state_data: dict = {"domain": await addresses.arrival_base_url(request), "from_url": from_url}
    if app_id:
        state_data["app_id"] = app_id
    state_str = json.dumps(state_data)

    nonce = secrets.token_urlsafe(16)

    config = build_microsoft_provider_config(client_id, client_secret, callback_url)
    redirect_url = build_authorize_url(
        config,
        state=state_str,
        nonce=nonce,
        prompt="select_account",
    )
    return oauth_start_response(request, redirect_url, status_code=302)


async def microsoft_callback(
    request: Request,
    state: str | None = Query(None),
    code: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    settings: Settings = Depends(get_settings),
):
    # Probed: the error branch runs BEFORE state validation, and the message
    # carries the error code only — never error_description.
    if error:
        raise AppHTTPException(400, f"OAuth authentication failed: {error}")

    try:
        if not state:
            raise _MicrosoftFailure("state missing")
        try:
            state_data = json.loads(state)
        except (json.JSONDecodeError, TypeError):
            raise _MicrosoftFailure("state malformed")

        from_url = state_data.get("from_url")

        client_id, client_secret, callback_url = await resolve_microsoft_oauth(settings)
        config = build_microsoft_provider_config(client_id, client_secret, callback_url)

        token = await exchange_code_for_token(config, code)
        userinfo = await fetch_userinfo(config, token["access_token"])

        email = (userinfo.get("email") or "").lower().strip()
        name = userinfo.get("name", "")

        if not email or not name:
            # Graph's OIDC userinfo omits `email` for some Entra org
            # configurations, and omits `name` for personal accounts
            # (observed live on an MSA 2026-08-18). The id_token came
            # straight from Microsoft's token endpoint over TLS, so its
            # claims are usable without a local signature check;
            # `preferred_username` is the UPN, which is the sign-in email
            # for the org accounts the email fallback exists for.
            claims: dict = {}
            if token.get("id_token"):
                try:
                    claims = jwt.decode(
                        token["id_token"], options={"verify_signature": False}
                    )
                except jwt.PyJWTError:
                    claims = {}
            if not email:
                email = (claims.get("email") or "").lower().strip()
            if not email and "@" in (claims.get("preferred_username") or ""):
                email = claims["preferred_username"].lower().strip()
            if not name:
                name = claims.get("name", "")

        if not email:
            raise _MicrosoftFailure("no email in userinfo or id_token")
    except AppHTTPException:
        raise
    except Exception as exc:
        logger.warning("Microsoft login failed: %s", exc)
        raise AppHTTPException(401, GENERIC_FAILURE_MESSAGE)

    return await post_oauth_login(
        email=email,
        name=name,
        provider="microsoft",
        fallback_base_url=await addresses.arrival_base_url(request),
        oauth_tokens=token,
        from_url=from_url,
        settings=settings,
    )


class _MicrosoftFailure(Exception):
    """Internal sentinel — collapsed into the probed 401 catch-all."""
