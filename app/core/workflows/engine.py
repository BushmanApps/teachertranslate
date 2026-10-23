"""The workflow execution engine — a resumable state machine, not a coroutine.

The fork has NO background process of any kind (verified: main.py's lifespan
does db/registry/providers init and nothing else — H §8b.2), so a run is
persisted state in the user's own Mongo, advanced by whoever holds its lease:
the internal tick (pg_cron → /api/internal/workflows/tick, the only guaranteed
executor) or an opportunistic in-process task right after a trigger fires.

Measured semantics implemented here (H = research/divergence-chasing/
2026-08-19-workflows/HANDOFF.md):

- one fire = one run = one attempt; there is NO in-run retry (H §13.5);
- any non-2xx function response fails the run; failure text is uniformly
  `Task '<name>' failed: <reason>` (H §14.4, §14.3);
- output binding is ALWAYS an object: JSON objects bind verbatim, any other
  JSON value wraps as {"result": v}, non-JSON text wraps as
  {"raw_response": text}, an empty body binds {} (H §14.4);
- step outputs bind at the jq root under the step name; run metadata rides
  `_`-prefixed keys; `trigger` holds the trigger payload (H §4.2);
- `_run_id` in the CONTEXT is an empty string on scheduled runs and the real
  UUID elsewhere — replicated: an expression reading it behaves differently
  by trigger type on Base44 (H §13.6);
- switch: cases in order, first jq-truthy wins; a jq runtime error in `when`
  fails the run at the switch task (H §14.5);
- `then: "end"` is terminal and wins over a task literally named "end"
  (H §14.5); the interpreter carries Base44's 10,000-step cap (H §14.5);
- steps_count counts successfully-completed steps (H §6.4, §13.5);
  entity-triggered runs carry a synthetic `__trigger__` ledger row not
  counted in steps_count (H §14.6);
- the step ledger is append-only, two rows per step (started +
  completed/failed), input_data/output_data always null — Base44 does not
  persist step I/O there and neither do we; the run's context document is the
  engine's real data plane (H §6.3);
- auto-deactivate after 5 consecutive failures for scheduled workflows, 50
  for every other trigger type, `status_reason: "consecutive_failures"`
  (H §7b, §13.5);
- cancellation is two-phase (`cancelling` → settled), interrupts a durable
  wait, is idempotent on terminal runs, and a cancelled run counts in
  NEITHER total_runs NOR consecutive_failures (H §14.7);
- `total_runs` counts only terminal non-cancelled runs (H §14.10);
- credits_consumed is 0 on every run this engine creates — there are no
  credits outside Base44; imported history keeps its recorded values;
- send_email (chase 2026-08-31-new-workflow-triggers §5): the template is
  the app's own (`base44/emails/<template_name>.html`, read at send time and
  rendered by core/email_templates.py — the registry and the renderer Core
  SendEmail uses), From-name = the app's display name; test runs DRY-RUN
  ({"dry_run": true, "sent": false, "to"}) and real fires bind
  {"sent": true, "to"}; a missing template fails the run with Base44's
  exact 404 message.

CRASH SEMANTICS (ours, documented divergence): a run interrupted by process
death mid-safe-step (wait, between steps) is resumed by the tick when its
lease expires. A run whose lease expires mid-FUNCTION-CALL is FAILED with an
explicit error — the call may or may not have executed, and re-executing a
side effect (an email, a charge) is worse than a visible failure that the
consecutive-failures machinery surfaces. Base44's platform survives its own
restarts invisibly; ours trades that, rarely, for never double-firing.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import orjson
from bson import ObjectId
from pymongo import ReturnDocument

from app.core import db
from app.core import addresses
from app.core import email_templates
from app.core.providers.email import build_email_provider
from app.core.functions.service_token import (
    mint_state_token,
    mint_workflow_creator_token,
    mint_workflow_service_token,
)

from .compiler import END, CompiledWorkflow, Task, compile_definition, expression_body, is_expression
from .contract import CONTRACT, RUNTIME_STEP_LIMIT
from .durations import WaitError, parse_wait
from .expressions import ExpressionError, evaluate, evaluate_args, is_truthy

logger = logging.getLogger("escapebase44.workflows")

WORKFLOWS = "_workflows"
VERSIONS = "_workflow_versions"
RUNS = "_workflow_runs"
STEPS = "_workflow_run_steps"

# No measured Base44 timeout below 200 s (H §14.4). The edge platform's own
# wall clock (Supabase Free: 150 s) is the real bound; ours just has to sit
# above it so WE never kill a call the platform would allow (AGENTS §2.17).
CALL_TIMEOUT_S = 210.0
# A wait at or below this executes inline (lease extended over it) instead of
# parking for the tick — sub-minute waits keep Base44-like fidelity. Longer
# waits persist `resume_at` and the tick resumes them.
INLINE_WAIT_MAX_S = 30.0
LEASE_SLACK_S = 30.0

# Aggregate vocabulary differs from run vocabulary: the workflow record says
# "success" where the run says "completed" (H §11.3); "cancelled" passes
# through (H §14.7). "failed" is assumed symmetric — its aggregate word was
# not captured, and no other value is coherent with the observed pair.
_AGGREGATE_STATUS = {"completed": "success", "failed": "failed", "cancelled": "cancelled"}

# Version documents are immutable (content-addressed — H §5), so this cache
# can never serve a stale plan.
_compiled_cache: dict[str, CompiledWorkflow] = {}


def _now() -> datetime:
    # Naive UTC — the fork's storage convention (`utcnow_naive` in
    # core/responses): motor is initialized without tz_aware, so BSON dates
    # round-trip naive and an aware datetime here would make every comparison
    # with a loaded document raise.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def workflow_key(workflow_id):
    if isinstance(workflow_id, ObjectId):
        return workflow_id
    try:
        return ObjectId(workflow_id)
    except Exception:
        return workflow_id


async def _compiled_for_version(version_id: str) -> CompiledWorkflow:
    cached = _compiled_cache.get(version_id)
    if cached is not None:
        return cached
    # Version DOCS are per-workflow (`{workflow_id, version_id, …}` — two
    # workflows with identical definitions each get their own record), but
    # the version_id is content-addressed, so ANY doc bearing it carries the
    # identical definition — lookup by version_id alone is safe.
    version = await db.coll(VERSIONS).find_one({"version_id": version_id})
    if version is None:
        raise RuntimeError(f"workflow version '{version_id}' not found")
    compiled = compile_definition(version["definition"], mode="import")
    _compiled_cache[version_id] = compiled
    return compiled


# ── run creation ──

async def create_run(
    workflow: dict,
    *,
    trigger_type: str,
    trigger_payload: dict,
    is_test_run: bool = False,
    hop_depth: int = 0,
    origin_run_id: str | None = None,
) -> str:
    """Insert a run in `running` state, due immediately. Returns the run id.

    The caller decides how it executes: `kick(run_id)` for opportunistic
    in-process advancement, or nothing — the tick claims any due run within a
    minute. Callers enforce the cascade rules BEFORE calling this (the entity
    adapter: same-workflow suppression + the depth-5 cap — H §14.6).
    """
    run_id = str(uuid4())
    now = _now()
    context_run_id = "" if trigger_type == "scheduled" else run_id  # H §13.6
    run = {
        "_id": run_id,
        "workflow_id": str(workflow["_id"]),
        "workflow_name": workflow["name"],
        "trigger_type": trigger_type,
        "status": "running",
        "status_reason": "",
        "error_message": "",
        "started_at": now,
        "completed_at": None,
        "duration_ms": None,
        "steps_count": 0,
        "is_test_run": is_test_run,
        "credits_consumed": 0,
        "definition_version_id": workflow["current_version_id"],
        "_engine": {
            "context_extra": {
                "trigger": trigger_payload,
                "_run_id": context_run_id,
                "_trigger_type": trigger_type,
                "_is_test_run": is_test_run,
                "_hop_depth": hop_depth,
            },
            "outputs": {},
            "cursor": None,  # None = start at the plan's first task
            "phase": "ready",  # ready | invoking | waiting | done
            "resume_at": now,
            "lease_until": None,
            "cancel_requested": False,
            "origin_run_id": origin_run_id,
            "steps_executed": 0,
            "waiting": None,
        },
    }
    await db.coll(RUNS).insert_one(run)
    if trigger_type in ("entity", "connector"):
        # Entity- and connector-triggered runs carry a synthetic completed
        # `__trigger__` row ahead of the first real task, not counted in
        # steps_count (H §14.6; connector: a customer's 200 captured runs,
        # 2026-09-02 — `task_name: __trigger__, task_type: trigger`). A
        # connector run's row carries the trigger payload as `input_data`
        # (every captured connector run; the task rows stay null).
        await _append_step(run, "__trigger__", "trigger", "completed", now, now, None,
                           input_data=trigger_payload if trigger_type == "connector" else None)
    return run_id


def kick(run_id: str) -> None:
    """Opportunistic in-process advancement — ONLY where the host can finish
    work after a response (Settings.EB44_BACKGROUND_TASKS, i.e. the VPS
    providers' long-lived uvicorn).

    On serverless it is a NO-OP, deliberately. Vercel freezes the container
    when the response is sent, so a fire-and-forget advance is suspended
    mid-HTTP-call; the next tick then finds an expired lease in `invoking` and
    fails a run whose function may well have executed (measured on a live
    deployment 2026-08-22 — scheduled runs failed this way and marched toward
    auto-deactivation). There, the minutely tick is the only executor: it
    advances synchronously, so a run is either finished inside one invocation
    or left cleanly due for the next. The cost is latency, bounded by one tick
    and inside Base44's own measured scheduling precision (a 60s wait of theirs
    ran 92s and 130s — H §14.3).

    Never awaited from request handlers either way: a workflow must not add
    latency or failure surface to the write that triggered it (§2.17)."""
    from app.deps import get_settings
    if not get_settings().EB44_BACKGROUND_TASKS:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(advance_run(run_id))
    task.add_done_callback(_log_kick_failure)


def _log_kick_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.debug("workflow kick failed (tick will pick the run up)", exc_info=exc)


# ── the state machine ──

class _TaskFailed(Exception):
    """Internal: a task-level failure; message becomes the run error."""


async def advance_run(run_id: str) -> None:
    """Claim the run and execute until it parks (long wait), finishes, fails,
    or is cancelled. Every step transition is persisted before the next step
    executes, so a resumed run continues exactly where the last one stopped."""
    run = await _claim(run_id)
    if run is None:
        return

    from app.deps import get_settings
    settings = get_settings()

    engine = run["_engine"]
    try:
        compiled = await _compiled_for_version(run["definition_version_id"])
    except Exception as e:
        await _fail_run(run, f"workflow version could not be loaded: {e}")
        return

    workflow = await db.coll(WORKFLOWS).find_one({"_id": workflow_key(run["workflow_id"])})
    creator_email = (workflow or {}).get("created_by") or ""
    legacy_origin = _legacy_origin_of(workflow)

    # Cancel wins before anything else — including before closing a parked
    # wait, whose interruption leaves its `started` ledger row unmatched (the
    # step did not complete; a cancelled run's steps_count counts only what
    # finished — H §14.7).
    if engine["cancel_requested"]:
        await _settle_cancel(run)
        return

    # A run parked in a wait whose resume time arrived: close the wait's
    # ledger row before continuing.
    if engine["phase"] == "waiting" and engine.get("waiting"):
        waiting = engine["waiting"]
        await _append_step(
            run, waiting["task"], "wait", "completed", waiting["started_at"], _now(), None
        )
        run["steps_count"] += 1
        engine["steps_executed"] += 1
        engine["cursor"] = waiting["then"]
        engine["phase"] = "ready"
        engine["waiting"] = None
        await _persist_progress(run)

    cursor = engine["cursor"] or compiled.first_task

    while True:
        if engine["cancel_requested"]:
            await _settle_cancel(run)
            return
        if cursor == END:
            await _complete_run(run)
            return
        if engine["steps_executed"] >= RUNTIME_STEP_LIMIT:
            # Base44's own interpreter backstop, leaked verbatim by its cycle
            # error (H §14.5).
            await _fail_run(run, f"workflow exceeded the {RUNTIME_STEP_LIMIT}-step limit")
            return

        task = compiled.tasks.get(cursor)
        if task is None:
            await _fail_run(run, f"Task '{cursor}' does not exist in this workflow version")
            return

        started_at = _now()
        await _append_step(run, task.name, task.type, "started", started_at, None, None)

        try:
            if task.type == "call":
                next_cursor = await _exec_call(run, task, settings, creator_email, started_at,
                                               legacy_origin=legacy_origin)
            elif task.type == "switch":
                next_cursor = _exec_switch_pick(run, task, settings, creator_email)
                await _mark_step_completed(run, task, started_at)
            else:
                next_cursor = await _exec_wait(run, task, settings, creator_email, started_at)
                if next_cursor is None:
                    return  # parked for the tick, or settled a cancel
        except _TaskFailed as failure:
            await _append_step(run, task.name, task.type, "failed", started_at, _now(), str(failure))
            await _fail_run(run, f"Task '{task.name}' failed: {failure}")
            return

        cursor = next_cursor
        engine["cursor"] = cursor
        await _persist_progress(run)


async def _mark_step_completed(run, task: Task, started_at: datetime) -> None:
    run["_engine"]["steps_executed"] += 1
    run["steps_count"] += 1
    await _append_step(run, task.name, task.type, "completed", started_at, _now(), None)


async def _exec_call(run, task: Task, settings, creator_email: str, started_at: datetime,
                     *, legacy_origin: dict | None = None) -> str:
    context = _build_context(run, settings, creator_email)
    try:
        if task.activity == "compute_seconds_until":
            output = _compute_seconds_until(evaluate_args(task.with_args, context))
        elif task.activity == "send_email":
            output = await _send_email(run, evaluate_args(task.with_args, context), settings)
        else:
            args = evaluate_args(task.with_args, context)
            output = await _invoke_backend_function(run, task, args, settings, creator_email,
                                                   legacy_origin=legacy_origin)
    except ExpressionError as e:
        raise _TaskFailed(str(e))

    run["_engine"]["outputs"][task.name] = output
    await _mark_step_completed(run, task, started_at)
    return task.then


def _legacy_origin_of(workflow: dict | None) -> dict | None:
    """The automation this workflow was CONVERTED from, or None.

    Base44 batch-converts an app's legacy automations into workflows (a wave
    measured 2026-09-06..09; every converted automation carries
    `migrated_workflow_ref` and is left inactive) and keeps handing the
    resulting workflow's function the LEGACY AUTOMATION BODY, even though the
    converted definition declares `args` — measured both ways, 2026-09-17/27
    (see `legacy_automation_body`). The migration records the origin on the
    seeded workflow as `legacy_origin: {automation_id, version_id}`.

    The origin is PINNED to the definition version it was measured against:
    once the owner edits the definition, reconcile mints a new
    `current_version_id`, the pin stops matching, and the workflow gets plain
    workflow semantics (evaluated args verbatim) — which is what a
    freshly-authored definition means and what every native workflow gets.
    Nothing to un-special-case later.
    """
    origin = (workflow or {}).get("legacy_origin")
    if not isinstance(origin, dict) or not origin.get("automation_id"):
        return None
    if origin.get("version_id") != (workflow or {}).get("current_version_id"):
        return None
    return origin


async def _legacy_automation_entry(automation_id: str) -> dict | None:
    """The seeded automation entry the origin points at (`_function_configs`,
    written by the same migration that seeded the workflow)."""
    async for func_config in db.coll("_function_configs").find():
        for auto in func_config.get("automations", []):
            if str(auto.get("id", "")) == str(automation_id):
                return auto
    return None


def _legacy_body_kwargs(trigger: dict) -> dict:
    """The trigger payload, in the argument shape the legacy body builder
    takes. Entity payload keys are H §13.1's; the connector event is the
    documented envelope's."""
    return {
        "op": trigger.get("event_type"),
        "entity_name": trigger.get("entity_name"),
        "row": trigger.get("data") if isinstance(trigger.get("data"), dict) else None,
        "old_data": trigger.get("old_data"),
        "connector_event": {
            "type": trigger.get("event_type", ""),
            "integration_type": trigger.get("integration_type", ""),
            "provider_identifier": trigger.get("provider_identifier", ""),
            "data": trigger.get("data") or {},
        },
    }


