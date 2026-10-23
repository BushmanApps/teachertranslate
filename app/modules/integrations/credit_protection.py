"""Credit protection — Base44's switch against the browser spending the owner's
model and email credits (`control_core_integrations` on the app record; the
security scan's "Prevent unauthorized credit usage" fix, on by default for new
apps since 2026-09; 152 of 353 apps on 2026-09-28).

Measured 2026-09-28 (research/divergence-chasing/2026-09-28-parity-audit,
probe 18 — every caller, every Core integration, the gateway):

- With the switch on, a credit-spending integration is refused to EVERY
  caller but the service role — a visitor, a signed-in user, the app's owner,
  and a backend function calling through its caller's own client — with a 403
  that names the integration and `core_integration_not_allowed`. The service
  role (`asServiceRole` inside a backend function) passes to validation.
- What spends credits: the eight below and the AI gateway (as `AIGateway`).
  The four file integrations (UploadFile, UploadPublicFile, UploadPrivateFile,
  CreateFileSignedUrl) spend none and stay open; so does the gateway's model
  list.
- Order: on a Core route the refusal precedes body validation (an empty body
  is refused, never 422'd); on the gateway it follows the body's `model`
  (an empty body is 400 "Field required" param model) and precedes every
  other check (an empty `messages`, an unknown model, `stream: true` are all
  refused first).
- `allowed_core_integrations` names exceptions; Base44 refuses to write it
  through the app API and every app holds `[]` — honoured as read.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.errors import AppError
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_app_settings

CREDIT_SPENDING = frozenset({
    "InvokeLLM", "GenerateImage", "GenerateVideo", "GenerateSpeech",
    "SendEmail", "SendPushNotification", "TranscribeAudio", "ExtractDataFromUploadedFile",
})
AI_GATEWAY = "AIGateway"


def refused(ctx: AuthedContext, app_settings: dict, integration: str) -> bool:
    if ctx.token_class == "service_role" or not app_settings.get("control_core_integrations"):
        return False
    return integration not in (app_settings.get("allowed_core_integrations") or [])


def refusal_message(integration: str) -> str:
    return (
        f"Core integration '{integration}' is blocked from direct app-runtime calls. "
        "This is a routing restriction, not an enablement or billing issue; "
        "call it from a backend function using its supported service-role API."
    )


async def guard_core(
    request: Request,
    ctx: AuthedContext = Depends(get_authed_context),
    app_settings: dict = Depends(get_app_settings),
) -> None:
    """The Core router's gate: the integration is the route's last path
    segment; a dependency runs before the body is read, as measured."""
    integration = request.url.path.rsplit("/", 1)[-1]
    if integration in CREDIT_SPENDING and refused(ctx, app_settings, integration):
        raise AppError(
            403, refusal_message(integration),
            extra_data={
                "app_id": request.path_params["app_id"],
                "integration_name": integration,
                "reason": "core_integration_not_allowed",
            },
        )
