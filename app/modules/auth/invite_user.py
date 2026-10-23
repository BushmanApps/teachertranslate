"""POST /api/apps/:appId/users/invite-user — auth-router-side invite.

Behavior diverges from the runtime route `/api/apps/:appId/runtime/users/
invite-user` on TWO axes (probed 2026-05-21 + 2026-05-22 on +pmM9):

  - **no-auth**:
    - auth-router: 401 "No authentication header (Authorization:
      Bearer <token> or api_key)" (HTTPException envelope). Base44 treats
      this route as an SDK client-facing API requiring an explicit credential.
    - runtime-router: 403 "You must be logged in to invite users."

  - **app_user JWT (any role, admin OR non-admin)** — F-030 finding:
    - auth-router: **401 "Could not validate credentials"** — B44 rejects
      app_user JWTs upfront on this route, even for admin users. Probed:
      pmm9 with role:"user" → 401; same after PUT-promoted to role:"admin"
      via api_key path → still 401. Decode itself succeeds (pmm9 hits
      `/User/me` fine on the same token); the rejection is specific to
      this route's auth gate.
    - runtime-router: accepts admin app_user JWTs (200), rejects
      non-admin (403). Same-decisions: SDK's `users.inviteUser` hits the
      runtime route; SDK's `auth.inviteUser` hits this route and is
      effectively api_key/platform-only on B44.

On the api_key / platform-Bearer success path both routes return the
full RuntimeApp wire shape via the shared `_do_invite_user` logic.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.config import Settings
from app.core.errors import AppHTTPException
from app.core.models import InviteUserBody
from app.core.security.pipeline import (
    AuthedContext,
    get_authed_context_required_no_visibility,
)
from app.deps import get_email_provider, get_settings
from app.modules.users.invite_user import _do_invite_user


async def invite_user(
    app_id: str,
    body: InviteUserBody,
    request: Request,
    # auth-required dep: raises 401 "No authentication header ..." on no-auth
    # before FastAPI runs Pydantic body validation. Matches Base44's
    # auth-router-side gate order.
    ctx: AuthedContext = Depends(get_authed_context_required_no_visibility),
    settings: Settings = Depends(get_settings),
    email_provider=Depends(get_email_provider),
):
    # F-030 (probed 2026-05-22 on +pmM9, both non-admin and admin):
    # B44 rejects app_user JWTs on this auth-router route with 401
    # "Could not validate credentials". The runtime-router route accepts
    # admin app_user JWTs (handled in users/invite_user.py).
    if ctx.token_class == "app_user":
        raise AppHTTPException(401, "Could not validate credentials")
    return await _do_invite_user(app_id, body, request, ctx, settings, email_provider)


__all__ = ["invite_user"]
