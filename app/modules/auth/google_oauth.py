"""Google OAuth routes — mounted under /api/apps/auth/ (no app_id in path).

GET /api/apps/auth/login       — start Google OAuth
GET /api/apps/auth/callback    — handle Google callback
GET /api/apps/auth/auth-error  — error page
GET /api/apps/auth/logout      — clear cookie and redirect
"""

from __future__ import annotations

import json
import secrets
from urllib.parse import urlparse

from fastapi import Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import Settings
from app.core import db
from app.core import addresses
from app.core.errors import AppHTTPException
from app.core.oauth import (
    ProviderConfig,
    build_authorize_url,
    exchange_code_for_token,
    fetch_userinfo,
)
from app.deps import get_settings
from app.modules.auth.oauth_post_login import post_oauth_login

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Note: previously this module also set an `app_session` cookie carrying the
# state JSON, and validated it on callback. Removed because Base44 doesn't —
# they encode state directly in the OAuth `state` parameter sent to Google
# and read it back from there on callback. The OAuth `state` parameter IS
# the CSRF-protection mechanism designed for this; the cookie was redundant
# belt-and-suspenders and produced wire divergence (Base44 emits no
# `Set-Cookie` on the redirect, and 400 "app_id is required" instead of our
# 307 to /auth-error when state is missing/malformed).
# The user-persistence cookie (`base44_access_token`) is set/cleared in
# `oauth_post_login.py` and unrelated to this flow.


def build_google_provider_config(
    client_id: str, client_secret: str, redirect_uri: str
) -> ProviderConfig:
    return ProviderConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="openid email profile",
        authorization_endpoint=GOOGLE_AUTHORIZE_URL,
        token_endpoint=GOOGLE_TOKEN_URL,
        userinfo_endpoint=GOOGLE_USERINFO_URL,
    )


async def resolve_google_oauth_credentials(
    settings: Settings, *, require_complete: bool = True
) -> tuple[str | None, str | None]:
    """Pick (client_id, client_secret) from auth_config + Settings.

    Custom mode overrides client_id when configured. Used by the login flow
    and by the SSO refresh path.
    """
    client_id, client_secret, _ = await resolve_google_oauth(
        settings, require_complete=require_complete
    )
    return client_id, client_secret


async def resolve_google_oauth(
    settings: Settings, *, require_complete: bool = True
) -> tuple[str | None, str | None, str]:
    """(client_id, client_secret, callback_url) for this deployment's mode.

    Default mode with GOOGLE_OAUTH_CALLBACK_URL set = EB44's shared client:
    the redirect_uri is the central forwarder URL registered on that client
    (state.domain routes the callback back here). Custom mode always uses
    this deployment's own callback — the builder registered it on THEIR
    client directly.
    """
    app_settings = await db.app_settings()
    auth_config = app_settings.get("auth_config") or {}
    google_mode = auth_config.get("google_oauth_mode", "default")

    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET

    # The custom-mode callback is REGISTERED at Google by the builder — it
    # must stay byte-stable across visits, so it derives from the canonical
    # address, never the arrival one.
    callback_url = f"{await addresses.canonical_base_url()}/api/apps/auth/callback"
    if google_mode != "custom" and settings.GOOGLE_OAUTH_CALLBACK_URL:
        callback_url = settings.GOOGLE_OAUTH_CALLBACK_URL

    if google_mode == "custom":
        custom_client_id = auth_config.get("google_oauth_client_id")
        if custom_client_id:
            client_id = custom_client_id
        elif require_complete:
            if not client_secret:
                raise AppHTTPException(500, "Custom Google OAuth is not properly configured")

    if require_complete and (not client_id or not client_secret):
        raise AppHTTPException(500, "Google OAuth is not configured")

    return client_id, client_secret, callback_url


