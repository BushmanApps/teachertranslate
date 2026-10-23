"""Workflows module startup: indexes, the env scrub, publish detection.

Runs for every app (module folders always ship) but no-ops in one cheap
query when the app is not Workflows-enabled — an entity-heavy legacy app
pays nothing for this module existing.
"""

import logging
import os

from app.core import db

logger = logging.getLogger("escapebase44.workflows")

# The belt to the jq denylist's braces (H §4.4, §13.4): libjq's `env` builtin
# reads the REAL process environment, which holds every provider secret. The
# denylist filter is the primary, Base44-exact defense; scrubbing the secrets
# out of os.environ after Settings captured them means a filter bypass reads
# nothing. Only ever runs on Workflows apps — the only apps where jq runs.
#
# ⚠️ THE INVARIANT THIS DEPENDS ON, and it is load-bearing for the WHOLE app:
# Settings must already be constructed when this runs, and nothing may ever
# construct it again. `create_app` calls `deps.get_settings()` (@lru_cache) at
# import time, so the single process-wide instance exists before any hook or
# request. This was NOT true once — create_app built its own `Settings()` and
# left the cache cold, so the first request after startup rebuilt Settings from
# the scrubbed environment and every Settings-dependent route 500'd on a live
# deployment (found by the end-to-end migration, 2026-08-22). The engine gate's
# "settings survive the scrub" case pins it.
#
# Lazy-env-reader audit (why this is safe): the fork's own consumers all take
# credentials explicitly from the Settings object (S3StorageProvider /
# VercelBlob / Resend / openai are constructed with values, not env lookups —
# main.py _init_providers + core/llm.py), and aioboto3 only falls back to
# AWS_* env when keys are NOT passed explicitly, which ours always are.
_SCRUB_KEYS = (
    "MONGO_URL",
    "APP_JWT_SECRET",
    "SERVICE_JWT_SECRET",
    "EB44_CRON_SECRET",
    "S3_SECRET_ACCESS_KEY",
    "S3_SESSION_TOKEN",
    "BLOB_READ_WRITE_TOKEN",
    "RESEND_API_KEY",
    "SES_SECRET_ACCESS_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "SERPAPI_API_KEY",
    "GOOGLE_CLIENT_SECRET",
    "MICROSOFT_CLIENT_SECRET",
    "IAP_GOOGLE_SA_JSON_B64",
)

_ENGINE_STATE = "_workflow_engine_state"


async def on_startup() -> None:
    settings_doc = await db.app_settings()
    if not settings_doc.get("workflows_enabled"):
        return

    for key in _SCRUB_KEYS:
        os.environ.pop(key, None)

    from app.core.workflows.engine import RUNS, STEPS, VERSIONS, WORKFLOWS
    runs = db.coll(RUNS)
    await runs.create_index([("status", 1), ("_engine.resume_at", 1)])
    await runs.create_index([("workflow_id", 1), ("started_at", -1)])
    await runs.create_index([("started_at", -1)])
    await db.coll(STEPS).create_index([("run_id", 1)])
    await db.coll(WORKFLOWS).create_index([("status", 1)])
    await db.coll(WORKFLOWS).create_index([("file_key", 1)])
    await db.coll(VERSIONS).create_index(
        [("workflow_id", 1), ("version_id", 1)], unique=True
    )

    await _detect_publish(settings_doc)


async def _detect_publish(settings_doc: dict) -> None:
    """Post-migration, "publish" is a deployment going live (the closest
    faithful analog — Base44's `published` event fires on app deploy,
    H §14.9). Detected by a build marker changing across boots:
    VERCEL_DEPLOYMENT_ID on Vercel (native), EB44_BUILD_MARKER on VPS
    (the runner writes the git sha into the backend .env). No marker — e.g.
    local dev — means no publish events, silently."""
    marker = os.environ.get("VERCEL_DEPLOYMENT_ID") or os.environ.get("EB44_BUILD_MARKER")
    if not marker:
        return
    state = await db.coll(_ENGINE_STATE).find_one({"_id": "publish_marker"})
    if state is not None and state.get("marker") == marker:
        return
    is_first = state is None
    await db.coll(_ENGINE_STATE).update_one(
        {"_id": "publish_marker"},
        {"$set": {"marker": marker}},
        upsert=True,
    )
    if is_first:
        # The marker's very first persistence is migration day / backfill —
        # the migration itself is not an app-publish event.
        return

    from app.core.workflows.dispatch import dispatch_publish
    owner_email = settings_doc.get("created_by") or ""
    owner = await db.coll("User").find_one({"email": owner_email}, {"_id": 1}) if owner_email else None
    try:
        await dispatch_publish(
            is_first_publish=False,
            published_by=str(owner["_id"]) if owner else "",
            visibility=settings_doc.get("public_settings", "public_without_login"),
        )
    except Exception:
        logger.debug("publish dispatch failed (non-fatal)", exc_info=True)