async def _invoke_backend_function(run, task: Task, args: dict, settings, creator_email: str,
                                   *, legacy_origin: dict | None = None) -> dict:
    from app.core.automations import legacy_automation_body
    from app.modules.functions.proxy import lookup_function

    function_name = args.get("function_name") or task.with_args.get("function_name")
    call_args = args.get("args", {})
    if legacy_origin is not None:
        automation = await _legacy_automation_entry(legacy_origin["automation_id"])
        if automation is None:
            # Never fall back to the declared args: this function is an
            # automation handler and the declared args are what Base44 does
            # NOT send it. A missing entry is a broken migration, and a loud
            # failure beats a silent no-op (the run shows the reason).
            raise _TaskFailed(
                f"workflow was converted from automation {legacy_origin['automation_id']}, "
                "whose entry is missing from this app's function configs"
            )
        call_args = legacy_automation_body(
            automation, **_legacy_body_kwargs(run["_engine"]["context_extra"].get("trigger") or {})
        )
    if not isinstance(call_args, dict):
        # The measured wire always POSTs an object body (H §6.2); a non-object
        # evaluated `args` is an unmeasured margin — fail loudly over guessing.
        raise _TaskFailed(f"'args' must evaluate to an object, got {type(call_args).__name__}")

    config = await lookup_function(function_name)
    if not config or not config.get("deployed_url"):
        # Measured message shape (H §14.4).
        raise _TaskFailed(
            f"No deployment URL for function '{function_name}' in app {settings.APP_ID}"
        )

    # The measured workflow wire (H §6.2): evaluated args as the verbatim JSON
    # body; BOTH an app-user (creator) token and a service token; the
    # x-workflow-run discriminator (a migrated function may branch on it);
    # base44-function-name; base44-state. The wf_* claims inside our tokens
    # carry cascade context to the entity adapter — Base44's exact claim set
    # is unmeasured (only token lengths were captured), and the SDK treats
    # both tokens as opaque.
    hop_depth = run["_engine"]["context_extra"]["_hop_depth"]
    headers = {
        "Content-Type": "application/json",
        "Base44-App-Id": settings.APP_ID,
        "Base44-Api-Url": await addresses.canonical_base_url(),
        "Base44-Service-Authorization": f"Bearer {mint_workflow_service_token(settings, workflow_id=run['workflow_id'], run_id=run['_id'], hop_depth=hop_depth)}",
        "base44-state": mint_state_token(settings),
        "base44-function-name": function_name,
        "x-workflow-run": "true",
        "authorization": f"Bearer {mint_workflow_creator_token(settings, creator_email, workflow_id=run['workflow_id'], run_id=run['_id'], hop_depth=hop_depth)}",
    }

    # The lease must outlive the slowest legitimate call; a lease that expires
    # mid-call means the process died — the tick then fails the run (CRASH
    # SEMANTICS above).
    run["_engine"]["phase"] = "invoking"
    await _persist_progress(run, lease_horizon_s=CALL_TIMEOUT_S + LEASE_SLACK_S)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(CALL_TIMEOUT_S, connect=30.0)) as client:
            resp = await client.post(
                config["deployed_url"].rstrip("/") + "/",
                headers=headers,
                content=orjson.dumps(call_args),
            )
    except httpx.HTTPError as e:
        run["_engine"]["phase"] = "ready"
        raise _TaskFailed(f"Backend function '{function_name}' request failed: {e}")

    run["_engine"]["phase"] = "ready"

    if not (200 <= resp.status_code < 300):
        # Any non-2xx fails the run (H §14.4); body text rides the message
        # (bounded — the cap is ours, Base44's is unmeasured).
        raise _TaskFailed(
            f"Backend function '{function_name}' returned HTTP {resp.status_code}: "
            f"{resp.text[:500]}"
        )

    # THE OUTPUT WRAPPING RULE (H §14.4): binding is always an object.
    if not resp.content:
        return {}
    try:
        parsed = orjson.loads(resp.content)
    except orjson.JSONDecodeError:
        return {"raw_response": resp.text}
    if isinstance(parsed, dict):
        return parsed
    return {"result": parsed}


