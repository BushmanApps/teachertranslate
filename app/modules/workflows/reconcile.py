"""The workflows registry converges onto the repo (core/reconcile.py): the
runner sends the repo's current canonical workflow files (+ the email
templates the send_email activity resolves) — the repo stays the source of
truth, runtime state is derived (the architecture doctrine, and Base44's
own model — H §6.1).
"""

from __future__ import annotations

from pydantic import TypeAdapter

from app.core import db
from app.core.workflows.reconcile import reconcile_files

_FILES = TypeAdapter(dict[str, str])


async def reconcile(payload: dict) -> dict | None:
    if "workflows" not in payload:
        return None
    files = _FILES.validate_python(payload["workflows"])
    settings_doc = await db.app_settings()
    if not settings_doc.get("workflows_enabled"):
        return {"skipped": "workflows are not enabled for this app"}
    owner = settings_doc.get("created_by") or ""
    return await reconcile_files(files, default_created_by=owner)
