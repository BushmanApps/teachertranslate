"""Trigger dispatch — turns app events into workflow runs.

One helper per trigger family, all funnelling into `_fire_matching`. Every
adapter constructs the MEASURED trigger payload for its family (H §13.1,
§14.9, §14.11b); `_fire_matching` then gives the event only to the workflows
whose `trigger.condition` admits it (`expressions.trigger_admits`, probe 37)
and enforces the measured cascade rules before creating runs.

THE CASCADE RULES (H §14.6 — final, after two retracted probes):
  1. a workflow does NOT re-fire on a row its own run wrote (same-workflow
     immediate guard);
  2. everything else cascades normally — a different workflow watching the
     same entity fires, chains across entities fire — with `_hop_depth`
     incrementing once per generation;
  3. the cascade stops at `_hop_depth` 5 (runs at depth ≤5 exist, depth 6
     never) — the contract's `cascade_depth_limit`.

Workflow origin rides the `wf_*` claims in the tokens the engine mints for
its function calls (service token for `asServiceRole` writes, creator token
for ordinary writes — both paths covered), read here off
`ctx.token_payload`.

Dispatch must NEVER fail or slow the event that triggered it: matching reads
a 5s-TTL in-process cache (the `_app_settings` pattern — one indexed query
per 5s worst case, nothing on the hot path for apps without workflows), run
creation errors are swallowed and logged, and execution itself is kicked
fire-and-forget with the tick as the guaranteed fallback executor.
"""

import logging
import time

import orjson

from app.core import db

from .contract import CASCADE_DEPTH_LIMIT
from .engine import WORKFLOWS, create_run, kick
from .expressions import trigger_admits

logger = logging.getLogger("escapebase44.workflows")

_cache: list[dict] | None = None
_cache_read_at: float = 0.0
_CACHE_TTL_S = 5.0

# UPDATE events always include these three system-field keys in
# changed_fields even when unchanged — Base44's diff behaviour, measured on
# the automations wire (core/automations.py, 2026-05-21). The workflows
# entity payload shares the "changed fields on update" contract (H §13.1);
# whether it shares this quirk is unmeasured — assuming one shared diff
# function is the smallest hypothesis.
_UPDATE_ALWAYS_INCLUDED = frozenset({"created_by_id", "is_sample", "updated_date"})


async def _active_workflows() -> list[dict]:
    global _cache, _cache_read_at
    now = time.monotonic()
    if _cache is not None and now - _cache_read_at < _CACHE_TTL_S:
        return _cache
    _cache = await db.coll(WORKFLOWS).find({"status": "active"}).to_list(length=1000)
    _cache_read_at = now
    return _cache


def invalidate_cache() -> None:
    global _cache
    _cache = None


def _trigger_config(workflow: dict) -> dict:
    return (workflow.get("trigger") or {}).get("config") or {}


def _workflow_origin(ctx) -> tuple[str | None, int]:
    """(origin workflow id, hop depth of the originating run) from the
    caller's token claims; (None, -1) for non-workflow writes."""
    payload = getattr(ctx, "token_payload", None) or {}
    origin = payload.get("wf_workflow_id")
    if origin is None:
        return None, -1
    return str(origin), int(payload.get("wf_hop_depth", 0))


def _jsonable(value):
    """Trigger payloads enter the jq context, which needs pure-JSON values —
    datetimes flatten to isoformat, ObjectIds to str."""
    return orjson.loads(orjson.dumps(value, default=_orjson_default))


def _orjson_default(obj):
    from datetime import datetime
    from bson import ObjectId
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError(f"unsupported type in trigger payload: {type(obj)}")


async def _fire_matching(matches: list[dict], trigger_payload: dict, *,
                         origin_workflow_id: str | None, origin_hop_depth: int) -> None:
    """Create + kick a run per matching workflow whose trigger condition
    admits the event, cascade rules applied."""
    child_depth = origin_hop_depth + 1 if origin_workflow_id is not None else 0
    if child_depth > CASCADE_DEPTH_LIMIT:
        return  # rule 3 — Base44 stops the cascade past depth 5 (H §14.6)
    payload = _jsonable(trigger_payload)
    for workflow in matches:
        if origin_workflow_id is not None and str(workflow["_id"]) == origin_workflow_id:
            continue  # rule 1 — never re-fire the workflow that wrote the row
        if not trigger_admits((workflow.get("trigger") or {}).get("condition"), payload):
            continue  # not this workflow's event (probe 37)
        try:
            run_id = await create_run(
                workflow,
                trigger_type=payload["trigger_type"],
                trigger_payload=payload,
                hop_depth=child_depth,
            )
            kick(run_id)
        except Exception:
            logger.debug(
                "workflow trigger dispatch failed for '%s' (non-fatal)",
                workflow.get("name"), exc_info=True,
            )


# ── entity events (H §13.1, §13.2) ──

