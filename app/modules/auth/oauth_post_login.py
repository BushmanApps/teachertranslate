"""Provider-agnostic post-OAuth login.

Once an OAuth provider has been exchanged for tokens and an email/name
extracted, every provider does the same thing: upsert the User, upsert
_private_users with the OAuth tokens, mint the app JWT, and 302 the
browser back to the SDK with `access_token` (and `is_new_user=true` for
new accounts) on the URL plus a session cookie.

Google, Microsoft and Apple-on-the-web use the redirect shape; the native
Apple leg uses `complete_oauth_login` directly and answers JSON.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import jwt
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.core import db
from app.core.responses import utcnow_naive
from app.core.security.tokens import encode_app_token
from app.modules.auth.helpers import (
    build_new_user_doc,
    build_private_user_doc,
    get_app_visibility_mode,
    is_user_invited,
)

SESSION_COOKIE_NAME = "base44_access_token"
SESSION_MAX_AGE = 14 * 24 * 60 * 60
EXPIRES_AT_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


@dataclass(frozen=True)
class OAuthLogin:
    """What a completed provider login amounts to: the app token — or, for an
    uninvited person on a restricted app, the request-access page they are
    sent to instead (no token)."""

    access_token: str | None
    is_new_user: bool
    access_request_url: str | None


async def post_oauth_login(
    *,
    email: str,
    name: str | None,
    provider: str,
    oauth_tokens: dict,
    from_url: str | None,
    settings: Settings,
    # The address the OAuth callback arrived on — the continuation base when
    # from_url is absent (callers derive it per request).
    fallback_base_url: str,
) -> RedirectResponse:
    """The browser-shaped ending: 302 back to the SDK with the token on the
    URL (307 to the request-access page for an uninvited person)."""
    login = await complete_oauth_login(
        email=email, name=name, provider=provider, oauth_tokens=oauth_tokens,
        settings=settings, fallback_base_url=fallback_base_url,
    )
    if login.access_request_url:
        return RedirectResponse(url=login.access_request_url, status_code=307)
    access_token = login.access_token or ""
    redirect_target = _safe_redirect_url(from_url, fallback_base_url, settings.APP_ID)
    separator = "&" if "?" in redirect_target else "?"
    final_url = f"{redirect_target}{separator}access_token={access_token}"
    if login.is_new_user:
        final_url += "&is_new_user=true"

    response = RedirectResponse(url=final_url, status_code=302)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        access_token,
        max_age=SESSION_MAX_AGE,
        path="/",
        samesite="lax",
    )
    return response


async def complete_oauth_login(
    *,
    email: str,
    name: str | None,
    provider: str,
    oauth_tokens: dict,
    settings: Settings,
    fallback_base_url: str,
) -> OAuthLogin:
    """Everything a provider login does once the provider has vouched for an
    email: upsert the User and its private twin, fire the auth workflow, mint
    the app token. Shared by the redirect flows (Google, Microsoft, Apple on
    the web) and the native Apple leg, which answers JSON instead of a 302."""
    email = email.lower().strip()

    is_new_user = False
    user = await db.coll("User").find_one(
        {"email": email, "app_id": settings.APP_ID}
    )
    if user:
        if not user.get("is_verified"):
            await db.coll("User").update_one(
                {"_id": user["_id"]},
                {"$set": {"is_verified": True, "updated_date": utcnow_naive()}},
            )
        user_id = str(user["_id"])
    else:
        # New account via OAuth. A restricted app (private/workspace) gates a
        # brand-new uninvited user exactly like register does — probed
        # 2026-05-24 on ParityGym: B44 register under private_with_login
        # returns the access-request branch (no token) for an uninvited email,
        # while an EXISTING user still logs in. Without this gate an uninvited
        # Google user would be admitted to a Private app (a hole), since the
        # visibility gate alone admits any authenticated app_user. Existing
        # users are handled by the `if user:` branch above and are unaffected.
        visibility_mode = await get_app_visibility_mode()
        is_restricted = visibility_mode in ("private_with_login", "workspace_with_login")
        if is_restricted and not await is_user_invited(email, settings.APP_ID):
            # B44 wire (probed 2026-05-24 via HAR, fresh uninvited Google user
            # on a private_with_login app): the callback 307-redirects to the
            # SPA access-request page with a short-lived confirm JWT in the URL
            # fragment, and issues NO access_token —
            #   307 → {app}/request-access?app_id=<id>#confirmation_token=<JWT>
            # JWT (HS256, APP_JWT_SECRET): {email, app_id, jti, iat,
            # exp:iat+3600, aud:"access_request_confirm"}.
            confirm_token = _build_access_request_token(email, settings)
            base = fallback_base_url.rstrip("/")
            return OAuthLogin(
                access_token=None,
                is_new_user=False,
                access_request_url=f"{base}/request-access?app_id={settings.APP_ID}#confirmation_token={confirm_token}",
            )
        is_new_user = True
        full_name = name or email.split("@")[0]
        user_doc = build_new_user_doc(email, full_name, settings.APP_ID)
        user_doc["is_verified"] = True
        try:
            await db.coll("User").insert_one(user_doc)
        except DuplicateKeyError:
            # Parallel OAuth callbacks for the same account must converge on
            # the first persisted user, not leave the second callback failed.
            user = await db.coll("User").find_one(
                {"email": email, "app_id": settings.APP_ID}
            )
            if not user:
                raise
            is_new_user = False
            if not user.get("is_verified"):
                await db.coll("User").update_one(
                    {"_id": user["_id"]},
                    {"$set": {"is_verified": True, "updated_date": utcnow_naive()}},
                )
            user_id = str(user["_id"])
        else:
            user_id = str(user_doc["_id"])

    login_oauth_tokens = build_login_oauth_tokens(provider, oauth_tokens)
    private_doc = build_private_user_doc(email, settings.APP_ID, user_id)
    await db.coll("_private_users").update_one(
        {"email": email, "app_id": settings.APP_ID},
        {
            "$setOnInsert": private_doc,
            "$set": {"login_oauth_tokens": login_oauth_tokens},
        },
        upsert=True,
    )

    # Workflows: an OAuth-created user is a `signup` (they come into being
    # verified — the same "when the user actually exists" rule OTP
    # verification measured, H §14.9); a returning one is a `login`. The
    # event firing is the measured contract; `auth_method` carrying the
    # provider name is the natural value (only "password" was measured).
    from app.core.workflows.dispatch import dispatch_auth
    try:
        await dispatch_auth(
            "signup" if is_new_user else "login",
            user_doc if is_new_user else {**user, "is_verified": True},
            auth_method=provider,
        )
    except Exception:
        pass  # a workflow must never fail the auth path

    return OAuthLogin(
        access_token=encode_app_token(email, settings),
        is_new_user=is_new_user,
        access_request_url=None,
    )


def _build_access_request_token(email: str, settings: Settings) -> str:
    """Mint the short-lived access-request confirmation JWT B44 puts in the
    `/request-access#confirmation_token=` fragment for an uninvited OAuth user
    on a restricted app. Shape probed 2026-05-24 (HAR): HS256, 1-hour expiry,
    `aud: "access_request_confirm"`, random `jti`.
    """
    now = int(time.time())
    return jwt.encode(
        {
            "email": email,
            "app_id": settings.APP_ID,
            "jti": secrets.token_urlsafe(16),
            "iat": now,
            "exp": now + 3600,
            "aud": "access_request_confirm",
        },
        settings.APP_JWT_SECRET,
        algorithm="HS256",
    )


def build_login_oauth_tokens(provider: str, token: dict) -> dict:
    return {
        "provider": provider,
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "expires_at": format_expires_at(token.get("expires_at")),
        "scope": token.get("scope"),
        "token_type": token.get("token_type", "Bearer"),
    }


def format_expires_at(value) -> str | None:
    """Authlib returns expires_at as epoch seconds; we store as naive UTC ISO string.

    Mirrors the existing `_private_users` convention (see otp_expiry_time in
    helpers.py) — fields land as strings, not BSON dates.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value.replace(tzinfo=None) if value.tzinfo else value
    else:
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
    return dt.strftime(EXPIRES_AT_FORMAT)