# The migrator's mobile kit appends this marker to the wrapped app's
# WebView user agent (capacitor.config.json `appendUserAgent`). When the
# login starts from inside the wrapped app, the OAuth consent finishes in
# the system browser — which cannot navigate back into the webview — so
# the post-login redirect must go through the app's URL scheme instead.
# The scheme derivation (eb44-<app id>) mirrors mobile-scaffolding.ts and
# the login page template; all three are generated from the same app id.
MOBILE_APP_UA_MARKER = "EB44MobileApp"


def is_mobile_shell(request: Request) -> bool:
    return MOBILE_APP_UA_MARKER in (request.headers.get("user-agent") or "")


def oauth_start_response(request: Request, redirect_url: str, status_code: int = 307):
    """The response that sends the browser off to the provider's consent page.

    Shared by every social-login start route (Google, Microsoft, …) so the
    mobile-shell interstitial exists exactly once. `status_code` matches each
    provider's probed wire shape: Google 307, Microsoft 302.
    """
    if is_mobile_shell(request):
        # Inside the wrapped app, a redirect to the provider's consent page
        # would bounce the user out to the Safari APP (Capacitor sends external
        # navigations there). The native pattern is an in-app browser
        # sheet, so instead of redirecting we serve a tiny page that opens
        # the provider via the Capacitor Browser plugin (the page runs on the
        # app's own origin, so the bridge is available) and steps the
        # webview back to where the user was. The scheme redirect on
        # callback then reopens the app and the SPA listener closes the
        # sheet. If the plugin isn't there (older shells), fall back to
        # the plain redirect behavior.
        interstitial = f"""<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;display:flex;align-items:center;justify-content:center;height:100vh;font-family:-apple-system,system-ui,sans-serif;color:#64748b">
Continuing to sign-in…
<script>
(function () {{
  var url = {json.dumps(redirect_url)};
  var C = window.Capacitor;
  if (C && C.Plugins && C.Plugins.Browser) {{
    C.Plugins.Browser.open({{ url: url }});
    setTimeout(function () {{ history.back(); }}, 300);
  }} else {{
    window.location.replace(url);
  }}
}})();
</script></body></html>"""
        return HTMLResponse(interstitial)

    # Base44 uses 307 for the Google redirect and 302 for Microsoft (both
    # probe-verified). Browsers don't care for GET (OAuth start is always
    # GET), but matching each wire shape exactly. No Set-Cookie here —
    # state is carried in the OAuth `state` param.
    return RedirectResponse(url=redirect_url, status_code=status_code)


async def google_login(
    request: Request,
    app_id: str | None = Query(None),
    from_url: str | None = Query(None),
    settings: Settings = Depends(get_settings),
):
    if not app_id:
        raise AppHTTPException(400, "app_id is required")

    if is_mobile_shell(request):
        from_url = f"eb44-{settings.APP_ID}://oauth"

    client_id, client_secret, callback_url = await resolve_google_oauth(settings)

    state_data = {
        # The user returns to the address they arrived on (Base44's own
        # contract, measured 2026-08-31); the forwarder allow-lists it.
        "domain": await addresses.arrival_base_url(request),
        "from_url": from_url,
        "app_id": app_id,
    }
    state_str = json.dumps(state_data)

    nonce = secrets.token_urlsafe(16)

    config = build_google_provider_config(client_id, client_secret, callback_url)
    redirect_url = build_authorize_url(
        config,
        state=state_str,
        nonce=nonce,
        prompt="select_account",
    )

    return oauth_start_response(request, redirect_url)