async def dispatch_entity(entity_name: str, op: str, row: dict, ctx, *,
                          old_data: dict | None = None) -> None:
    """Fire entity-triggered workflows for a SINGLE-record write.

    Callers are exactly the fork's single-record entity mutation paths —
    measured rule: cardinality decides, identity does not (single create/
    update/delete fire, service-role included; every bulk/many path and
    restore are silent — H §13.2). Never call this from a bulk path.
    """
    workflows = await _active_workflows()
    matches = [
        w for w in workflows
        if _trigger_config(w).get("trigger_type") == "entity"
        and _trigger_config(w).get("entity_name") == entity_name
        and op in (_trigger_config(w).get("events") or [])  # `events: []` never fires (H §14.1)
    ]
    if not matches:
        return

    origin_workflow_id, origin_hop_depth = _workflow_origin(ctx)
    payload = {
        "trigger_type": "entity",
        "entity_name": entity_name,
        "entity_id": str(row.get("id", "")),
        "event_type": op,
        "data": row,  # the record AS STORED, server stamps included (H §13.1)
        "old_data": old_data if op == "update" else None,  # null on create AND delete
        "changed_fields": _changed_fields(op, row, old_data),
    }
    await _fire_matching(matches, payload,
                         origin_workflow_id=origin_workflow_id,
                         origin_hop_depth=origin_hop_depth)


def _changed_fields(op: str, row: dict, old_data: dict | None) -> list[str]:
    # create: every field; update: changed fields only (H §13.1); delete is
    # unmeasured for workflows — all fields, matching the automations wire.
    if op != "update":
        return sorted(row.keys())
    changed: set[str] = set()
    if old_data is not None:
        for key in set(row.keys()) | set(old_data.keys()):
            if row.get(key) != old_data.get(key):
                changed.add(key)
    for key in _UPDATE_ALWAYS_INCLUDED:
        if key in row:
            changed.add(key)
    return sorted(changed)


# ── app_user_auth events (H §14.9) ──

async def dispatch_auth(event_type: str, user: dict, *, auth_method: str = "password") -> None:
    """`signup` fires at OTP VERIFICATION (when the user actually exists),
    not at register; `login` on each login (H §14.9)."""
    workflows = await _active_workflows()
    matches = [
        w for w in workflows
        if _trigger_config(w).get("trigger_type") == "app_user_auth"
        and event_type in (_trigger_config(w).get("events") or [])
    ]
    if not matches:
        return
    from app.core.responses import utcnow_naive
    app_user = {
        "id": str(user.get("_id", user.get("id", ""))),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "role": user.get("role", "user"),
        "collaborator_role": user.get("collaborator_role"),
        "is_verified": user.get("is_verified", True),
    }
    # Measured shape: flat AND duplicated under `data` — expressions address
    # either `.trigger.email` or `.trigger.data.email` (H §14.9).
    flat = {
        "trigger_type": "app_user_auth",
        "event_type": event_type,
        "auth_method": auth_method,
        "occurred_at": utcnow_naive().isoformat(),
        "user_id": app_user["id"],
        "email": app_user["email"],
        "full_name": app_user["full_name"],
        "role": app_user["role"],
        "app_user": app_user,
    }
    payload = {**flat, "data": dict(flat)}
    await _fire_matching(matches, payload, origin_workflow_id=None, origin_hop_depth=-1)


# ── in_app_agent events (H §14.9) ──

async def dispatch_agent_conversation_started(agent_name: str, *, app_user_id: str,
                                              conversation_id: str, message_id: str,
                                              message_text: str, has_files: bool,
                                              channel: str = "in_app") -> None:
    """`conversation_started` fires on the FIRST MESSAGE of a conversation,
    not on conversation creation (H §14.9) — the caller owns that distinction."""
    workflows = await _active_workflows()
    matches = [
        w for w in workflows
        if _trigger_config(w).get("trigger_type") == "in_app_agent"
        and _trigger_config(w).get("agent_name") == agent_name
        and "conversation_started" in (_trigger_config(w).get("events") or [])
    ]
    if not matches:
        return
    payload = {
        "trigger_type": "in_app_agent",
        "event_type": "conversation_started",
        "agent_name": agent_name,
        "data": {
            "app_user": {"id": app_user_id},
            "event": {
                "type": "conversation_started",
                "agent_name": agent_name,
                "channel": channel,
                "conversation_id": conversation_id,
                "message_id": message_id,
            },
            "message": {"text": message_text, "has_files": has_files},
        },
    }
    await _fire_matching(matches, payload, origin_workflow_id=None, origin_hop_depth=-1)


# ── app_publish events (H §14.9) ──

async def dispatch_publish(*, is_first_publish: bool, published_by: str, visibility: str) -> None:
    """Post-migration, "publish" means a deployment going live — fired by the
    module's boot-time new-deployment detection (lifespan.py)."""
    workflows = await _active_workflows()
    matches = [
        w for w in workflows
        if _trigger_config(w).get("trigger_type") == "app_publish"
        and "published" in (_trigger_config(w).get("events") or [])
    ]
    if not matches:
        return
    from app.core.responses import utcnow_naive
    payload = {
        "trigger_type": "app_publish",
        "event_type": "published",
        "is_first_publish": is_first_publish,
        "occurred_at": utcnow_naive().isoformat(),
        "published_by": published_by,
        "visibility": visibility,
    }
    await _fire_matching(matches, payload, origin_workflow_id=None, origin_hop_depth=-1)
