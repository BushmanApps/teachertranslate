"""Engine-owned scheduling for workflow triggers — the tick's brain.

Provider cron cannot host per-workflow schedules faithfully: pg_cron runs in
ONE database timezone (real blocked apps schedule in LA/London/Vienna/
Johannesburg/Vancouver — H §8.0), cannot count `ends_after_count`, and knows
nothing about interval anchoring. So scheduling lives HERE, and the provider
carries exactly one dumb job per app: a minutely poke of
/api/internal/workflows/tick (the trigger/payload split the automations path
already proved in production).

Measured semantics (H §14.2):
- `recurring`: the cron expression, evaluated in the trigger's IANA timezone;
- `interval`: WALL-CLOCK ALIGNED, not creation-anchored (a 5-minute interval
  created at :28 first fired at :30:07) — implemented as the equivalent cron
  so both modes share one code path;
- `one_time`: fires once; the stored datetime is NAIVE and the separate
  `timezone` field locates it (H §14.2 — do not assume it carries an offset);
- a schedule that reaches its end — one_time after firing, `after_count`
  after N fires, `on_date` past the date — is ARCHIVED automatically with
  `status_reason: "end_condition_reached"`;
- a 1-minute tick sits comfortably inside Base44's own observed precision
  (their 60s wait measured 92s and 130s; their scheduled fires drifted 0-11s).

Fire claiming is CAS-style on the stored `next_fire_at`, so concurrent ticks
(overlapping pg_cron pokes, a VPS + a stray manual tick) can never double-fire
one slot.
"""

import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pymongo import ReturnDocument

from app.core import db

from .engine import WORKFLOWS, advance_run, create_run, sweep_due_runs

logger = logging.getLogger("escapebase44.workflows")

_UNITS_TO_CRON = {
    # Interval mode as its aligned-cron equivalent. Day intervals step the
    # day-of-month (cron semantics restart each month) — Base44's behaviour at
    # a month boundary is unmeasured; within a month this matches the measured
    # wall-clock alignment.
    "minutes": lambda n: f"*/{n} * * * *",
    "hours": lambda n: f"0 */{n} * * *",
    "days": lambda n: f"0 0 */{n} * *",
}


def compute_next_fire(config: dict, *, after: datetime) -> datetime | None:
    """Next fire time (naive UTC) strictly after `after` (naive UTC), or None
    when the schedule has nothing left to fire. End conditions are enforced by
    the sweep, not here — this is pure schedule arithmetic."""
    from croniter import croniter  # lazy — the `workflows` optional extra

    mode = config.get("schedule_mode")
    tz = ZoneInfo(config.get("timezone") or "UTC")

    if mode == "one_time":
        raw = config.get("one_time_date")
        if raw is None:
            return None
        when = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if when.tzinfo is None:
            # Stored naive; the `timezone` field locates it (H §14.2).
            when = when.replace(tzinfo=tz)
        when_utc = when.astimezone(timezone.utc).replace(tzinfo=None)
        return when_utc if when_utc > after else None

    if mode == "interval":
        unit = config.get("interval_unit")
        value = config.get("interval_value")
        if unit not in _UNITS_TO_CRON or not value:
            return None
        expr = _UNITS_TO_CRON[unit](int(value))
    else:  # recurring
        expr = config.get("cron_expression")
        if not expr:
            return None

    after_local = after.replace(tzinfo=timezone.utc).astimezone(tz)
    try:
        nxt = croniter(expr, after_local).get_next(datetime)
    except (ValueError, KeyError) as e:
        logger.warning("unschedulable cron '%s': %s", expr, e)
        return None
    return nxt.astimezone(timezone.utc).replace(tzinfo=None)


async def ensure_schedule_state(workflow: dict, *, now: datetime) -> None:
    """Give an active scheduled workflow its next_fire_at if it lacks one —
    called at seed/reconcile time and on activation/unarchive."""
    config = (workflow.get("trigger") or {}).get("config") or {}
    if config.get("trigger_type") != "scheduled" or workflow.get("status") != "active":
        return
    state = workflow.get("schedule_state") or {}
    if state.get("next_fire_at") is not None:
        return
    await db.coll(WORKFLOWS).update_one(
        {"_id": workflow["_id"]},
        {"$set": {"schedule_state": {
            "next_fire_at": compute_next_fire(config, after=now),
            "fire_count": state.get("fire_count", 0),
        }}},
    )


