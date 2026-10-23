"""
JWT minters for backend function calls and automation invocations.

Two service-token shapes — both signed with SERVICE_JWT_SECRET, HS256:

1. **Proxy invocations** (`mint_for_proxy(function_name)`) — issued when an
   SDK/HTTP caller invokes a function via `/api/functions/<name>`. Carries
   the per-invocation pair `backend_function_invocation_id` (uuid4().hex)
   and `backend_function_name`. 9 claims total.

   Shape captured from Base44 production function-proxy probes (functions
   agent, 2026-05-20):
   { sub, client_id, app_id, aud: "base44_api", scope: "app.access",
     exp, iat, backend_function_invocation_id, backend_function_name }

2. **Automation invocations** (`mint_for_automation()`) — issued when an
   automation (entity or scheduled) fires. Base44 does NOT include
   `backend_function_*` claims here; the call is not tied to a specific
   SDK invocation (verified 2026-05-21 against entity + scheduled automation
   payloads on auto-pulse-lab.base44.app). 7 claims total.

   Shape captured live:
   { sub, client_id, app_id, aud: "base44_api", scope: "app.access",
     exp, iat }

Both keep `exp` before `iat` in dict-insertion order to match Base44's wire
ordering byte-for-byte (the JWT payload is order-sensitive at the base64
layer, so this matters for any future signature-snapshot tests).

Also mints:
- **`base44-state` tokens** (`mint_state_token(settings)`) — `{app_id, exp}`,
  ~5 min TTL. Used as the `Base44-State` header on automation invocations.
- **Creator tokens** (`mint_creator_token(settings, email)`) — `{sub: email,
  iat, exp+90d}`. Signed with APP_JWT_SECRET (not SERVICE_JWT_SECRET) —
  these are app_user tokens identifying the human creator of an automation.
  Sent as the `Authorization: Bearer ...` header on automation calls so the
  function's `base44.auth.me()` returns the automation's creator (per docs:
  "When an automation runs, the request is authenticated as the user who
  created the automation, not as the user who performed the action.").
"""

import time
from uuid import uuid4

import jwt


def mint_for_proxy(settings, *, function_name: str) -> str:
    """Per-invocation service JWT for backend-function proxy calls."""
    now = int(time.time())
    payload = {
        "sub": settings.SERVICE_PRINCIPAL_ID,
        "client_id": settings.SERVICE_PRINCIPAL_ID,
        "app_id": settings.APP_ID,
        "aud": "base44_api",
        "scope": "app.access",
        "exp": now + 3600,
        "iat": now,
        "backend_function_invocation_id": uuid4().hex,
        "backend_function_name": function_name,
    }
    return jwt.encode(payload, settings.SERVICE_JWT_SECRET, algorithm="HS256")


def mint_for_automation(settings) -> str:
    """Per-fire service JWT for automation invocations (entity + scheduled).

    Distinct from `mint_for_proxy` — Base44 production omits the
    `backend_function_*` claims for automation calls (verified live).
    """
    now = int(time.time())
    payload = {
        "sub": settings.SERVICE_PRINCIPAL_ID,
        "client_id": settings.SERVICE_PRINCIPAL_ID,
        "app_id": settings.APP_ID,
        "aud": "base44_api",
        "scope": "app.access",
        "exp": now + 3600,
        "iat": now,
    }
    return jwt.encode(payload, settings.SERVICE_JWT_SECRET, algorithm="HS256")


def mint_state_token(settings) -> str:
    """Short-lived `Base44-State` token sent with every automation call.

    Payload `{app_id, exp}` with ~5 min TTL — matches Base44 prod.
    """
    now = int(time.time())
    payload = {
        "app_id": settings.APP_ID,
        "exp": now + 300,
    }
    return jwt.encode(payload, settings.SERVICE_JWT_SECRET, algorithm="HS256")


def mint_creator_token(settings, email: str) -> str:
    """Mint the automation-creator's app_user JWT for the Authorization header.

    Signed with APP_JWT_SECRET (the same secret /auth/login mints with), so
    the function-side `createClientFromRequest` SDK accepts it and
    `base44.auth.me()` returns the creator user. Payload matches a normal
    app_user token shape (verified live: `{sub: email, iat, exp+90d}`,
    nothing else).

    Per Base44's automation contract, the creator token is freshly minted
    per fire — `iat` is `now`, so two fires of the same automation produce
    different tokens.
    """
    now = int(time.time())
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + 7776000,  # 90 days, matching observed Base44 creator tokens
    }
    return jwt.encode(payload, settings.APP_JWT_SECRET, algorithm="HS256")


def mint_workflow_service_token(settings, *, workflow_id: str, run_id: str, hop_depth: int) -> str:
    """Service JWT for workflow-invoked backend functions.

    The measured workflow wire carries BOTH a service token and an app-user
    token (H §6.2 of the workflows chase); Base44's exact claim sets were not
    captured (only token lengths), so the base shape is the automation
    service token, plus our `wf_*` claims — the carrier for the measured
    cascade rules (H §14.6): the entity dispatcher reads them to suppress
    re-triggering the workflow that wrote the row and to cap `_hop_depth` at
    5. The SDK treats the token as opaque, so the extra claims are inert to
    user code.
    """
    now = int(time.time())
    payload = {
        "sub": settings.SERVICE_PRINCIPAL_ID,
        "client_id": settings.SERVICE_PRINCIPAL_ID,
        "app_id": settings.APP_ID,
        "aud": "base44_api",
        "scope": "app.access",
        "exp": now + 3600,
        "iat": now,
        "wf_workflow_id": workflow_id,
        "wf_run_id": run_id,
        "wf_hop_depth": hop_depth,
    }
    return jwt.encode(payload, settings.SERVICE_JWT_SECRET, algorithm="HS256")


def mint_workflow_creator_token(settings, email: str, *, workflow_id: str, run_id: str, hop_depth: int) -> str:
    """The app-user (creator) token a workflow call carries — `auth.me()`
    inside the function resolves to the app owner (H §6.2). Same base shape
    as `mint_creator_token`, plus the `wf_*` cascade claims (see
    `mint_workflow_service_token`); non-asServiceRole writes from the
    function carry THIS token, so both write paths propagate workflow
    origin."""
    now = int(time.time())
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + 7776000,
        "wf_workflow_id": workflow_id,
        "wf_run_id": run_id,
        "wf_hop_depth": hop_depth,
    }
    return jwt.encode(payload, settings.APP_JWT_SECRET, algorithm="HS256")


def validate_state_token(token: str, settings) -> dict | None:
    try:
        return jwt.decode(token, settings.SERVICE_JWT_SECRET, algorithms=["HS256"])
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None


# Backwards-compat alias so the functions module's proxy code (which still
# imports `mint`) doesn't break in the same commit. It's the 9-claim path.
def mint(settings, *, function_name: str) -> str:
    return mint_for_proxy(settings, function_name=function_name)
