"""Apple Push Notification service, over HTTP/2 with a provider token.

The provider token is an ES256 JWT signed with the owner's APNs auth key
(the `.p8` from Apple Developer → Keys), good for an hour; Apple asks for a
fresh one no more often than every twenty minutes, so one is kept for fifty.
A build from the App Store or TestFlight talks to the production gateway; a
build a developer ran onto their own phone (Xcode, a development profile)
holds a sandbox token, which production refuses as BadDeviceToken — that one
answer is retried on the sandbox gateway before the token is given up on.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx
import jwt

from app.config import Settings
from app.core.mobile_identity import ios_bundle_id

logger = logging.getLogger("escapebase44.push")

PRODUCTION = "https://api.push.apple.com"
SANDBOX = "https://api.sandbox.push.apple.com"

_provider_token: tuple[str, float, str] | None = None  # (token, minted_at, key id)


def configured(settings: Settings) -> bool:
    return bool(settings.APNS_KEY_P8 and settings.APNS_KEY_ID and settings.APPLE_TEAM_ID)


def provider_token(settings: Settings) -> str:
    global _provider_token
    now = time.time()
    if _provider_token and _provider_token[2] == settings.APNS_KEY_ID and now - _provider_token[1] < 50 * 60:
        return _provider_token[0]
    token = jwt.encode(
        {"iss": settings.APPLE_TEAM_ID, "iat": int(now)},
        settings.APNS_KEY_P8,
        algorithm="ES256",
        headers={"kid": settings.APNS_KEY_ID},
    )
    _provider_token = (token, now, settings.APNS_KEY_ID or "")
    return token


@dataclass
class SendResult:
    ok: bool
    # The token is gone for good (uninstalled, rotated): forget it.
    dead: bool = False
    detail: str | None = None


def payload(title: str, content: str, action_label: str | None, action_url: str | None) -> dict:
    body: dict = {"aps": {"alert": {"title": title, "body": content}, "sound": "default"}}
    # Custom keys ride at the top level; the Capacitor plugin hands them to
    # the app as `notification.data`, where the shell reads `action_url`.
    if action_url:
        body["action_url"] = action_url
    if action_label:
        body["action_label"] = action_label
    return body


async def send(client: httpx.AsyncClient, settings: Settings, token: str, body: dict) -> SendResult:
    headers = {
        "authorization": f"bearer {provider_token(settings)}",
        "apns-topic": ios_bundle_id(settings),
        "apns-push-type": "alert",
        "apns-priority": "10",
        "apns-expiration": "0",
    }
    result = await _post(client, PRODUCTION, token, headers, body)
    if result.dead and result.detail == "BadDeviceToken":
        # A development build's token — try the sandbox before giving up.
        sandbox = await _post(client, SANDBOX, token, headers, body)
        if sandbox.ok or not sandbox.dead:
            return sandbox
    return result


async def _post(client: httpx.AsyncClient, host: str, token: str, headers: dict, body: dict) -> SendResult:
    try:
        res = await client.post(f"{host}/3/device/{token}", headers=headers, json=body)
    except httpx.HTTPError as e:
        return SendResult(ok=False, detail=f"apns unreachable: {e}")
    if res.status_code == 200:
        return SendResult(ok=True)
    reason = None
    try:
        reason = res.json().get("reason")
    except ValueError:
        pass
    # 410 = the token is no longer active; 400 BadDeviceToken /
    # DeviceTokenNotForTopic = never valid for this app.
    dead = res.status_code == 410 or reason in ("BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered")
    if not dead:
        logger.warning("apns %s answered %s %s", host, res.status_code, reason or res.text[:200])
    return SendResult(ok=False, dead=dead, detail=reason or f"{res.status_code}")
