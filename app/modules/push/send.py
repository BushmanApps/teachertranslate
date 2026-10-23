"""One push to one person: every device they registered, through the
platform's service, dead tokens forgotten as they answer."""

from __future__ import annotations

import logging

import httpx

from app.config import Settings
from app.modules.push import apns, fcm, store

logger = logging.getLogger("escapebase44.push")


def platforms_configured(settings: Settings) -> dict[str, bool]:
    """What the app's shell asks before registering a device: whether the
    owner has set up sending for each platform. An app with neither never
    prompts anyone for permission."""
    return {"ios": apns.configured(settings), "android": fcm.configured(settings)}


async def send_to_user(
    settings: Settings,
    user_id: str,
    title: str,
    content: str,
    action_label: str | None,
    action_url: str | None,
) -> dict:
    devices = await store.devices_for(user_id)
    ready = platforms_configured(settings)
    sa = fcm.service_account(settings) if ready["android"] and any(d["platform"] == "android" for d in devices) else None
    sent = 0
    forgotten = 0
    # HTTP/2 for APNs (it accepts nothing else); FCM rides the same client.
    async with httpx.AsyncClient(http2=True, timeout=15) as client:
        for device in devices:
            platform = device["platform"]
            if not ready.get(platform):
                continue
            if platform == "ios":
                result = await apns.send(client, settings, device["token"], apns.payload(title, content, action_label, action_url))
            else:
                result = await fcm.send(client, sa or {}, device["token"], fcm.message(device["token"], title, content, action_label, action_url))
            if result.ok:
                sent += 1
            elif result.dead:
                await store.forget(platform, device["token"])
                forgotten += 1
            else:
                logger.warning("push to %s device failed: %s", platform, result.detail)
    return {"devices": len(devices), "sent": sent, "forgotten": forgotten}
