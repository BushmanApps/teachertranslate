"""
Automation dispatcher — single source of truth for "build a Base44-shaped
automation request and POST it to the function URL."

Both code paths land here:

  ENTITY: entity services call `dispatch_entity(entity_name, op, row, ctx, old_data=...)`
          after a successful single-record mutation.
  SCHEDULED: the `/api/internal/fire-automation/{id}` trigger endpoint
             (called by pg_cron / Deno.cron at cron-tick time) calls
             `dispatch_scheduled(automation_id)`.
  CONNECTOR: the workflows engine's connector poller (core/workflows/
             connectors.py — one provider channel per resource, polled from
             the tick) calls `dispatch_connector(automation, url, …)` with
             the provider event it detected, for every legacy connector
             automation subscribed to it. Extracted + seeded since May,
             never fired until 2026-09-02.

Both build their payload + headers via the shared `_build_request(...)`,
which knows the difference between entity and scheduled bodies by the
automation's `type` field. Outbound HTTP is also shared.

Mirrors Base44's architecture: their EventBridge worker is a pure trigger
(no payload knowledge), payload construction lives on their backend. Same
service-token shape, same creator-token shape, same body shapes captured
live against Base44 production 2026-05-21.
"""

import asyncio
import logging

import httpx
import orjson

from app.core import db
from app.core import addresses
from app.core.functions.service_token import (
    mint_creator_token,
    mint_for_automation,
    mint_state_token,
)

logger = logging.getLogger("escapebase44.automations")

# Verified against Base44 production payload_too_large boundary. Below this
# size both `data` and `old_data` are sent in full; above this size both go
# null and `changed_fields` becomes [].
_PAYLOAD_SIZE_THRESHOLD = 199924

# UPDATE events always include these three system-field keys in
# changed_fields even when they didn't change — Base44's diff function
# treats them as "the server always touches these, so they always count as
# changed." Verified live with no-op / single-field / multi-field updates
# on auto-pulse-lab.base44.app (2026-05-21).
_UPDATE_ALWAYS_INCLUDED = frozenset({"created_by_id", "is_sample", "updated_date"})


# ── public dispatch entry points ──

async def dispatch_entity(
    entity_name: str,
    op: str,
    row: dict,
    ctx,
    invoker=None,
    *,
    old_data: dict | None = None,
) -> None:
    """Fire every matching entity automation for (entity_name, op).

    Called from entity services after a successful single-record mutation.
    Fan-out is concurrent. Failures are logged but never bubble up — an
    automation error must not roll back the originating mutation.

    This is also the single entity-event choke point for WORKFLOW entity
    triggers: an app is either legacy-Automations or Workflows, never both
    (the measured capability split), so exactly one of the two dispatchers
    below finds matches. Only single-record writes reach here — which is
    itself the measured Base44 rule for entity triggers (cardinality
    decides; every bulk/many path is silent — workflows H §13.2).
    """
    from app.core.workflows.dispatch import dispatch_entity as dispatch_workflow_entity
    try:
        await dispatch_workflow_entity(entity_name, op, row, ctx, old_data=old_data)
    except Exception:
        logger.debug("workflow entity dispatch failed (non-fatal)", exc_info=True)

    from app.deps import get_settings
    settings = get_settings()

    tasks = []
    async for func_config in db.coll("_function_configs").find():
        deployed_url = func_config.get("deployed_url")
        if not deployed_url:
            continue
        for auto in func_config.get("automations", []):
            if auto.get("type") != "entity":
                continue
            if auto.get("entity_name") != entity_name:
                continue
            if op not in (auto.get("event_types") or []):
                continue
            if auto.get("is_active") is False:
                continue
            # Entity `trigger_conditions` gate the fire. This was extracted,
            # persisted and NEVER evaluated until 2026-08-22 — so a Base44
            # automation configured "only when status == paid" fired on
            # EVERY matching event after migration. Grammar + semantics
            # measured 15/15 on a real legacy app (workflows HANDOFF §14.8).
            if not conditions_match(
                auto.get("trigger_conditions"),
                data=row,
                old_data=old_data if op == "update" else None,
                changed_fields=_compute_changed_fields(op, row, old_data),
            ):
                continue
            tasks.append(
                _fire(
                    settings,
                    deployed_url,
                    auto,
                    function_name=str(func_config.get("name") or ""),
                    op=op,
                    entity_name=entity_name,
                    row=row,
                    old_data=old_data,
                )
            )

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def dispatch_scheduled(automation_id: str) -> bool:
    """Fire a single scheduled automation by id.

    Called from the cron-trigger endpoint when pg_cron / Deno.cron ticks.
    Returns True if the automation was found and fired, False if it didn't
    exist (404), is inactive, or its function isn't deployed. Errors during
    the outbound POST are caught and logged — the cron infra retries on
    its own schedule.
    """
    from app.deps import get_settings
    settings = get_settings()

    auto, deployed_url, function_name = await _lookup_scheduled(automation_id)
    if auto is None or deployed_url is None:
        return False
    if auto.get("is_active") is False:
        return False
    if not await _claim_scheduled_fire(auto):
        return False

    try:
        await _fire(settings, deployed_url, auto, function_name=function_name,
                    op=None, entity_name=None, row=None, old_data=None)
        return True
    except Exception:
        logger.debug("Scheduled automation %s failed (non-fatal)", automation_id, exc_info=True)
        return False