async def sweep_due_schedules(*, now: datetime) -> int:
    """Fire every due schedule. Returns the number of runs created."""
    fired = 0
    cursor = db.coll(WORKFLOWS).find({
        "status": "active",
        "trigger.config.trigger_type": "scheduled",
        "schedule_state.next_fire_at": {"$lte": now},
    })
    async for workflow in cursor:
        config = workflow["trigger"]["config"]
        state = workflow.get("schedule_state") or {}
        due_at = state.get("next_fire_at")
        fire_count = state.get("fire_count", 0)

        ends_type = config.get("ends_type") or "never"
        ends_after = config.get("ends_after_count")
        is_last_allowed = (
            config.get("schedule_mode") == "one_time"
            or (ends_type == "after_count" and ends_after is not None
                and fire_count + 1 >= int(ends_after))
        )
        next_fire = None if is_last_allowed else compute_next_fire(config, after=max(now, due_at))
        if ends_type == "on_date" and next_fire is not None:
            ends_on = config.get("ends_on_date")
            if ends_on is not None:
                tz = ZoneInfo(config.get("timezone") or "UTC")
                edge = ends_on if isinstance(ends_on, datetime) else datetime.fromisoformat(
                    str(ends_on).replace("Z", "+00:00"))
                if edge.tzinfo is None:
                    edge = edge.replace(tzinfo=tz)
                if next_fire > edge.astimezone(timezone.utc).replace(tzinfo=None):
                    next_fire = None

        # CAS on the stored next_fire_at: whoever flips it owns this fire.
        update: dict = {
            "$set": {"schedule_state.next_fire_at": next_fire},
            "$inc": {"schedule_state.fire_count": 1},
        }
        claimed = await db.coll(WORKFLOWS).find_one_and_update(
            {"_id": workflow["_id"], "status": "active",
             "schedule_state.next_fire_at": due_at},
            update,
            return_document=ReturnDocument.AFTER,
        )
        if claimed is None:
            continue  # another tick owns this fire

        try:
            await create_run(
                claimed,
                trigger_type="scheduled",
                trigger_payload={},  # measured: scheduled runs get trigger {} (H §13.6)
            )
            # Deliberately NOT kicked: the tick's own sweep_due_runs (below)
            # picks this run up microseconds later and advances it
            # SYNCHRONOUSLY inside this same invocation. That is what makes
            # scheduled execution correct on serverless, where a kicked task
            # would be frozen when the tick's response returns.
            fired += 1
        except Exception:
            logger.debug("scheduled fire failed for '%s' (non-fatal)",
                         claimed.get("name"), exc_info=True)

        if next_fire is None:
            # A finished schedule archives itself, machine-readably (H §14.2).
            await db.coll(WORKFLOWS).update_one(
                {"_id": claimed["_id"], "status": "active"},
                {"$set": {"status": "archived", "status_reason": "end_condition_reached"}},
            )
    return fired


# How long the tick may keep STARTING new runs. The host kills the invocation
# at its own maxDuration (Vercel: 60s Hobby / 300s Pro by default), and being
# killed mid-call is the one outcome we cannot recover from — the run sits in
# `invoking` with an expired lease and gets failed even though its function may
# have executed. So the tick stops taking on new work well before any plausible
# platform ceiling; whatever it did not start stays due and the next minute
# continues. A single run that overruns on its own is still exposed, which is
# why CALL_TIMEOUT is the engine's, not the platform's, problem to bound.
TICK_START_BUDGET_S = 45.0


async def tick() -> dict:
    """One heartbeat: fire due schedules, then advance every due run. Called by
    /api/internal/workflows/tick (pg_cron, minutely).

    On serverless this is the ONLY executor (kick() is a no-op there — see
    engine.kick), which is why every advance here is AWAITED: work this
    function starts, this function finishes, or leaves cleanly for the next
    tick. No fire-and-forget, ever."""
    started = time.monotonic()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fired = await sweep_due_schedules(now=now)
    from .connectors import poll_connector_triggers
    fired += await poll_connector_triggers()
    # The push door's inbox (slack, outlook, …): the door verifies and stores,
    # the tick fans out — the response has to be fast and the container freezes
    # when it is sent (core/workflows/push.py). Owning-side subscriptions
    # (Graph's) are created and renewed here too.
    from .push import drain_push_inbox, ensure_push_subscriptions
    from app.core import addresses
    try:
        base = await addresses.canonical_base_url()
        await ensure_push_subscriptions(lambda integration: f"{base}/api/connector-events/{integration}")
    except Exception:
        logger.debug("push subscription ensure failed (next tick retries)", exc_info=True)
    fired += await drain_push_inbox()
    # Includes the runs sweep_due_schedules just created — they are due now.
    due = await sweep_due_runs()
    advanced = 0
    for run_id in due:
        # Sequential on purpose: the tick is a budgeted worker, not a fan-out —
        # anything it doesn't finish stays due and the next tick continues.
        # Base44 runs same-workflow runs concurrently (H §14.10); on a VPS that
        # concurrency comes from kick() at trigger time, and the tick is the
        # serial safety net.
        if time.monotonic() - started > TICK_START_BUDGET_S:
            logger.info("tick budget spent with %d run(s) still due; next tick continues",
                        len(due) - advanced)
            break
        try:
            await advance_run(run_id)
            advanced += 1
        except Exception:
            logger.debug("tick advance failed for run %s (non-fatal)", run_id, exc_info=True)
    return {"fired": fired, "advanced": advanced, "deferred": len(due) - advanced}