def _compute_seconds_until(args: dict) -> dict:
    """Native activity (H §13.7): {target_iso} → {now_iso, seconds, target_iso};
    seconds fractional, past targets CLAMP TO 0 (why eNook guards on > 0).

    `now_iso` is tz-AWARE "+00:00"-style — the measured context value
    ("2026-08-21T07:48:07.330897+00:00"); storage timestamps stay naive."""
    now = datetime.now(timezone.utc)
    target_iso = args.get("target_iso")
    if target_iso is None:
        # The validator requires no args (H §3.2) and a target-less call is
        # unmeasured — clamp-to-0 is the smallest consistent behaviour.
        return {"now_iso": now.isoformat(), "seconds": 0, "target_iso": None}
    try:
        target = datetime.fromisoformat(str(target_iso).replace("Z", "+00:00"))
    except ValueError:
        raise _TaskFailed(f"compute_seconds_until: invalid target_iso '{target_iso}'")
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    seconds = max(0.0, (target - now).total_seconds())
    return {"now_iso": now.isoformat(), "seconds": seconds, "target_iso": target_iso}



async def _send_email(run, args: dict, settings) -> dict:
    """The send_email activity (chase 2026-08-31-new-workflow-triggers §5).

    Required args (contract-enforced at compile): to, subject, template_name;
    `variables` optional. Args are jq-evaluated by the caller like every other
    activity's (measured: a `${ }` subject arrived evaluated). The template is
    read at SEND time — on Base44 from the app's live file tree, here from the
    runtime copy reconcile converges on every deploy, which is the migrated
    world's same statement (file edits reach the runtime when they deploy).

    Test runs DRY-RUN: Base44's run-now completed with
    {"dry_run": true, "sent": false, "to": …} and delivered nothing, while a
    real trigger fire delivered and bound {"sent": true, "to": …}.
    """
    template_name = args.get("template_name")
    template = await email_templates.find(template_name)
    if template is None:
        # Base44's exact message (the engine's uniform `Task 'x' failed: `
        # prefix rides on top, same as every _TaskFailed).
        raise _TaskFailed("404: " + email_templates.NOT_FOUND.format(name=template_name))

    variables = args.get("variables")
    rendered = email_templates.render(
        template, variables if isinstance(variables, dict) else None, escape=True
    )
    to = args.get("to")

    if run.get("is_test_run"):
        return {"dry_run": True, "sent": False, "to": to}

    if build_email_provider(settings) is None:
        raise _TaskFailed("email is not configured (EMAIL_PROVIDER / EMAIL_FROM)")
    # From-name = the app's display name — what Base44 sends (measured:
    # `From: <app name> <app@base44.com>`; their platform sender obviously
    # doesn't transfer) and what the fork's own SendEmail integration already
    # defaults to.
    app_settings = await db.app_settings()
    try:
        await _deliver_email(
            settings,
            to=to,
            subject=args.get("subject"),
            html=rendered,
            from_name=app_settings.get("name"),
        )
    except Exception as e:
        raise _TaskFailed(f"sending the email failed: {e}")
    return {"sent": True, "to": to}