async def dispatch_connector(
    automation: dict,
    deployed_url: str,
    *,
    function_name: str,
    integration_type: str,
    event_type: str,
    data: dict,
    provider_identifier: str,
) -> bool:
    """Fire one legacy connector automation for a provider event the poller
    detected. The body is Base44's documented connector-automation envelope
    (developers/backend/resources/backend-functions/automations — "Webhook
    payload"): `automation{id,name,type}`, `event{type, integration_type,
    provider_identifier}`, `data` (the provider's raw payload, the same
    object the workflows trigger carries), `payload_too_large`. Trigger
    conditions are evaluated over `data` — the docs' field paths are
    relative to it (`"status"` reads `payload.data.status`; EyeOn Pro's
    live automation reads `has_new_messages` bare), unlike entity
    automations' `data.`/`old_data.` prefixes.

    Returns True when the request was sent (conditions admitted it)."""
    if not connector_conditions_match(automation.get("trigger_conditions"), data):
        return False
    from app.deps import get_settings
    settings = get_settings()
    try:
        headers, body_bytes = await _build_request(
            settings, automation, function_name=function_name,
            op=None, entity_name=None, row=None, old_data=None,
            connector_event={"type": event_type, "integration_type": integration_type,
                             "provider_identifier": provider_identifier, "data": data},
        )
        url = deployed_url.rstrip("/") + "/"
        async with httpx.AsyncClient(timeout=180) as client:
            await client.post(url, headers=headers, content=body_bytes)
    except Exception:
        logger.debug("Connector automation %s failed (non-fatal)", automation.get("name"), exc_info=True)
    return True


async def _claim_scheduled_fire(auto: dict) -> bool:
    """Enforce the schedule's END conditions — pg_cron can't.

    Two bugs this closes (live in every migration before 2026-08-22):
    - a ONE-TIME automation was registered as the cron `m h D M *`, which
      re-fires ANNUALLY; it now fires exactly once (`eb44_fired_at`);
    - `ends_type` "after" (`ends_after_count` fires) and "on" (`ends_on_date`)
      were never enforced; the automation ran forever.
    The legacy vocabulary is `never | on | after` (the workflows one is
    `never | on_date | after_count` — different, don't conflate).

    Bookkeeping lives on the automation entry inside `_function_configs`
    (`eb44_fired_at`, `eb44_fire_count`), claimed atomically with a filtered
    update so two ticks can't both win one slot.
    """
    from datetime import datetime, timezone
    from app.core.responses import utcnow_naive
    now = utcnow_naive()
    coll = db.coll("_function_configs")
    entry = {"id": auto.get("id")}

    if auto.get("schedule_mode") == "one-time":
        result = await coll.update_one(
            {"automations": {"$elemMatch": {**entry, "eb44_fired_at": None}}},
            {"$set": {"automations.$.eb44_fired_at": now}},
        )
        return result.modified_count == 1

    ends_type = auto.get("ends_type") or "never"
    if ends_type == "on":
        ends_on = auto.get("ends_on_date")
        if ends_on is not None:
            edge = ends_on if isinstance(ends_on, datetime) else datetime.fromisoformat(
                str(ends_on).replace("Z", "+00:00"))
            if edge.tzinfo is not None:
                edge = edge.astimezone(timezone.utc).replace(tzinfo=None)
            if now > edge:
                return False
    if ends_type == "after":
        limit = auto.get("ends_after_count")
        if limit is not None:
            result = await coll.update_one(
                {"automations": {"$elemMatch": {
                    **entry,
                    "$or": [{"eb44_fire_count": {"$lt": int(limit)}},
                            {"eb44_fire_count": {"$exists": False}}],
                }}},
                {"$inc": {"automations.$.eb44_fire_count": 1}},
            )
            return result.modified_count == 1
    await coll.update_one({"automations": {"$elemMatch": entry}},
                          {"$inc": {"automations.$.eb44_fire_count": 1}})
    return True


