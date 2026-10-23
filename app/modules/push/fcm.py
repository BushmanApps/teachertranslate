"""Firebase Cloud Messaging (HTTP v1), as the owner's Firebase project.

The sender credential is the project's service-account key
(FCM_SERVICE_ACCOUNT_JSON_B64); the app-side half, google-services.json, is
baked into the Android build by the mobile kit. A token FCM reports as
UNREGISTERED (the app was uninstalled, the token rotated) is forgotten.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.core.google_service_account import access_token, load_service_account

logger = logging.getLogger("escapebase44.push")

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


def configured(settings: Settings) -> bool:
    return bool(settings.FCM_SERVICE_ACCOUNT_JSON_B64)


def service_account(settings: Settings) -> dict:
    return load_service_account(settings.FCM_SERVICE_ACCOUNT_JSON_B64 or "", "FCM_SERVICE_ACCOUNT_JSON_B64")


@dataclass
class SendResult:
    ok: bool
    dead: bool = False
    detail: str | None = None


def message(token: str, title: str, content: str, action_label: str | None, action_url: str | None) -> dict:
    data: dict[str, str] = {}
    if action_url:
        data["action_url"] = action_url
    if action_label:
        data["action_label"] = action_label
    return {
        "message": {
            "token": token,
            "notification": {"title": title, "body": content},
            "data": data,
            "android": {"priority": "high"},
        }
    }


async def send(client: httpx.AsyncClient, sa: dict, token: str, body: dict) -> SendResult:
    try:
        bearer = await access_token(sa, _SCOPE)
        res = await client.post(
            f"https://fcm.googleapis.com/v1/projects/{sa['project_id']}/messages:send",
            headers={"Authorization": f"Bearer {bearer}"},
            json=body,
        )
    except Exception as e:  # token exchange or transport
        return SendResult(ok=False, detail=f"fcm unreachable: {e}")
    if res.status_code == 200:
        return SendResult(ok=True)
    detail = res.text[:300]
    dead = res.status_code == 404 and "UNREGISTERED" in res.text or (
        res.status_code == 400 and "not a valid FCM registration token" in res.text
    )
    if not dead:
        logger.warning("fcm answered %s %s", res.status_code, detail)
    return SendResult(ok=False, dead=dead, detail=detail)
