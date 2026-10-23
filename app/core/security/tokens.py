"""
JWT encode/decode — to be implemented by the security agent.

Handles:
- Decoding and verifying app-user JWTs (signed with APP_JWT_SECRET)
- Decoding and verifying service-role JWTs (signed with SERVICE_JWT_SECRET)
- Encoding app-user JWTs (for auth endpoints: login, verify-otp, etc.)
  Payload: {sub: user_email, iat, exp}. Expiry: settings.APP_TOKEN_TTL_SECONDS
  (90 days by default — Base44 parity; 24 h on HIPAA deployments). Algorithm: HS256.

See security.md for token payload shapes.
"""

from __future__ import annotations

import time

import jwt
from jwt import InvalidTokenError



def decode_app_token(token: str, settings) -> dict:
    payload = jwt.decode(
        token,
        settings.APP_JWT_SECRET,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("sub"), str):
        raise InvalidTokenError("Invalid app token payload")
    return payload


def try_decode_app_token(token: str, settings) -> dict | None:
    try:
        return decode_app_token(token, settings)
    except InvalidTokenError:
        return None


def decode_service_token(token: str, settings) -> dict:
    payload = jwt.decode(
        token,
        settings.SERVICE_JWT_SECRET,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    subject = payload.get("sub") or payload.get("client_id")
    if not isinstance(payload, dict) or not isinstance(subject, str):
        raise InvalidTokenError("Invalid service token payload")
    return payload


def try_decode_service_token(token: str, settings) -> dict | None:
    try:
        return decode_service_token(token, settings)
    except InvalidTokenError:
        return None


def encode_app_token(user_email: str, settings) -> str:
    # Payload key order matches Base44 wire (probed 2026-05-21 session 4):
    # Base44 emits {sub, exp, iat}; we previously emitted {sub, iat, exp}.
    # JWT spec is order-insensitive but byte-parity diff needs the match.
    now = int(time.time())
    payload = {
        "sub": user_email,
        "exp": now + settings.APP_TOKEN_TTL_SECONDS,
        "iat": now,
    }
    return jwt.encode(payload, settings.APP_JWT_SECRET, algorithm="HS256")
