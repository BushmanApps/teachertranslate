"""Reconcile the repo's canonical workflow files into runtime state.

The user's repo is the authoritative source (`base44/workflows/*.jsonc` —
exactly how Base44 itself works: writing that file CREATES the workflow, and
its version records read "Updated via file tree" — H §6.1, §5). The CD runner
calls /api/internal/workflows/reconcile after every deploy with the current
file set; this module converges the `_workflows` / `_workflow_versions`
collections onto it.

Measured laws honoured here:

- version identity is content-addressed — sha256 of the canonically-dumped
  definition, verified bit-for-bit against ids Base44 minted (H §5). This
  Python implementation is the ONE hash implementation in the product; the
  migrator deliberately never computes it (a TS re-implementation would be a
  drift risk on unicode/float serialization).
- a definition edit mints a version; a trigger edit does NOT (H §13.8) —
  trigger changes update the record in place.
- `file_key` ↔ record is 1-to-many once archiving is involved; the ACTIVE
  record per file_key is the join (H §7c).
- a file that fails validation creates NO record — Base44 writes the file and
  silently skips the workflow (H §14.2). We do the same, but return the
  rejection so the CD log and the builder agent can see it.
- a record whose file vanished is ARCHIVED (unmeasured margin: the probes
  archived via the API before deleting files, so file-delete-alone was never
  observed — archiving preserves history and stops firing, and Base44 has no
  hard delete at all).
"""

import logging

from app.core import db
from app.core.responses import utcnow_naive

from .compiler import WorkflowValidationError, compile_workflow_source, version_id_for
from .engine import VERSIONS, WORKFLOWS

logger = logging.getLogger("escapebase44.workflows")

CANONICAL_ROOT = "base44/workflows/"


def file_key_for(path: str) -> str:
    name = path[len(CANONICAL_ROOT):]
    return name[:-6] if name.endswith(".jsonc") else name


async def reconcile_files(files: dict[str, str], *, default_created_by: str) -> dict:
    """Converge runtime workflow state onto the repo's canonical files.

    `files` maps canonical paths → raw JSONC text (the full current set — an
    active record with no corresponding file gets archived). Returns a
    summary the CD log prints.
    """
    from .dispatch import invalidate_cache
    from .scheduler import ensure_schedule_state

    now = utcnow_naive()
    seen_keys: set[str] = set()
    created, updated, unchanged, archived, rejected = [], [], [], [], []

    for path, text in files.items():
        if not path.startswith(CANONICAL_ROOT):
            continue
        key = file_key_for(path)
        seen_keys.add(key)
        try:
            parsed = compile_workflow_source(text, mode="import")
        except WorkflowValidationError as e:
            # Base44 writes the file and creates no record (H §14.2); we also
            # SURFACE the reason instead of being silent about it.
            rejected.append({"file_key": key, "code": e.code, "message": e.message})
            continue

        version_id = parsed.compiled.version_id
        record = await db.coll(WORKFLOWS).find_one(
            {"file_key": key, "status": {"$ne": "archived"}}
        )
        if record is None:
            from bson import ObjectId
            doc = {
                "_id": ObjectId(),
                "app_type_context": {},
                "file_key": key,
                "name": parsed.name,
                "description": parsed.description,
                "status": "active",  # a file-created workflow starts ACTIVE (H §6.5)
                "status_reason": None,
                "trigger": parsed.trigger,
                "current_version_id": version_id,
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "consecutive_failures": 0,
                "last_run_at": None,
                "last_run_status": None,
                "created_by": default_created_by,
                "created_date": now,
                "updated_date": now,
                "schedule_state": {"next_fire_at": None, "fire_count": 0},
            }
            await db.coll(WORKFLOWS).insert_one(doc)
            await _ensure_version(doc, parsed.compiled.definition, version_id,
                                  default_created_by, now)
            await ensure_schedule_state(doc, now=now)
            created.append(key)
            continue

        changes: dict = {}
        if record.get("current_version_id") != version_id:
            await _ensure_version(record, parsed.compiled.definition, version_id,
                                  default_created_by, now)
            changes["current_version_id"] = version_id
        if _trigger_body(record.get("trigger")) != _trigger_body(parsed.trigger):
            # Trigger edits update in place, no new version (H §13.8); a
            # schedule change recomputes from scratch. The record's trigger
            # carries Base44's trigger `id` (H §9.1) which the file never
            # does — compare bodies, preserve the id.
            changes["trigger"] = {**(parsed.trigger or {}),
                                  **({"id": record["trigger"]["id"]} if (record.get("trigger") or {}).get("id") else {})}
            changes["schedule_state"] = {"next_fire_at": None, "fire_count": 0}
        if record.get("name") != parsed.name:
            changes["name"] = parsed.name
        if record.get("description") != parsed.description:
            changes["description"] = parsed.description

        if changes:
            changes["updated_date"] = now
            await db.coll(WORKFLOWS).update_one({"_id": record["_id"]}, {"$set": changes})
            await ensure_schedule_state({**record, **changes}, now=now)
            updated.append(key)
        else:
            await ensure_schedule_state(record, now=now)
            unchanged.append(key)

    # Records whose file vanished: archive (see module docstring).
    cursor = db.coll(WORKFLOWS).find(
        {"status": {"$ne": "archived"}, "file_key": {"$nin": sorted(seen_keys)}}
    )
    async for record in cursor:
        await db.coll(WORKFLOWS).update_one(
            {"_id": record["_id"]},
            {"$set": {"status": "archived", "status_reason": None, "updated_date": now}},
        )
        archived.append(record["file_key"])

    invalidate_cache()
    return {
        "created": created, "updated": updated, "unchanged": unchanged,
        "archived": archived, "rejected": rejected,
    }


def _trigger_body(trigger) -> dict:
    """A trigger minus its record-side `id` — the file-vs-record comparison."""
    return {k: v for k, v in (trigger or {}).items() if k != "id"}


async def _ensure_version(record: dict, definition: dict, version_id: str,
                          created_by: str, now) -> None:
    # Version docs are PER-WORKFLOW — the content-addressed version_id can
    # legitimately repeat across workflows with identical definitions, so the
    # identity here is the (workflow_id, version_id) pair.
    assert version_id == version_id_for(definition)
    workflow_id = str(record["_id"])
    existing = await db.coll(VERSIONS).find_one(
        {"workflow_id": workflow_id, "version_id": version_id}, {"_id": 1}
    )
    if existing is None:
        await db.coll(VERSIONS).insert_one({
            "workflow_id": workflow_id,
            "version_id": version_id,
            "definition": definition,
            "created_by": created_by,
            "change_summary": "Updated via file tree",  # Base44's own wording (H §5)
            "created_date": now,
        })