# ── entity trigger_conditions (measured grammar, workflows HANDOFF §14.8) ──

# { logic: "and"|"or", conditions: [ FieldCondition | ConditionGroup ] }
# FieldCondition = { field, operator, value? }  — field starts with data. /
# old_data. / changed_fields;  ConditionGroup = { logic, conditions } (nested).
_CONDITION_OPERATORS = frozenset({
    "equals", "not_equals", "gt", "gte", "lt", "lte", "contains", "not_contains",
    "starts_with", "ends_with", "in_list", "not_in_list", "exists", "not_exists",
    "is_empty", "is_not_empty",
})

_MISSING = object()


def connector_conditions_match(conditions, data: dict | None) -> bool:
    """Connector automations' `trigger_conditions` use the same grammar and
    operators as entity ones, but their field paths are relative to the
    provider payload itself (docs: `"status"` reads `payload.data.status`) —
    the scope root IS `data`. No conditions = always fires."""
    if not conditions or not isinstance(conditions, dict):
        return True
    return _group_matches(conditions, data or {})


def conditions_match(conditions, *, data: dict | None, old_data: dict | None,
                     changed_fields: list[str]) -> bool:
    """True iff the automation's trigger_conditions admit this event.
    No conditions = always fires (measured)."""
    if not conditions or not isinstance(conditions, dict):
        return True
    scope = {"data": data or {}, "old_data": old_data or {}, "changed_fields": changed_fields}
    return _group_matches(conditions, scope)


def _group_matches(group: dict, scope: dict) -> bool:
    items = group.get("conditions") or []
    results = []
    for item in items:
        if not isinstance(item, dict):
            results.append(False)
        elif "conditions" in item:
            results.append(_group_matches(item, scope))
        else:
            results.append(_field_condition_matches(item, scope))
    if not results:
        return True
    return any(results) if group.get("logic") == "or" else all(results)


def _resolve_field(path: str, scope: dict):
    """`data.status` → scope["data"]["status"]; `changed_fields` → the list.
    Returns the _MISSING sentinel when any segment is absent."""
    current = scope
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return _MISSING
    return current


def _is_empty(value) -> bool:
    return value is _MISSING or value is None or value == "" or value == [] or value == {}


def _field_condition_matches(cond: dict, scope: dict) -> bool:
    operator = cond.get("operator")
    if operator not in _CONDITION_OPERATORS:
        return False
    actual = _resolve_field(str(cond.get("field", "")), scope)
    expected = cond.get("value")

    if operator == "exists":
        return actual is not _MISSING
    if operator == "not_exists":
        return actual is _MISSING
    if operator == "is_empty":
        return _is_empty(actual)
    if operator == "is_not_empty":
        return not _is_empty(actual)
    if actual is _MISSING:
        return False  # a field neither row has matches nothing (measured)
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator in ("gt", "gte", "lt", "lte"):
        try:
            a, b = float(actual), float(expected)
        except (TypeError, ValueError):
            return False
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[operator]
    if operator in ("contains", "not_contains"):
        try:
            hit = expected in actual
        except TypeError:
            hit = False
        return hit if operator == "contains" else not hit
    if operator == "starts_with":
        return isinstance(actual, str) and actual.startswith(str(expected))
    if operator == "ends_with":
        return isinstance(actual, str) and actual.endswith(str(expected))
    if operator in ("in_list", "not_in_list"):
        hit = isinstance(expected, list) and actual in expected
        return hit if operator == "in_list" else not hit
    return False


async def _lookup_scheduled(automation_id: str) -> tuple[dict | None, str | None, str]:
    async for func_config in db.coll("_function_configs").find():
        deployed_url = func_config.get("deployed_url")
        for auto in func_config.get("automations", []):
            if auto.get("type") != "scheduled":
                continue
            if str(auto.get("id", "")) != automation_id:
                continue
            return auto, deployed_url, str(func_config.get("name") or "")
    return None, None, ""


