"""Workflows API — the measured Base44 surface, feature-gated per app mode.

Route map and response shapes are Base44's, measured (H §2, §10, §11, §14.10
+ raw evidence/03-read-surfaces.json — field lists, orderings, limits and
error strings follow the captures, timestamp formats included: workflow
records use `Z`, runs/steps use `+00:00`, version lists are naive. Base44's
serialization is genuinely that inconsistent and clients may key on it).

Deliberately NOT implemented (the product replicates apps, not Base44's
editor — Daniel's ruling): public create/update/rename routes and the AI
run-analysis route. Authoring is the repo's canonical files, converged by
the internal reconcile below; the builder agent edits files like any other
source.

Auth: owner-level (is_admin — app-owner app_user or service_role). Base44's
exact gate class for these management surfaces is unmeasured (probes ran on
platform tokens, an identity that does not exist post-migration); owner-level
is the conservative equivalent.
"""

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel

from app.config import Settings
from app.core import db
from app.core.errors import AppHTTPException
from app.core.internal_auth import check_cron_secret
from app.core.security.pipeline import AuthedContext, get_authed_context_no_visibility
from app.core.workflows import engine, scheduler
from app.core.workflows.compiler import WorkflowValidationError, compile_definition
from app.core.workflows.contract import CONTRACT
from app.core.workflows.dispatch import invalidate_cache
from app.core.workflows.engine import RUNS, STEPS, VERSIONS, WORKFLOWS, workflow_key
from app.deps import get_settings

router = APIRouter(prefix="/api/apps/{app_id}/workflows", tags=["workflows"])
internal = APIRouter(prefix="/api/internal/workflows", tags=["workflows-internal"])

# Measured ceiling on every listing surface: `le: 200` leaked by Base44's
# validator (2026-08-22) on the workflows list, runs and versions alike. (The
# changelog's "pages through up to 1000" is about paging, not the per-request
# limit.)
MAX_LIMIT = 200
RUNS_LIMIT = 200


# ── gates ──

async def _gate(ctx: AuthedContext) -> None:
    """Feature gate + owner gate. A legacy-automations app answers 403 with
    Base44's exact message (H §5.3)."""
    settings_doc = await db.app_settings()
    if not settings_doc.get("workflows_enabled"):
        raise AppHTTPException(403, "Workflows are not enabled for this app")
    if not ctx.is_admin:
        raise AppHTTPException(403, "Workflow management requires admin access")


async def _load_workflow(workflow_id: str) -> dict:
    workflow = await db.coll(WORKFLOWS).find_one({"_id": workflow_key(workflow_id)})
    if workflow is None:
        raise AppHTTPException(404, "Workflow not found")
    return workflow


# ── serialization (measured shapes) ──

def _z(dt) -> str | None:
    return dt.isoformat() + "Z" if dt is not None else None


def _offset(dt) -> str | None:
    return dt.isoformat() + "+00:00" if dt is not None else None


