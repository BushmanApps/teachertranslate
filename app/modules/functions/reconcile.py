"""The functions registry converges onto the repo (core/reconcile.py).

The backend routes a call to a function by its `_function_configs` row, and
fires a function's automations (entity, scheduled, connector) off the same
row. Until 2026-09-18 the row was written ONCE, at migration — a function
the builder added afterwards deployed fine and answered 404 here forever.
Now the runner reports the functions it just deployed with their runtime
addresses: listed names get their address (a new name gets a row), unlisted
rows go.

Since 2026-09-27 the repo also declares each function's AUTOMATIONS (the
`automations` of its `function.jsonc` — Base44's own file), and the runner
sends them with the function:

- an automation is known by its `id` (the one Base44 gave it, written into
  the file at migration; for an automation written since, derived by the
  runner from the function's and the automation's names);
- the file's fields win — the runner sends every file field, null where the
  file sets none, so a field removed from the file is removed here;
- what only the backend knows is kept: who created the automation
  (`created_by` — the creator's token rides every fire), the fire count and
  the fired mark (`_claim_scheduled_fire`), anything else the row carried;
- a new automation is created by the app's owner, the workflows reconcile's
  rule for a new workflow;
- a schedule that changed starts counting from zero, as a workflow's does;
- an automation gone from the file goes.

A function sent WITHOUT the key (a repo generated before 2026-09-27, whose
runner declares no automations) keeps the automations its row has.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, TypeAdapter

from app.core import db


class DeployedFunction(BaseModel):
    name: str
    url: str
    automations: list[dict] | None = None


_FUNCTIONS = TypeAdapter(list[DeployedFunction])

# What decides WHEN a scheduled automation fires. A change to any of them is
# a new schedule: the fire count and the fired mark belong to the old one.
_SCHEDULE_FIELDS = (
    "schedule_mode", "schedule_type", "cron_expression", "repeat_unit", "repeat_interval",
    "one_time_date", "repeat_on_days", "repeat_on_day_of_month", "start_time",
    "ends_type", "ends_on_date", "ends_after_count",
)
_FIRE_BOOKKEEPING = ("eb44_fired_at", "eb44_fire_count")
# The file's dates, kept the way the migration seeds them (BSON dates).
_DATE_FIELDS = ("one_time_date", "ends_on_date")


def _as_date(value):
    """An ISO string → a naive UTC datetime (the seed's shape); anything else
    — a datetime already, null, a string that is not a date — as it is."""
    if not isinstance(value, str):
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def merge_automations(existing: list[dict], declared: list[dict], *, default_created_by: str) -> list[dict]:
    known = {str(a.get("id")): a for a in existing if isinstance(a, dict) and a.get("id")}
    merged: list[dict] = []
    for entry in declared:
        entry = {**entry}
        for field in _DATE_FIELDS:
            if field in entry:
                entry[field] = _as_date(entry[field])
        # The listing's own key for the type rides beside `type` on a seeded
        # automation; keep the two saying the same thing.
        entry["automation_type"] = entry.get("type")
        before = known.get(str(entry.get("id")))
        if before is None:
            merged.append({**entry, "created_by": default_created_by})
            continue
        kept = {k: v for k, v in before.items() if k not in entry}
        if any(_as_date(before.get(f)) != entry.get(f) for f in _SCHEDULE_FIELDS if f in entry):
            for field in _FIRE_BOOKKEEPING:
                kept.pop(field, None)
        merged.append({**kept, **entry})
    return merged


async def reconcile(payload: dict) -> dict | None:
    if "functions" not in payload:
        return None
    functions = _FUNCTIONS.validate_python(payload["functions"])
    coll = db.coll("_function_configs")
    names = [f.name for f in functions]
    owner: str | None = None
    automations = 0
    for fn in functions:
        update: dict = {"name": fn.name, "deployed_url": fn.url}
        if fn.automations is not None:
            if owner is None:
                owner = (await db.app_settings()).get("created_by") or ""
            row = await coll.find_one({"name": fn.name}) or {}
            update["automations"] = merge_automations(
                row.get("automations") or [], fn.automations, default_created_by=owner,
            )
            automations += len(update["automations"])
        await coll.update_one({"name": fn.name}, {"$set": update}, upsert=True)
    removed = await coll.delete_many({"name": {"$nin": names}})
    result: dict = {"registered": len(names), "removed": removed.deleted_count}
    if any(fn.automations is not None for fn in functions):
        result["automations"] = automations
    return result