async def _deliver_email(settings, *, to, subject, html, from_name) -> None:
    """The one seam between the activity and the transport (patchable in the
    engine gate). Base44 sends an html-only mail. A workflow fires outside
    any request, so a link-delivered message (the HIPAA lineup) opens at the
    app's canonical address."""
    from app.core.mail import build_app_mail

    await build_app_mail(build_email_provider(settings), settings).deliver(
        to=to, subject=subject, html=html, from_name=from_name,
        base_url=await addresses.canonical_base_url(),
    )


def _exec_switch_pick(run, task: Task, settings, creator_email: str) -> str:
    context = _build_context(run, settings, creator_email)
    for case in task.cases:
        try:
            result = evaluate(case.when, context)
        except ExpressionError as e:
            raise _TaskFailed(str(e))
        if is_truthy(result):  # FIRST match wins (H §14.5)
            return case.then
    # Unreachable on a Base44-validated definition (exhaustiveness enforced at
    # authoring — H §3.5); reachable only through an import-mode warning. Fail
    # loudly rather than invent a default path.
    raise _TaskFailed("no switch case matched and the switch has no catch-all")


async def _exec_wait(run, task: Task, settings, creator_email: str, started_at: datetime) -> str | None:
    """Returns the next cursor, or None when the run parked (or a cancel
    arriving during an inline sleep settled it)."""
    engine = run["_engine"]
    raw = task.wait

    if is_expression(raw):
        context = _build_context(run, settings, creator_email)
        try:
            raw = evaluate(expression_body(raw), context)  # jq FIRST (H §14.3, §8.3)
        except ExpressionError as e:
            raise _TaskFailed(str(e))

    try:
        seconds = parse_wait(raw)
    except WaitError as e:
        raise _TaskFailed(str(e))

    if seconds <= INLINE_WAIT_MAX_S:
        await _persist_progress(run, lease_horizon_s=seconds + LEASE_SLACK_S)
        await asyncio.sleep(seconds)
        if await _refresh_cancel_flag(run):
            await _settle_cancel(run)
            return None
        await _mark_step_completed(run, task, started_at)
        return task.then

    engine["phase"] = "waiting"
    engine["resume_at"] = _now() + timedelta(seconds=seconds)
    engine["waiting"] = {"task": task.name, "then": task.then, "started_at": started_at}
    engine["lease_until"] = None  # parked — the tick owns the wake-up
    await db.coll(RUNS).update_one({"_id": run["_id"]}, {"$set": {"_engine": engine}})
    return None


