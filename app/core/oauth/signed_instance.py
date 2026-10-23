"""Verify a provider's signed payload of the form `<sig>.<data>` — base64url
HMAC-SHA256 over the base64url data, keyed by the app secret, no padding
(Wix's `signedInstance` on its external-install callback; the same scheme
Wix uses for its `instance` query parameter). Returns the decoded payload or
None; a payload is never trusted before this returns it."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_signed_instance(value: str, secret: str) -> dict | None:
    sig_b64, _, data_b64 = value.partition(".")
    if not sig_b64 or not data_b64:
        return None
    try:
        sig = _b64url_decode(sig_b64)
        payload = json.loads(_b64url_decode(data_b64))
    except Exception:
        return None
    expected = hmac.new(secret.encode(), data_b64.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    return payload if isinstance(payload, dict) else None