# ── shared request builder + outbound ──

async def _fire(
    settings,
    deployed_url: str,
    automation: dict,
    *,
    function_name: str,
    op: str | None,
    entity_name: str | None,
    row: dict | None,
    old_data: dict | None,
) -> None:
    try:
        headers, body_bytes = await _build_request(
            settings,
            automation,
            function_name=function_name,
            op=op,
            entity_name=entity_name,
            row=row,
            old_data=old_data,
        )
        url = deployed_url.rstrip("/") + "/"
        async with httpx.AsyncClient(timeout=180) as client:
            await client.post(url, headers=headers, content=body_bytes)
    except Exception:
        logger.debug("Automation %s failed (non-fatal)", automation.get("name"), exc_info=True)


def legacy_automation_body(
    automation: dict,
    *,
    op: str | None = None,
    entity_name: str | None = None,
    row: dict | None = None,
    old_data: dict | None = None,
    connector_event: dict | None = None,
) -> dict:
    """The body an AUTOMATION's function receives, by automation type.

    The ONE owner of the legacy body contract. Two callers: this module's own
    fires, and the workflows engine for a workflow Base44 CONVERTED from an
    automation — such a workflow keeps the legacy body even though its
    definition declares `args` (measured both ways 2026-09-17 on the
    `automations-probe` fixture Base44 converted on 09-07; a NATIVE workflow
    with `args: {}` receives `{}` verbatim, measured 2026-09-27 on the parity
    lab, so the rule is keyed on the conversion, never on empty args).

      - "entity": full envelope `{automation, event, data, old_data,
        changed_fields, payload_too_large, [args]}`.
      - "scheduled": the body IS the function_args dict (or `{}` when null),
        no envelope.
      - "connector": the documented envelope `{automation, event{type,
        integration_type, provider_identifier}, data, payload_too_large,
        [args]}`.
    """
    automation_type = automation.get("type") or "entity"
    if automation_type == "entity":
        return _build_entity_body(automation, op or "update", entity_name or "", row or {}, old_data)
    if automation_type == "scheduled":
        return _build_scheduled_body(automation)
    if automation_type == "connector":
        return _build_connector_body(automation, connector_event or {})
    raise ValueError(f"unknown automation type {automation_type!r}")


async def _build_request(
    settings,
    automation: dict,
    *,
    function_name: str,
    op: str | None,
    entity_name: str | None,
    row: dict | None,
    old_data: dict | None,
    connector_event: dict | None = None,
) -> tuple[dict, bytes]:
    """Construct (headers, body_bytes) for an automation invocation.
    `function_name` is the invoked function's name — Base44 sends it as the
    `base44-function-name` header on every automation fire (measured on
    entity, scheduled and connector fires of one real app, 2026-09-02).

    The body comes from `legacy_automation_body`; the marker header is per
    type (`base44-entity-automation` / `base44-scheduled-task` /
    `base44-connector-automation`).
    """
    automation_type = automation.get("type") or "entity"
    body = legacy_automation_body(
        automation, op=op, entity_name=entity_name, row=row, old_data=old_data,
        connector_event=connector_event,
    )

    # Offline invocation — no visitor, so the app's canonical address.
    headers = _build_headers(settings, automation, automation_type=automation_type,
                             api_url=await addresses.canonical_base_url(),
                             function_name=function_name)
    body_bytes = orjson.dumps(body, default=_orjson_default)
    return headers, body_bytes


def _build_entity_body(
    automation: dict,
    op: str,
    entity_name: str,
    row: dict,
    old_data: dict | None,
) -> dict:
    data: dict | None = row
    payload_too_large = False

    serialized_size = len(orjson.dumps(data, default=_orjson_default)) if data else 0
    if serialized_size > _PAYLOAD_SIZE_THRESHOLD:
        payload_too_large = True
        data = None
        old_data = None
        changed_fields: list[str] = []
    else:
        changed_fields = _compute_changed_fields(op, row, old_data)

    body: dict = {
        "automation": {
            "id": str(automation.get("id", "")),
            "name": automation.get("name", ""),
            "type": "entity",
        },
        "event": {
            "type": op,
            "entity_name": entity_name,
            "entity_id": row.get("id", ""),
        },
        "data": data,
        "old_data": old_data if op == "update" and not payload_too_large else None,
        "changed_fields": changed_fields,
        "payload_too_large": payload_too_large,
    }

    # `args` is included ONLY when function_args is non-null on Base44 prod
    # (verified live — null → key omitted, populated → key present at end).
    fn_args = automation.get("function_args")
    if fn_args is not None:
        body["args"] = fn_args
    return body