# ── context ──

def _build_context(run, settings, creator_email: str) -> dict:
    """The jq root document, dumped whole from a live run (H §4.2): step
    outputs at the root under their step names, trigger payload, and the
    `_`-prefixed metadata family."""
    engine = run["_engine"]
    return {
        **engine["outputs"],
        **engine["context_extra"],
        "_app_id": settings.APP_ID,
        "_app_type": "user_app",
        "_app_type_context": {},
        "_creator_email": creator_email,
        "_workflow_id": run["workflow_id"],
    }


# ── claiming, persistence, terminal transitions ──

async def _claim(run_id: str, *, horizon_s: float = LEASE_SLACK_S):
    """Atomic lease claim — the only way a run gets an executor. Requires the
    run to be DUE (resume_at arrived, or a cancel pending) and UNLEASED, so a
    parked run can never be advanced early and two executors can never hold
    the same run."""
    now = _now()
    return await db.coll(RUNS).find_one_and_update(
        {
            "_id": run_id,
            "status": "running",
            "$and": [
                {"$or": [
                    {"_engine.lease_until": None},
                    {"_engine.lease_until": {"$lt": now}},
                ]},
                {"$or": [
                    {"_engine.resume_at": {"$lte": now}},
                    {"_engine.cancel_requested": True},
                ]},
            ],
        },
        {"$set": {"_engine.lease_until": now + timedelta(seconds=horizon_s)}},
        return_document=ReturnDocument.AFTER,
    )


