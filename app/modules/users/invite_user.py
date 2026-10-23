"""POST handler for invite-user — shared between two routes with DIFFERENT
no-auth gate behavior:

- `/api/apps/{app_id}/users/invite-user` (auth router): no-auth -> 401
  "No authentication header (Authorization: Bearer <token> or api_key)".
  Handler: `auth/invite_user.py:invite_user` (uses
  `get_authed_context_required_no_visibility`).
- `/api/apps/{app_id}/runtime/users/invite-user` (runtime router):
  no-auth -> 403 "You must be logged in to invite users." Handler:
  `runtime_invite_user` below (uses `get_authed_context_no_visibility`
  so anonymous flows through to the permission check).

Both paths converge on `_do_invite_user` which runs visibility gate +
permission check + email send + `_app_settings` update + RuntimeApp
response. Verified via 2026-05-21 probes: anonymous on the two routes
produces the two different envelopes; api_key on both routes produces
the same RuntimeApp 200.

The response is `RuntimeApp` with `updated_date` stamped fresh on the
response (aware UTC). Mongo stores it naive (utcnow_naive). The dual-
stamp pattern lets orjson's `OPT_UTC_Z` flag emit `Z`-suffix ISO on
the wire (D-031, D-052):
- Aware datetime in the response dict -> orjson emits `Z` suffix.
- Naive datetime stored in Mongo -> next read returns naive (no suffix).
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.config import Settings
from app.core import db
from app.core import addresses
from app.core.errors import AppHTTPException
from app.core.models import InviteUserBody, RuntimeApp
from app.core.providers.email.templates import invite_email_html
from app.core.responses import app_settings_to_runtime, utcnow, utcnow_naive
from app.core.security.pipeline import AuthedContext, get_authed_context_no_visibility
from app.core.security.visibility import assert_app_visible
from app.deps import get_email_provider, get_settings


def _is_default_role(role: str | None) -> bool:
    return role is None or role == "" or role == "user"


def _effective_token_class(ctx: AuthedContext, request: Request) -> str:
    # Base44-Service-Authorization alone (without Authorization) is anonymous-like
    # on the invite route — see users.md "Service token in Authorization" section
    if ctx.token_class == "service_role" and not request.headers.get("Authorization"):
        return "anonymous"
    return ctx.token_class


def _check_invite_permission(
    token_class: str,
    ctx: AuthedContext,
    role: str | None,
    app_id: str,
) -> None:
    """Authorization check that runs AFTER `assert_app_visible` in the
    handler. By the time we reach here:
    - Visibility gate has already produced envelope #6 (AppError +
      extra_data) for any anonymous/platform/app_user-without-user caller
      on the 3 login-required modes (public_with_login, private_with_login,
      workspace_with_login). Wire-matched to probe #4 (anonymous-runtime-invite-user).
    - Service-role and preview are skipped by the caller before this
      function — they bypass the gate by design.
    - Verified app_user falls through to the role-based logic below.
    """
    if token_class in ("preview", "service_role"):
        return

    # Visibility gate handled the 3 login-required modes; only
    # public_without_login reaches here for unauth callers. Wire matches
    # probe #4a (envelope #4, "You must be logged in to invite users.").
    if token_class in ("anonymous", "platform") or (
        token_class == "app_user" and ctx.user is None
    ):
        raise AppHTTPException(403, "You must be logged in to invite users.")

    user_role = (ctx.user.get("role") or "user") if ctx.user else "user"

    if user_role == "admin":
        return

    if user_role == "owner":
        if _is_default_role(role):
            return
        raise AppHTTPException(403, "Only admins can invite users with non-default roles.")

    privacy_mode = ctx.app_settings.get("public_settings", "public_without_login")
    if privacy_mode in ("private_with_login", "workspace_with_login"):
        raise AppHTTPException(403, "Only admins can invite users to private apps.")

    if not _is_default_role(role):
        raise AppHTTPException(403, "Only admins can invite users with non-default roles.")


def _get_inviter_identity(ctx: AuthedContext) -> str:
    if ctx.token_class == "service_role" and ctx.service_principal:
        return ctx.service_principal["email"]
    if ctx.user:
        return ctx.user.get("email", "unknown")
    if ctx.token_payload:
        return ctx.token_payload.get("sub", "unknown")
    return "unknown"


async def runtime_invite_user(
    app_id: str,
    body: InviteUserBody,
    request: Request,
    # Non-required auth dep: anonymous flows through to `_check_invite_permission`,
    # which raises 403 "You must be logged in to invite users." (matches Base44's
    # runtime-router envelope on data-core-lab 2026-05-21). The auth-router
    # variant in `auth/invite_user.py:invite_user` uses the *required* dep
    # instead so its no-auth case emits 401 with the "No authentication header"
    # envelope.
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
    settings: Settings = Depends(get_settings),
    email_provider=Depends(get_email_provider),
):
    return await _do_invite_user(app_id, body, request, ctx, settings, email_provider)


async def _do_invite_user(
    app_id: str,
    body: InviteUserBody,
    request: Request,
    ctx: AuthedContext,
    settings: Settings,
    email_provider,
):
    """Shared core for both auth-router and runtime-router invite endpoints.

    Pre-conditions:
    - `ctx` is built by EITHER the required-auth dep (auth-router; anonymous
      callers already 401'd before this fires) OR the non-required dep
      (runtime-router; anonymous reaches here with `ctx.token_class ==
      "anonymous"` and gets 403'd in `_check_invite_permission`).
    """
    token_class = _effective_token_class(ctx, request)

    # Visibility-gate the invite (probe #4 on 2026-05-18 — anonymous on
    # login-required modes emits envelope #6 with extra_data, not envelope #4).
    # We run the gate manually here instead of switching the handler dep to
    # `get_authed_context` because `_effective_token_class` may reclassify a
    # service_role token (BSA-only, no Authorization) to "anonymous" per
    # users.md, and we want the gate to fire on that effective class.
    # Service_role and preview skip the gate by design — same as the perm check.
    if token_class not in ("service_role", "preview"):
        assert_app_visible(
            token_class, ctx.app_settings, settings.APP_ID, user=ctx.user,
        )

    _check_invite_permission(token_class, ctx, body.role, app_id)

    app_name = ctx.app_settings.get("name", "this app")
    invite_role = body.role if body.role else "user"
    inviter = _get_inviter_identity(ctx)
    app_url = await addresses.arrival_base_url(request)

    try:
        await email_provider.send(
            to=body.user_email,
            subject=f"You're invited to join {app_name}",
            html=invite_email_html(
                app_name, body.user_email, inviter, invite_role, app_url,
                description=ctx.app_settings.get("user_description") or "",
            ),
            from_name=app_name,
        )
    except Exception:
        raise AppHTTPException(500, "Failed to send invitation email.")

    invited_email = body.user_email.strip().lower()
    aware_now = utcnow()
    update_set: dict = {"updated_date": utcnow_naive()}
    update_doc: dict = {"$set": update_set}
    if invited_email:
        update_doc["$addToSet"] = {"invited_users": invited_email}

    await db.coll("_app_settings").update_one({}, update_doc)

    # Refresh the freshness-bounded cache from Mongo (reload=True) so the
    # just-added invited user is reflected immediately, not a TTL later.
    await db.app_settings(reload=True)
    # The response is the full RuntimeApp shape, so it needs the fields the
    # hot read projects out (`agents`, `seo_settings` — see core/db.py).
    fresh = await db.app_settings_full()
    # Overwrite the read-back naive updated_date with the in-process aware
    # value so orjson's OPT_UTC_Z emits the `Z` suffix on the wire (D-052).
    fresh["updated_date"] = aware_now

    return RuntimeApp(**app_settings_to_runtime(fresh)).model_dump(mode="json")
