"""Device registrations — the `_push_devices` system collection.

One doc per (platform, token), bound to the app user whose signed-in app
registered it. Underscore-prefixed so it is invisible to the entity surface
(not in `_entity_schemas` → unreachable through entity routes). Written only
by the app's own registration route; read only by the sender.

Doc shape:
    user_id, platform ("ios"|"android"), token, app_version,
    created_date, updated_date
"""

from __future__ import annotations

from app.core import db
from app.core.responses import utcnow

COLLECTION = "_push_devices"


async def ensure_indexes() -> None:
    await db.coll(COLLECTION).create_index([("platform", 1), ("token", 1)], unique=True)
    await db.coll(COLLECTION).create_index([("user_id", 1)])


async def register(user_id: str, platform: str, token: str, app_version: str | None) -> None:
    """A device belongs to whoever is signed in on it now — a token seen
    again under another account moves to that account."""
    now = utcnow()
    await db.coll(COLLECTION).update_one(
        {"platform": platform, "token": token},
        {
            "$set": {"user_id": user_id, "app_version": app_version, "updated_date": now},
            "$setOnInsert": {"created_date": now},
        },
        upsert=True,
    )


async def unregister(user_id: str, platform: str, token: str) -> None:
    await db.coll(COLLECTION).delete_one({"platform": platform, "token": token, "user_id": user_id})


async def devices_for(user_id: str) -> list[dict]:
    return await db.coll(COLLECTION).find({"user_id": user_id}).to_list(length=200)


async def forget(platform: str, token: str) -> None:
    """The store said the token is dead (the app was uninstalled, the token
    rotated) — it is never tried again."""
    await db.coll(COLLECTION).delete_one({"platform": platform, "token": token})