async def _persist_progress(run, *, lease_horizon_s: float = LEASE_SLACK_S) -> None:
    engine = run["_engine"]
    engine["lease_until"] = _now() + timedelta(seconds=lease_horizon_s)
    await db.coll(RUNS).update_one(
        {"_id": run["_id"]},
        {"$set": {"_engine": engine, "steps_count": run["steps_count"]}},
    )


async def _refresh_cancel_flag(run) -> bool:
    fresh = await db.coll(RUNS).find_one({"_id": run["_id"]}, {"_engine.cancel_requested": 1})
    requested = bool(fresh and fresh["_engine"]["cancel_requested"])
    run["_engine"]["cancel_requested"] = requested
    return requested


async def _append_step(run, task_name: str, task_type: str, status: str,
                       started_at: datetime, completed_at: datetime | None,
                       error_message: str | None, *, input_data=None) -> None:
    """Append-only ledger, two rows per executed step, task I/O deliberately
    null — the measured API shape (H §6.3 + raw evidence/03): even a
    `started` row carries a completed_at (its write time) with duration_ms 0,
    and error_message is always a string, "" when empty. The one row with
    input: a connector run's `__trigger__` (the trigger payload — measured on
    every captured connector run, 2026-09-02)."""
    from app.deps import get_settings
    if completed_at is None:  # a "started" row
        completed_at = _now()
        duration_ms = 0
    else:
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
    await db.coll(STEPS).insert_one({
        "run_id": run["_id"],
        "workflow_id": run["workflow_id"],
        "app_id": get_settings().APP_ID,
        "task_name": task_name,
        "task_type": task_type,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "input_data": input_data,
        "output_data": None,
        "error_message": error_message or "",
    })