async def google_callback(
    request: Request,
    state: str | None = Query(None),
    code: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    settings: Settings = Depends(get_settings),
):
    # Base44 wire contract: state is required and carries app_id. Missing or
    # malformed → 400 "app_id is required" (NOT a redirect to /auth-error).
    # The OAuth `state` parameter IS the CSRF check — the OAuth spec uses it
    # for exactly this purpose. Probe-verified against base44.app: both
    # "no state at all" and "state= but malformed JSON" produce 400 with
    # message "app_id is required".
    if not state:
        raise AppHTTPException(400, "app_id is required")
    try:
        state_data = json.loads(state)
    except (json.JSONDecodeError, TypeError):
        raise AppHTTPException(400, "app_id is required")
    app_id = state_data.get("app_id")
    if not app_id:
        raise AppHTTPException(400, "app_id is required")

    # Google reported an OAuth-side error (e.g. user denied consent) — only
    # check this AFTER we have a valid state, so we can still report nicely.
    # Base44 also reaches this branch only after state validation.
    if error:
        error_msg = f"{error}: {error_description or ''}"
        return RedirectResponse(
            url=f"/api/apps/auth/auth-error?error_type=OAuthError&error_message={_url_encode(error_msg)}",
            status_code=307,
        )

    from_url = state_data.get("from_url")

    client_id, client_secret, callback_url = await resolve_google_oauth(settings)
    config = build_google_provider_config(client_id, client_secret, callback_url)

    try:
        token = await exchange_code_for_token(config, code)
        userinfo = await fetch_userinfo(config, token["access_token"])
    except Exception:
        return RedirectResponse(
            url="/api/apps/auth/auth-error?error_type=OAuthError&error_message="
                + _url_encode("Failed to complete Google authentication"),
            status_code=307,
        )

    google_email = userinfo.get("email", "").lower().strip()
    google_name = userinfo.get("name", "")

    if not google_email:
        return RedirectResponse(
            url="/api/apps/auth/auth-error?error_type=OAuthError&error_message="
                + _url_encode("No email returned from Google"),
            status_code=307,
        )

    return await post_oauth_login(
        email=google_email,
        name=google_name,
        provider="google",
        fallback_base_url=await addresses.arrival_base_url(request),
        oauth_tokens=token,
        from_url=from_url,
        settings=settings,
    )


async def auth_error(request: Request):
    # Copied verbatim from Base44 production wire output (probed against
    # https://map-track-bd5d3b8e.base44.app/api/apps/auth/auth-error?reason=test
    # on 2026-05-19). The page body is static — Base44 ignores any query
    # params (`error_type`, `error_message`, `reason`) and always serves
    # this exact HTML. Leading newline + indentation match Base44 byte-for-byte.
    return HTMLResponse(
        content="""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Authentication Error</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        text-align: center;
                    }
                    .error-container {
                        margin-top: 50px;
                        padding: 20px;
                        border: 1px solid #ddd;
                        border-radius: 5px;
                        background-color: #f8f8f8;
                    }
                    h1 {
                        color: #333;
                    }
                    .error-message {
                        color: #555;
                        margin: 20px 0;
                    }
                    .login-button {
                        display: inline-block;
                        padding: 10px 20px;
                        background-color: #4285f4;
                        color: white;
                        text-decoration: none;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                    .login-button:hover {
                        background-color: #3367d6;
                    }
                </style>
            </head>
            <body>
                <div class="error-container">
                    <h1>Login Session Expired</h1>
                    <p class="error-message">
                        Your login session has expired or was interrupted. This can happen if:
                        <ul style="text-align: left;">
                            <li>You waited too long on the login screen</li>
                            <li>You closed and reopened your browser during login</li>
                            <li>You navigated away from the login page</li>
                            <li>Your browser blocked third-party cookies</li>
                        </ul>
                    </p>
                    <a href="/api/auth/login" class="login-button">Try Logging In Again</a>
                </div>
            </body>
        </html>
        """,
        status_code=200,
    )


async def logout(
    request: Request,
    from_url: str | None = Query(None),
):
    redirect_target = "/"
    if from_url:
        parsed = urlparse(from_url)
        if parsed.scheme and parsed.netloc:
            redirect_target = "/"
        else:
            redirect_target = from_url

    response = RedirectResponse(url=redirect_target, status_code=302)
    response.delete_cookie(
        "base44_access_token",
        path="/",
        samesite="lax",
    )
    return response


def _url_encode(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")
