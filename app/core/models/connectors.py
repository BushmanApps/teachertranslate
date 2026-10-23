"""Connectors module wire-shape models.

The connectors module is **deliberately divergent from Base44 at the
implementation level** — we run our own OAuth state machine
(`_connector_configs`, `_connector_pending`, `_connector_tokens`) while
Base44 runs a config-driven registry + one generic OAuth engine (their
May-era Composio brokering is gone from new dances — it survives only as
a legacy-state fallback on their callback, measured 2026-08-28). The
wire shapes here DO mirror Base44's so SDK consumers see the same contract.

There is deliberately NO integration-type enum here. Base44 dropped its
Literal validation between May and August 2026 (D-021 recorded the
literal_error in May; on 2026-08-28 the same probes return registry-lookup
404s — "Unknown integration type: {t}" on initiate/status, and the vend
path doesn't type-check at all). Their registry adds types weekly
(41 of 82 current types postdate our May snapshot), so any frozen list
here is guaranteed stale — validation is by config lookup, matching their
current mechanism. Probes: research/divergence-chasing/
2026-08-28-connectors-registry/.

Status enum is PENDING/ACTIVE/FAILED with `status_reason` — measured
2026-08-28 (error-callback replay: `{"status":"FAILED","reporting_fields":{},
"status_reason":"OAuth provider returned access_denied: User denied access"}`;
the enum confirmed against Base44's own CLI zod schema). May's
ERROR/error/error_message shape is dead.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class InitiateAppBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Plain str — unknown types 404 at the config lookup (see module
    # docstring), exactly like Base44's registry lookup does today.
    integration_type: str
    scopes: list[str] = Field(default_factory=list)
    force_reconnect: bool = False
    connection_config: Optional[dict] = None


class InitiateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    redirect_url: Optional[str] = None
    connection_id: Optional[str] = None
    # Echoed back on Base44's initiate response (measured 2026-08-28).
    integration_type: Optional[str] = None
    already_authorized: bool = False
    error: Optional[str] = None
    error_message: Optional[str] = None
    other_user_email: Optional[str] = None


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["PENDING", "ACTIVE", "FAILED"]
    reporting_fields: dict = Field(default_factory=dict)
    # Emitted as an explicit null when absent (Base44 wire, 2026-08-28).
    status_reason: Optional[str] = None


# PROBE_GAP: the success-path response shape for connector token vending is
# taken from our own handler — the endpoint is service-role-gated and the
# research couldn't synthesize a service token to probe it. If wire diffs
# surface, the implementor should NOT invent a different shape; flag and ask.
class TokenVendResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
    integration_type: str
    connection_config: Optional[dict] = None