async def _finish_run(run, status: str, *, status_reason: str = "", error_message: str = "") -> bool:
    """Terminal transition, guarded on `running` so double-settlement is
    structurally impossible."""
    now = _now()
    duration_ms = int((now - run["started_at"]).total_seconds() * 1000)
    result = await db.coll(RUNS).update_one(
        {"_id": run["_id"], "status": "running"},
        {"$set": {
            "status": status,
            "status_reason": status_reason,
            "error_message": error_message,
            "completed_at": now,
            "duration_ms": duration_ms,
            "steps_count": run["steps_count"],
            "_engine.lease_until": None,
            "_engine.resume_at": None,
            "_engine.phase": "done",
        }},
    )
    if result.modified_count == 0:
        return False
    run["status"] = status
    run["error_message"] = error_message
    await _update_workflow_aggregates(run, status, now)
    return True


async def _update_workflow_aggregates(run, status: str, now: datetime) -> None:
    """Workflow-record counters (H §14.7, §14.10, §13.5): total_runs counts
    completed+failed only; cancels touch neither total_runs nor
    consecutive_failures; failure streaks auto-deactivate at 5 (scheduled) /
    50 (other trigger types)."""
    wf_key = workflow_key(run["workflow_id"])
    update: dict = {"$set": {"last_run_at": now, "last_run_status": _AGGREGATE_STATUS[status]}}
    if status == "completed":
        update["$inc"] = {"total_runs": 1, "successful_runs": 1}
        update["$set"]["consecutive_failures"] = 0
        await db.coll(WORKFLOWS).update_one({"_id": wf_key}, update)
        return
    if status == "cancelled":
        await db.coll(WORKFLOWS).update_one({"_id": wf_key}, update)
        return

    update["$inc"] = {"total_runs": 1, "failed_runs": 1, "consecutive_failures": 1}
    workflow = await db.coll(WORKFLOWS).find_one_and_update(
        {"_id": wf_key}, update, return_document=ReturnDocument.AFTER
    )
    if workflow is None:
        return
    thresholds = CONTRACT["auto_deactivate"]
    trigger_type = (workflow.get("trigger") or {}).get("config", {}).get("trigger_type")
    limit = thresholds["scheduled"] if trigger_type == "scheduled" else thresholds["other"]
    if workflow.get("consecutive_failures", 0) >= limit and workflow.get("status") == "active":
        result = await db.coll(WORKFLOWS).update_one(
            {"_id": wf_key, "status": "active"},
            {"$set": {"status": "inactive", "status_reason": "consecutive_failures"}},
        )
        if result.modified_count == 1:
            await _notify_owner_deactivated(workflow, run)


