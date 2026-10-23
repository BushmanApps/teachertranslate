"""
Token classification.

Given a request's Authorization header, determine the token class:
- "anonymous" — no Authorization header
- "app_user" — JWT signed with APP_JWT_SECRET (payload: {sub: user_email, ...})
- "service_role" — JWT signed with SERVICE_JWT_SECRET (payload:
  {sub: client_id, client_id, app_id, aud:"base44_api",
  scope:"app.access", backend_function_invocation_id,
  backend_function_name, iat, exp}). Probed F-034 against B44 production
  (2026-05-23 via deployed dump_headers function): B44 only honors
  service tokens in `Authorization: Bearer`, NOT in
  `Base44-Service-Authorization`. The Base44-Service-Authorization header
  is what B44 INJECTS into outbound backend-function invocations; the
  SDK's `createClientFromRequest` reads it from the function's incoming
  request and re-emits it as `Authorization: Bearer` on subsequent
  callbacks. We do not honor `Base44-Service-Authorization` inbound.
- "platform" — Bearer JWT that's not app_user/service_role/preview
  (e.g. Base44 CLI/dashboard token, payload aud:"platform"). Does NOT
  act as a runtime user. Behaves like anonymous on entity endpoints.
  Exists for SDK wire compatibility.
- "preview" — JWT signed with APP_JWT_SECRET, payload impersonated: true

Returns the token class and decoded payload (if any).

Classification order on a Bearer-extracted token: try APP_JWT_SECRET
(app_user, or preview if impersonated). Then try SERVICE_JWT_SECRET
(service_role). Otherwise → platform.

See security.md for the full specification of each token class.
"""

from __future__ import annotations

from typing import Literal

from app.core.security.tokens import (
    try_decode_app_token,
    try_decode_service_token,
)


TokenClass = Literal["anonymous", "app_user", "service_role", "platform", "preview"]


def classify_headers(authorization: str | None, settings) -> tuple[TokenClass, dict | None]:
    # F-034 (probed 2026-05-23 paired against B44 with deployed
    # dump_headers function): B44 only honors service tokens via
    # `Authorization: Bearer`. Inbound `Base44-Service-Authorization`
    # alone returns 403 visibility-deny — same as anon — so it is not read.
    token = _extract_bearer_token(authorization)
    if not token:
        return "anonymous", None

    app_payload = try_decode_app_token(token, settings)
    if app_payload is not None:
        if app_payload.get("impersonated") is True:
            return "preview", app_payload
        return "app_user", app_payload

    service_payload = try_decode_service_token(token, settings)
    if service_payload is not None:
        return "service_role", service_payload

    return "platform", None


def _extract_bearer_token(header_value: str | None) -> str | None:
    if not header_value:
        return None

    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    return token