def _build_scheduled_body(automation: dict) -> dict:
    """Scheduled body shape: function_args itself becomes the body root.

    Verified live 2026-05-21:
      - function_args null → body is empty {}
      - function_args {"k": "v"} → body is {"k": "v"} (NOT wrapped in {args: ...})

    This is inconsistent with how entity automations wrap function_args under
    `args`, but it's Base44's actual contract — replicate exactly.
    """
    fn_args = automation.get("function_args")
    return fn_args if isinstance(fn_args, dict) else {}


def _build_connector_body(automation: dict, event: dict) -> dict:
    """Connector body shape — Base44's documented "Webhook payload"
    (developers/backend/resources/backend-functions/automations): the
    automation, the event (its subscribed name, the integration, the provider
    account identifier), the provider's raw payload as `data`, and the same
    ~200 KB `payload_too_large` rule the entity envelope has. `args` rides
    along when function_args is set, as on the entity envelope."""
    data: dict | None = event.get("data") or {}
    payload_too_large = False
    if len(orjson.dumps(data, default=_orjson_default)) > _PAYLOAD_SIZE_THRESHOLD:
        payload_too_large = True
        data = None
    body: dict = {
        "automation": {
            "id": str(automation.get("id", "")),
            "name": automation.get("name", ""),
            "type": "connector",
        },
        "event": {
            "type": event.get("type", ""),
            "integration_type": event.get("integration_type", ""),
            "provider_identifier": event.get("provider_identifier", ""),
        },
        "data": data,
        "payload_too_large": payload_too_large,
    }
    fn_args = automation.get("function_args")
    if fn_args is not None:
        body["args"] = fn_args
    return body


def _compute_changed_fields(op: str, row: dict, old_data: dict | None) -> list[str]:
    if op == "create":
        return sorted(row.keys())
    if op == "delete":
        return sorted(row.keys())
    if op == "update":
        changed: set[str] = set()
        if old_data is not None:
            for key in set(row.keys()) | set(old_data.keys()):
                if row.get(key) != old_data.get(key):
                    changed.add(key)
        # System fields the server always mutates on update — Base44 lists
        # them in changed_fields regardless of whether they actually changed.
        for key in _UPDATE_ALWAYS_INCLUDED:
            if key in row:
                changed.add(key)
        return sorted(changed)
    return sorted(row.keys())


def _build_headers(settings, automation: dict, *, automation_type: str, api_url: str,
                   function_name: str) -> dict:
    headers: dict = {
        "Content-Type": "application/json",
        "Base44-App-Id": settings.APP_ID,
        "Base44-Api-Url": api_url,
        "Base44-Service-Authorization": f"Bearer {mint_for_automation(settings)}",
        "base44-automation-id": str(automation.get("id", "")),
        # the invoked function's name rides every automation fire (entity,
        # scheduled, connector — measured 2026-09-02), as it does on
        # workflow invocations
        "base44-function-name": function_name,
        "base44-state": mint_state_token(settings),
    }
    if automation_type == "entity":
        headers["base44-entity-automation"] = "true"
    elif automation_type == "scheduled":
        headers["base44-scheduled-task"] = "true"
    elif automation_type == "connector":
        headers["base44-connector-automation"] = "true"

    creator_email = automation.get("created_by")
    if creator_email:
        headers["authorization"] = f"Bearer {mint_creator_token(settings, creator_email)}"

    return headers


def _orjson_default(obj):
    # Pass datetimes through as raw isoformat — Base44's automation body uses
    # `.isoformat()` (`+00:00` for tz-aware, naive otherwise) rather than
    # the REST `Z`-style. See SERIALIZE_FOR_AUTOMATION in entities/services.
    from datetime import datetime
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"unsupported type for automation body: {type(obj)}")


# ── back-compat alias ──
# Until all entity services are switched, keep the old `dispatch` name as an
# alias for the entity-side path.
dispatch = dispatch_entity