async def _notify_owner_deactivated(workflow: dict, run) -> None:
    """Base44 emails the owner when a workflow auto-deactivates (H §7b).
    Best-effort through the app's own email provider; never raises."""
    try:
        from app.deps import get_settings
        settings = get_settings()
        to = workflow.get("created_by")
        provider = build_email_provider(settings)
        if not to or provider is None:
            return
        name = workflow.get("name", "")
        await provider.send(
            to=to,
            subject=f"Workflow \"{name}\" was paused after repeated failures",
            text=(
                f"Your workflow \"{name}\" failed {workflow.get('consecutive_failures', 0)} times in a row "
                f"and has been paused.\n\nLast error: {run.get('error_message') or '(see run history)'}\n\n"
                "Fix the cause, then reactivate it (toggle-status) — the failure count resets."
            ),
        )
    except Exception:
        logger.debug("owner deactivation email failed (non-fatal)", exc_info=True)


async def _complete_run(run) -> None:
    await _finish_run(run, "completed")


async def _fail_run(run, error_message: str) -> None:
    await _finish_run(run, "failed", error_message=error_message)


async def _settle_cancel(run) -> None:
    # `status_reason: "user_requested"`, error empty, duration = full elapsed
    # (H §14.7). An interrupted wait's `started` ledger row stays unmatched —
    # the step did not complete.
    await _finish_run(run, "cancelled", status_reason="user_requested")


async def request_cancel(run_id: str) -> dict | None:
    """Two-phase cancel, Base44's shape (H §14.7): acknowledge immediately;
    the executor (inline check, wait-resume check, or the tick's sweep)
    settles it. Idempotent on terminal runs — returns their current status."""
    run = await db.coll(RUNS).find_one({"_id": run_id}, {"status": 1})
    if run is None:
        return None
    if run["status"] != "running":
        return {"status": run["status"], "run_id": run_id}
    await db.coll(RUNS).update_one(
        {"_id": run_id}, {"$set": {"_engine.cancel_requested": True}}
    )
    return {"status": "cancelling", "run_id": run_id}


# ── tick-side sweep (called by the scheduler module) ──

async def sweep_due_runs(*, limit: int = 50) -> list[str]:
    """Ids of runs an executor should pick up now: fresh/parked runs whose
    resume_at arrived (lease-free), pending cancels, and stale-lease survivors
    of a dead process. A stale lease in phase `invoking` is FAILED here, not
    resumed (CRASH SEMANTICS above)."""
    now = _now()
    due: list[str] = []
    cursor = db.coll(RUNS).find(
        {
            "status": "running",
            "$or": [
                {
                    "_engine.resume_at": {"$lte": now},
                    "_engine.lease_until": None,
                },
                {"_engine.lease_until": {"$lt": now}},
                {"_engine.cancel_requested": True},
            ],
        },
        {"_engine.phase": 1, "_engine.lease_until": 1, "_engine.cancel_requested": 1,
         "started_at": 1, "steps_count": 1, "workflow_id": 1},
        limit=limit,
    )
    async for run in cursor:
        lease = run["_engine"].get("lease_until")
        lease_expired = lease is not None and lease < now
        if (
            run["_engine"]["phase"] == "invoking"
            and lease_expired
            and not run["_engine"].get("cancel_requested")
        ):
            await _fail_run(run, (
                "the engine was interrupted during a backend-function call; "
                "the call may or may not have executed, so the run was not retried"
            ))
            continue
        if lease is None or lease_expired or run["_engine"].get("cancel_requested"):
            due.append(run["_id"])
    return due
