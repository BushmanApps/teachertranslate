"""EscapeBase44 push notifications — /api/apps/{app_id}/eb44/push/*.

Our own namespace (the `eb44` segment), not a Base44 replica surface: the
device side of push, which Base44 keeps inside its wrapper. The wrapped app
(the shell injected into the SPA, mobile-kit/shell.ts) asks `config` whether
the owner has set sending up for its platform, registers the device's token
under the signed-in user, and drops it on sign-out. Sending is Base44's own
`SendPushNotification` integration (modules/integrations).
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import Depends
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from app.config import Settings
from app.core.errors import AppHTTPException
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings
from app.modules.push import store
from app.modules.push.send import platforms_configured

router = APIRouter(prefix="/api/apps/{app_id}/eb44/push", tags=["eb44-push"])


class DeviceBody(BaseModel):
    platform: Literal["ios", "android"]
    token: str = Field(min_length=1, max_length=4096)
    app_version: Optional[str] = Field(default=None, max_length=64)


def _require_user(ctx: AuthedContext) -> dict:
    if not ctx.user:
        raise AppHTTPException(401, "Sign in to register for notifications")
    return ctx.user


async def config(
    app_id: str,
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    return platforms_configured(settings)


async def register_device(
    app_id: str,
    body: DeviceBody,
    ctx: AuthedContext = Depends(get_authed_context),
):
    user = _require_user(ctx)
    await store.register(user["id"], body.platform, body.token, body.app_version)
    return {"success": True}


async def unregister_device(
    app_id: str,
    body: DeviceBody,
    ctx: AuthedContext = Depends(get_authed_context),
):
    user = _require_user(ctx)
    await store.unregister(user["id"], body.platform, body.token)
    return {"success": True}


router.add_api_route("/config", config, methods=["GET"])
router.add_api_route("/devices", register_device, methods=["POST"])
router.add_api_route("/devices", unregister_device, methods=["DELETE"])
