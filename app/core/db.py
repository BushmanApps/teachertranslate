import time

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None
_app_settings_cache: dict | None = None
_app_settings_read_at: float = 0.0

# How long a read of what this process holds about the app may serve before
# it is read again: the cached `_app_settings` document below, and a realtime
# listener's resolved reader (core/realtime.py). Bounds staleness for writes that happen OUTSIDE this process
# (EB44's wizard adds `custom_domains`, the canonical-URL switch rewrites the
# SEO/url fields) while keeping the hot path off the DB link — see
# `app_settings` below.
FRESHNESS_SECONDS = 5.0

# `_app_settings` carries the app's full backend source as build artifacts the
# runtime never reads (~0.65MB on a real app). Nothing ever serves these.
_APP_SETTINGS_BUILD_ARTIFACTS = ("functions", "backend_project", "backend_project_deno_backup")

# Fields that ARE served, but only on cold paths — one agent turn, one SSR
# shell render — while the hot read below runs on EVERY request. On a big app
# they dominate it: measured on a real 942.7KB document, `agents` (the app's
# agent instructions) was 52.5KB and `seo_settings` 13.8KB of a 78.2KB read,
# i.e. ~85% of the bytes the security pipeline drags per request for data it
# never looks at. Projected out of the hot read and fetched by their own
# consumers instead (`app_settings_field`), which also removes the whole class:
# a bigger agent prompt can no longer inflate the per-request read at all.
_APP_SETTINGS_COLD_FIELDS = ("agents", "seo_settings")

_APP_SETTINGS_HOT_EXCLUDED = _APP_SETTINGS_BUILD_ARTIFACTS + _APP_SETTINGS_COLD_FIELDS


def init(mongo_url: str, mongo_db: str) -> None:
    global _client, _db
    _client = AsyncIOMotorClient(mongo_url)
    _db = _client[mongo_db]


def close() -> None:
    global _client, _db, _app_settings_cache, _app_settings_read_at
    if _client:
        _client.close()
    _client = None
    _db = None
    _app_settings_cache = None
    _app_settings_read_at = 0.0


def database() -> AsyncIOMotorDatabase:
    assert _db is not None
    return _db


def coll(name: str):
    return database()[name]


async def app_settings(*, reload: bool = False) -> dict:
    """Freshness-bounded read of the singleton `_app_settings` document.

    The document changes while the process runs, and the writers are OUTSIDE
    this process — EB44's wizard `$addToSet`s `custom_domains` when the builder
    attaches a domain, and the canonical-URL switch rewrites the SEO/url fields
    in place. In-process invalidation can't see those writes, so an unbounded
    memoize serves stale settings forever. The TTL bounds staleness to seconds
    without putting the hot path (the security pipeline runs on every request)
    back on the DB link.

    Why not simply read per request: the same document carries the app's full
    backend source (`functions`, `backend_project`, ...) as build artifacts the
    runtime never reads, and re-reading all of it per request once tripped a
    metered free-tier cluster's transfer cap and throttled the whole app. The
    projection (`_APP_SETTINGS_HOT_EXCLUDED`) keeps every read tiny, and the
    TTL keeps reads rare — both protections, one bounded-staleness contract.

    This read is the HOT one — it must carry only what a request needs to be
    authorized and routed. Anything served on a cold path is projected out and
    fetched there: `app_settings_field` for a single cold field,
    `app_settings_full` for the whole served document.

    Callers needing read-your-write immediacy pass `reload=True` after writing
    (`invite_user` does); `is_user_invited` reads its field fresh directly.
    """
    global _app_settings_cache, _app_settings_read_at
    now = time.monotonic()
    if _app_settings_cache is None or reload or now - _app_settings_read_at > FRESHNESS_SECONDS:
        _app_settings_cache = await coll("_app_settings").find_one(
            {}, {field: 0 for field in _APP_SETTINGS_HOT_EXCLUDED}
        ) or {}
        _app_settings_read_at = now
    return _app_settings_cache


async def app_settings_full() -> dict:
    """The whole served `_app_settings` document, uncached.

    For the surfaces that hand the app document back on the wire —
    `RuntimeApp` declares `agents` and `seo_settings`, so serving them from
    the hot read would drop those fields from the response and diverge from
    Base44. Only the build artifacts (which no response carries) stay
    projected out. Uncached because both callers are cold: the SDK reads the
    runtime app once on boot, and `invite_user` runs per invitation.
    """
    return await coll("_app_settings").find_one(
        {}, {field: 0 for field in _APP_SETTINGS_BUILD_ARTIFACTS}
    ) or {}


async def app_settings_field(name: str) -> dict:
    """One cold field of `_app_settings`, fetched on its own path.

    Keeps the per-request read free of data only one consumer wants — see
    `_APP_SETTINGS_COLD_FIELDS`. Returns `{}` when the field is absent, which
    is what every caller already treated a missing field as.
    """
    doc = await coll("_app_settings").find_one({}, {name: 1}) or {}
    return doc.get(name) or {}


def to_oid(id_str: str) -> ObjectId:
    """Convert a 24-char hex string to an ObjectId for Mongo queries."""
    return ObjectId(id_str)


def prepare_mongo_filter(query: dict) -> dict:
    """Translate logical field names to MongoDB field names in a query filter.

    Handles: id → _id (with ObjectId conversion).
    Recursively processes $and/$or/$nor branches.
    """
    if not isinstance(query, dict):
        return query
    result = {}
    for key, value in query.items():
        if key == "id":
            result["_id"] = _translate_id_value(value)
        elif key in ("$and", "$or", "$nor"):
            if isinstance(value, list):
                result[key] = [prepare_mongo_filter(item) for item in value]
            else:
                result[key] = value
        else:
            result[key] = value
    return result


def _translate_id_value(value):
    if isinstance(value, str):
        try:
            return ObjectId(value)
        except Exception:
            return value
    if isinstance(value, dict):
        out = {}
        for op, val in value.items():
            if op in ("$in", "$nin", "$all"):
                out[op] = [_try_oid(v) for v in val] if isinstance(val, list) else val
            elif op in ("$ne", "$eq"):
                out[op] = _try_oid(val)
            else:
                out[op] = val
        return out
    return value


def _try_oid(value):
    if isinstance(value, str):
        try:
            return ObjectId(value)
        except Exception:
            return value
    return value
