"""Internal trigger endpoint for scheduled automations.

NOT a Base44 API. This is migration-internal infrastructure: the cron infra
(pg_cron on Supabase, Deno.cron on Deno Deploy) pokes this endpoint when a
schedule ticks, and we centralize all the actual payload construction here
(via `app.core.automations.dispatch_scheduled`) so scheduled and entity
automations share one code path.

Base44 has no equivalent — their scheduled-task worker calls the function
URL directly with a fully-constructed payload. We instead put the payload
construction on our migrated backend (one source of truth) and use the
cron infra purely as a trigger.

Authentication is a shared secret (`EB44_CRON_SECRET`), set on both this
backend's env and on the cron-side (pg_cron job SQL header or Deno.cron
handler env). The endpoint refuses any request missing or mismatching this
header.
"""

from fastapi import APIRouter, Depends, Header, Request

from app.config import Settings
from app.core.automations import dispatch_scheduled
from app.core.errors import AppError
from app.core.internal_auth import check_cron_secret
from app.deps import get_settings

router = APIRouter(prefix="/api/internal", tags=["automations-internal"])


@router.post("/fire-automation/{automation_id}")
async def fire_scheduled_automation(
    automation_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    x_eb44_cron_secret: str | None = Header(default=None, alias="X-Eb44-Cron-Secret"),
) -> dict:
    """Trigger one scheduled automation by id.

    Returns 204-like empty `{ok: true}` on success or skip (inactive, not
    found, function not deployed). Doesn't expose which of those happened —
    the caller is dumb cron infra that has no way to recover from a 404.
    """
    check_cron_secret(x_eb44_cron_secret, settings.EB44_CRON_SECRET)

    try:
        fired = await dispatch_scheduled(automation_id)
    except AppError:
        raise
    except Exception:
        # Any unexpected exception is swallowed for the cron — Base44's
        # behavior is to mark `consecutive_failures` and retry on the next
        # tick. We log via `core.automations` and return ok=False.
        fired = False

    return {"ok": fired}