def _naive(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _record(w: dict) -> dict:
    """The LIST record — exactly the §10.2 key set."""
    return {
        "id": str(w["_id"]),
        "app_id": None,  # filled by caller (settings)
        "file_key": w.get("file_key"),
        "name": w.get("name"),
        "description": w.get("description"),
        "status": w.get("status"),
        "status_reason": w.get("status_reason"),
        "trigger": w.get("trigger"),
        "total_runs": w.get("total_runs", 0),
        "consecutive_failures": w.get("consecutive_failures", 0),
        "last_run_at": _z(w.get("last_run_at")),
        "last_run_status": w.get("last_run_status"),
        "created_date": _z(w.get("created_date")),
    }


def _record_full(w: dict, definition: dict | None) -> dict:
    """The GET-ONE record — the richer measured set (evidence/03): adds
    definition, current_version_id, per-status counters, created_by,
    updated_date, app_type_context."""
    return {
        **_record(w),
        "app_type_context": w.get("app_type_context", {}),
        "created_by": w.get("created_by"),
        "updated_date": _z(w.get("updated_date")),
        "current_version_id": w.get("current_version_id"),
        "definition": definition,
        "successful_runs": w.get("successful_runs", 0),
        "failed_runs": w.get("failed_runs", 0),
    }


def _run(r: dict) -> dict:
    return {
        "run_id": r["_id"],
        "workflow_id": r.get("workflow_id"),
        "workflow_name": r.get("workflow_name"),
        "trigger_type": r.get("trigger_type"),
        "status": r.get("status"),
        "started_at": _offset(r.get("started_at")),
        "completed_at": _offset(r.get("completed_at")),
        "duration_ms": r.get("duration_ms"),
        "steps_count": r.get("steps_count", 0),
        "error_message": r.get("error_message", ""),
        "is_test_run": r.get("is_test_run", False),
        "credits_consumed": r.get("credits_consumed", 0),
        "status_reason": r.get("status_reason", ""),
    }


def _step(s: dict) -> dict:
    return {
        "run_id": s.get("run_id"),
        "workflow_id": s.get("workflow_id"),
        "app_id": s.get("app_id"),
        "task_name": s.get("task_name"),
        "task_type": s.get("task_type"),
        "status": s.get("status"),
        "started_at": _offset(s.get("started_at")),
        "completed_at": _offset(s.get("completed_at")),
        "duration_ms": s.get("duration_ms"),
        "input_data": None,
        "output_data": None,
        "error_message": s.get("error_message", ""),
    }


def _version(v: dict) -> dict:
    return {
        "version_id": v["version_id"],
        "workflow_id": v.get("workflow_id"),
        "created_by": v.get("created_by"),
        "change_summary": v.get("change_summary"),
        "created_date": _naive(v.get("created_date")),  # versions list is NAIVE on the wire
    }


def _check_limit(limit: int, ceiling: int = MAX_LIMIT) -> None:
    if limit > ceiling:
        raise AppHTTPException(422, f"Input should be less than or equal to {ceiling}")


# ── read surfaces ──

@router.get("")
async def list_workflows(
    app_id: str,
    include_archived: bool = Query(default=False),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
    settings: Settings = Depends(get_settings),
):
    await _gate(ctx)
    _check_limit(limit)
    query = {} if include_archived else {"status": {"$ne": "archived"}}
    rows = await db.coll(WORKFLOWS).find(query).sort(
        "created_date", -1  # measured ordering (H §14.10)
    ).skip(offset).limit(limit).to_list(length=limit)
    out = []
    for w in rows:
        record = _record(w)
        record["app_id"] = settings.APP_ID
        out.append(record)
    return out


@router.get("/runs")
async def list_all_runs(
    app_id: str,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    await _gate(ctx)
    _check_limit(limit, RUNS_LIMIT)
    rows = await db.coll(RUNS).find({}).sort("started_at", -1).skip(offset).limit(limit).to_list(length=limit)
    return [_run(r) for r in rows]


@router.get("/stats")
async def stats(
    app_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    await _gate(ctx)
    pipeline = [
        {"$group": {
            "_id": "$workflow_id",
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "cancelled": {"$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}},
            "total": {"$sum": 1},
            "avg_duration_ms": {"$avg": "$duration_ms"},
            "last_run_at": {"$max": "$started_at"},
        }},
    ]
    rows = await db.coll(RUNS).aggregate(pipeline).to_list(length=MAX_LIMIT)
    out = []
    for row in rows:
        workflow = await db.coll(WORKFLOWS).find_one(
            {"_id": workflow_key(row["_id"])}, {"last_run_status": 1}
        )
        out.append({
            "workflow_id": row["_id"],
            "completed": row["completed"],
            "failed": row["failed"],
            "cancelled": row["cancelled"],
            "total": row["total"],
            "avg_duration_ms": row["avg_duration_ms"],
            "last_run_at": _offset(row["last_run_at"]),
            "last_run_status": (workflow or {}).get("last_run_status"),
        })
    return out


class ValidateBody(BaseModel):
    definition: dict


@router.post("/validate-definition")
async def validate_definition(
    app_id: str,
    body: ValidateBody,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    """Pure validator, Base44's response shape (H §1): also OUR declared
    subset in machine-readable form — the same contract the drift probe
    diffs against Base44's own endpoint."""
    await _gate(ctx)
    errors: list[dict] = []
    valid = True
    try:
        compile_definition(body.definition, mode="validate")
    except WorkflowValidationError as e:
        valid = False
        errors.append({"code": e.code, "message": e.message})
    return {
        "valid": valid,
        "errors": errors,
        "supported_task_types": CONTRACT["task_types"],
        "available_activities": sorted(CONTRACT["activities"]),
    }


@router.get("/{workflow_id}")
async def get_workflow(
    app_id: str,
    workflow_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
    settings: Settings = Depends(get_settings),
):
    await _gate(ctx)
    workflow = await _load_workflow(workflow_id)
    version = await db.coll(VERSIONS).find_one(
        {"version_id": workflow.get("current_version_id")}
    )
    record = _record_full(workflow, (version or {}).get("definition"))
    record["app_id"] = settings.APP_ID
    return record


@router.get("/{workflow_id}/runs")
async def list_runs(
    app_id: str,
    workflow_id: str,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    await _gate(ctx)
    _check_limit(limit, RUNS_LIMIT)
    rows = await db.coll(RUNS).find({"workflow_id": workflow_id}).sort(
        "started_at", -1).skip(offset).limit(limit).to_list(length=limit)
    return [_run(r) for r in rows]


@router.get("/{workflow_id}/runs/{run_id}")
async def run_detail(
    app_id: str,
    workflow_id: str,
    run_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    await _gate(ctx)
    run = await db.coll(RUNS).find_one({"_id": run_id, "workflow_id": workflow_id})
    if run is None:
        raise AppHTTPException(404, "Run not found")
    steps = await db.coll(STEPS).find({"run_id": run_id}).to_list(length=MAX_LIMIT)
    detail = _run(run)
    detail["definition_version_id"] = run.get("definition_version_id")
    detail["steps"] = [_step(s) for s in steps]
    detail["ai_analysis"] = ""  # present-but-empty in the measured shape; the AI route is not ours
    return detail


@router.get("/{workflow_id}/versions")
async def list_versions(
    app_id: str,
    workflow_id: str,
    limit: int = Query(default=100),
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    await _gate(ctx)
    _check_limit(limit, RUNS_LIMIT)
    rows = await db.coll(VERSIONS).find({"workflow_id": workflow_id}).sort(
        "created_date", -1).limit(limit).to_list(length=limit)
    return [_version(v) for v in rows]


@router.get("/{workflow_id}/versions/{version_id}")
async def get_version(
    app_id: str,
    workflow_id: str,
    version_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    await _gate(ctx)
    version = await db.coll(VERSIONS).find_one(
        {"version_id": version_id, "workflow_id": workflow_id}
    )
    if version is None:
        raise AppHTTPException(404, "Version not found")
    out = _version(version)
    out["definition"] = version.get("definition")
    return out


# ── lifecycle ──

@router.post("/{workflow_id}/toggle-status")
async def toggle_status(
    app_id: str,
    workflow_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    """active ↔ inactive. Pause never touches in-flight runs (H §14.10)."""
    await _gate(ctx)
    workflow = await _load_workflow(workflow_id)
    if workflow["status"] == "archived":
        raise AppHTTPException(409, "Workflow is archived — unarchive it first")
    new_status = "inactive" if workflow["status"] == "active" else "active"
    update: dict = {"status": new_status, "status_reason": None}
    if new_status == "active":
        # Reactivation resets the failure streak (H §7b) and re-arms the
        # schedule from now.
        update["consecutive_failures"] = 0
        update["schedule_state"] = {"next_fire_at": None,
                                    "fire_count": (workflow.get("schedule_state") or {}).get("fire_count", 0)}
    await db.coll(WORKFLOWS).update_one({"_id": workflow["_id"]}, {"$set": update})
    if new_status == "active":
        await scheduler.ensure_schedule_state({**workflow, **update}, now=engine._now())
    invalidate_cache()
    return {"workflow_id": str(workflow["_id"]), "status": new_status, "message": None}


@router.delete("/{workflow_id}")
async def archive_workflow(
    app_id: str,
    workflow_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    """Archive — Base44 has no hard delete; history stays readable
    (H §14.10). Never touches in-flight runs."""
    await _gate(ctx)
    workflow = await _load_workflow(workflow_id)
    await db.coll(WORKFLOWS).update_one(
        {"_id": workflow["_id"]},
        {"$set": {"status": "archived", "status_reason": None}},
    )
    invalidate_cache()
    return {"status": "archived", "workflow_id": str(workflow["_id"])}


@router.post("/{workflow_id}/unarchive")
async def unarchive_workflow(
    app_id: str,
    workflow_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    """Unarchive comes back ACTIVE, not inactive (measured — H §14.10)."""
    await _gate(ctx)
    workflow = await _load_workflow(workflow_id)
    update = {"status": "active", "status_reason": None, "consecutive_failures": 0}
    await db.coll(WORKFLOWS).update_one({"_id": workflow["_id"]}, {"$set": update})
    await scheduler.ensure_schedule_state({**workflow, **update}, now=engine._now())
    invalidate_cache()
    return {"status": "active", "message": "Workflow transitioned to active"}


# ── run-now / cancel ──

class RunNowBody(BaseModel):
    replay_from_run_id: str | None = None


@router.get("/{workflow_id}/run-now-info")
async def run_now_info(
    app_id: str,
    workflow_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    await _gate(ctx)
    workflow = await _load_workflow(workflow_id)
    requires = _requires_previous_run(workflow)
    recent = await db.coll(RUNS).find({"workflow_id": str(workflow["_id"])}).sort(
        "started_at", -1).limit(10).to_list(length=10)
    return {
        "manual_run_config": {"requires_previous_run": requires},
        "recent_runs": [_run(r) for r in recent],
    }


def _requires_previous_run(workflow: dict) -> bool:
    """Scheduled workflows run-now with an empty trigger; every payload-
    bearing family replays a previous run's trigger data instead (H §7b,
    §14.10 — measured on entity; the doc states the same for connector and
    agent, and the payload-bearing logic generalises)."""
    trigger_type = (workflow.get("trigger") or {}).get("config", {}).get("trigger_type")
    return trigger_type != "scheduled"


@router.post("/{workflow_id}/run-now")
async def run_now(
    app_id: str,
    workflow_id: str,
    body: RunNowBody | None = None,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    """`Run now` executes REAL actions and is recorded as a test run
    (H §7b): scheduled workflows get trigger_type "manual" + empty trigger;
    payload-bearing families replay a prior run (H §14.10)."""
    await _gate(ctx)
    workflow = await _load_workflow(workflow_id)
    body = body or RunNowBody()

    if _requires_previous_run(workflow):
        if not body.replay_from_run_id:
            raise AppHTTPException(
                400, "This trigger requires a previous run's payload — pass replay_from_run_id."
            )
        prior = await db.coll(RUNS).find_one({"_id": body.replay_from_run_id})
        if prior is None:
            raise AppHTTPException(404, "Run not found")
        if not prior.get("_engine"):
            # Runs imported from Base44 are history without engine state —
            # Base44's API never exposed their trigger payloads, so there is
            # nothing to replay. Honest 400 over an invented empty payload.
            raise AppHTTPException(
                400, "This run predates the migration and its trigger payload was not "
                     "preserved by Base44's API — replay a run that happened here.",
            )
        run_id = await engine.create_run(
            workflow,
            trigger_type=prior["trigger_type"],  # the replay keeps the ORIGINAL type (H §14.10)
            trigger_payload=prior["_engine"]["context_extra"]["trigger"],
            is_test_run=True,
        )
    else:
        run_id = await engine.create_run(
            workflow,
            trigger_type="manual",  # the 8th trigger-type value, runs only (H §6.5)
            trigger_payload={},
            is_test_run=True,
        )
    engine.kick(run_id)
    return {"status": "started", "message": "Run started", "run_id": run_id}


@router.post("/{workflow_id}/runs/{run_id}/cancel")
async def cancel_run(
    app_id: str,
    workflow_id: str,
    run_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
):
    await _gate(ctx)
    result = await engine.request_cancel(run_id)
    if result is None:
        raise AppHTTPException(404, "Run not found")
    return result


# ── internal (cron-secret) surfaces ──

@internal.post("/tick")
async def tick_endpoint(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_eb44_cron_secret: str | None = Header(default=None, alias="X-Eb44-Cron-Secret"),
):
    """The heartbeat — pg_cron pokes this every minute. Fires due schedules,
    resumes due waits, settles cancels, reaps dead leases. Cheap when idle:
    two indexed queries."""
    check_cron_secret(x_eb44_cron_secret, settings.EB44_CRON_SECRET)
    try:
        return await scheduler.tick()
    except Exception:
        # The tick must never error at the cron layer — the next minute
        # retries everything (all sweeps are idempotent by construction).
        import logging
        logging.getLogger("escapebase44.workflows").exception("workflow tick failed")
        return {"fired": 0, "advanced": 0, "error": True}


# ── the push door (public, provider-facing, signature-verified) ──
#
# Slack, Outlook and the rest PUSH their events to a URL configured on the
# OAuth app — which is the customer's own app after migration, so this address
# is theirs (core/workflows/push.py carries the whole design and what was
# measured). Unauthenticated by construction: the provider has no session, and
# the signature (Slack) or the clientState we set on the subscription (Graph)
# is the contract. It never runs a workflow inline — it verifies, dedups and
# stores; the tick fans out, because the platform freezes this container the
# moment the response is sent and Slack retires a subscription that answers
# slower than 3 s.
push_router = APIRouter(tags=["connector-events"])


@push_router.api_route("/api/connector-events/{integration}", methods=["POST", "GET"])
async def connector_events(integration: str, request: Request):
    from app.core.workflows import push

    raw = await request.body()
    status, reply = await push.receive(
        integration, raw,
        {k.lower(): v for k, v in request.headers.items()},
        dict(request.query_params),
    )
    if reply is not None:
        return Response(content=reply.body, media_type=reply.media_type, status_code=status)
    if status != 200:
        return Response(status_code=status)
    # Drain right here where the host can finish work after a response; on
    # serverless this is a no-op and the tick does it within the minute.
    settings = get_settings()
    if settings.EB44_BACKGROUND_TASKS:
        import asyncio
        asyncio.create_task(push.drain_push_inbox())
    return {"ok": True}