def parse_expires_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, EXPIRES_AT_FORMAT)
    except (TypeError, ValueError):
        return None


def _safe_redirect_url(from_url: str | None, base_url: str, app_id: str) -> str:
    """Return an OAuth continuation only when it stays on this app's origin,
    or when it is this app's own store-app return address.

    The continuation receives the newly minted access token, so accepting an
    arbitrary absolute URL would leak that token to an attacker.  Relative
    paths are supported, but protocol-relative and backslash forms are
    rejected because browsers can reinterpret them as another origin.
    """
    # The store app (the Android and iPhone app built from this repo by the
    # EscapeBase44 mobile kit) runs Google, Apple, Facebook and Microsoft
    # sign-in in an in-app browser tab, with exactly this address as from_url
    # (see is_mobile_shell in the *_oauth.py files). Sending the tab here hands
    # the token back to the app, which closes the tab and signs itself in.
    # Without it the tab opens the website instead, signed in, on top of the
    # app, and the app stays on its sign-in page. Only this app's own address
    # is allowed: any other scheme still falls through to the checks below.
    if from_url == f"eb44-{app_id}://oauth":
        return from_url
    if not from_url or "\\" in from_url:
        return base_url

    try:
        target = urljoin(base_url.rstrip("/") + "/", from_url)
        base = urlparse(base_url)
        parsed = urlparse(target)
    except (TypeError, ValueError):
        return base_url

    if (
        parsed.scheme not in {"http", "https"}
        or (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc)
    ):
        return base_url
    return target
