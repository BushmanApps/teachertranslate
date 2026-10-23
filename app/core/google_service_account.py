"""A Google service-account key, and an OAuth access token minted from it
for one API scope. Shared by everything in the fork that speaks to Google as
the app's owner: the Play purchase verifier (iap/google.py, the
androidpublisher scope) and the FCM push sender (push/fcm.py, the
firebase.messaging scope). Tokens are good for an hour; cached per
(account, scope)."""

from __future__ import annotations

import base64
import json
import time

import httpx
import jwt

from app.core.errors import AppHTTPException

_TOKEN_URL = "https://oauth2.googleapis.com/token"

_token_cache: dict[tuple[str, str], tuple[str, float]] = {}


def load_service_account(b64: str, env_name: str) -> dict:
    """The decoded key file. `env_name` names the setting in the error, so a
    mis-pasted credential says which one."""
    try:
        sa = json.loads(base64.b64decode(b64))
        assert sa["client_email"] and sa["private_key"]
        return sa
    except Exception as e:
        raise AppHTTPException(500, f"{env_name} is not a base64-encoded service-account JSON") from e


async def access_token(sa: dict, scope: str) -> str:
    key = (sa["client_email"], scope)
    cached = _token_cache.get(key)
    if cached and cached[1] > time.time() + 60:
        return cached[0]

    now = int(time.time())
    assertion = jwt.encode(
        {"iss": sa["client_email"], "scope": scope, "aud": _TOKEN_URL, "iat": now, "exp": now + 3600},
        sa["private_key"],
        algorithm="RS256",
    )
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            _TOKEN_URL,
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        )
    if res.status_code != 200:
        raise AppHTTPException(
            502,
            f"Google token exchange failed ({res.status_code}) — check the service account "
            f"has access to what it is used for: {res.text[:200]}",
        )
    token = res.json()["access_token"]
    _token_cache[key] = (token, time.time() + 3300)
    return token
