"""Synchronize the Teacher Translate Pro entitlement into UserProfile."""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from bson import ObjectId

from app.config import Settings
from app.core import db
from app.core.responses import utcnow_naive
from app.modules.entities.services import serialize_for_automation
from app.modules.iap import store

PRO_PRODUCT_ID = "teacher_translate_pro_users"
REFUND_WINDOW = timedelta(days=14)


def _effective(store_active: bool, profile: dict) -> bool:
    if profile.get("lifetime_pro"):
        return True
    if profile.get("admin_override") == "grant":
        return True
    if profile.get("admin_override") == "revoke":
        return False
    return store_active


async def reconcile(user: dict, settings: Settings) -> dict:
    """Make the native subscription and the app profile agree.

    This is called after every verified purchase, entitlement read, and store
    notification.  It deliberately writes the normal entity change event so
    the existing Pro welcome-email workflow remains the delivery mechanism.
    """
    user_id = str(user.get("id") or user["_id"])
    email = (user.get("email") or "").lower()
    active = await store.active_for_user(user_id, settings)
    pro = [row for row in active if row.get("product_id") == PRO_PRODUCT_ID and row.get("product_type") == "subs"]
    entitlement = max(pro, key=lambda row: row.get("expires_at") or "", default=None)
    raw = None
    if entitlement:
        raw = await db.coll(store.COLLECTION).find_one({
            "user_id": user_id,
            "product_id": PRO_PRODUCT_ID,
            "product_type": "subs",
            "revoked": {"$ne": True},
        }, sort=[("expires_at", -1), ("updated_date", -1)])

    profiles = await db.coll("UserProfile").find({"$or": [{"created_by_id": user_id}, {"email": email}]}).to_list(50)
    profile = next((row for row in profiles if row.get("consent_given_date")), profiles[0] if profiles else None)
    now = utcnow_naive()
    store_active = entitlement is not None
    renewal = entitlement.get("expires_at")[:10] if entitlement and entitlement.get("expires_at") else None

    if profile is None:
        profile = {
            "_id": ObjectId(), "created_by_id": user_id, "created_by": email,
            "created_date": now, "updated_date": now, "is_sample": False,
            "email": email, "user_name": user.get("full_name") or email,
            "scans_used": 0, "is_subscribed": False,
        }
        await db.coll("UserProfile").insert_one(profile)
        old = None
        op = "create"
    else:
        old = dict(profile)
        op = "update"

    was_subscribed = bool(profile.get("is_subscribed"))
    subscribed = _effective(store_active, profile)
    updates = {
        "is_subscribed": subscribed,
        "updated_date": now,
        "email": email or profile.get("email"),
    }
    if renewal:
        updates["subscription_renewal"] = renewal
    if raw and raw.get("auto_renew_disabled") is not None:
        updates["auto_renew_disabled"] = bool(raw["auto_renew_disabled"])
        updates["renewal_warning_sent"] = False
    if store_active and not was_subscribed:
        blacklisted = await db.coll("RefundBlacklist").find_one({"email": email}) if email else None
        if not blacklisted:
            updates["refund_eligible"] = True
            updates["refund_eligible_until"] = now + REFUND_WINDOW
    if not store_active and not profile.get("lifetime_pro") and profile.get("admin_override") not in ("grant",):
        updates["refund_eligible"] = False

    await db.coll("UserProfile").update_one({"_id": profile["_id"]}, {"$set": updates})
    updated = {**profile, **updates}
    try:
        from app.core.automations import dispatch_entity
        await dispatch_entity(
            "UserProfile", op, serialize_for_automation("UserProfile", updated),
            SimpleNamespace(token_payload=None, user=None),
            old_data=serialize_for_automation("UserProfile", old) if old else None,
        )
    except Exception:
        pass
    return {
        "is_subscribed": subscribed,
        "subscription_renewal": renewal or updated.get("subscription_renewal"),
        "auto_renew_disabled": bool(updated.get("auto_renew_disabled")),
        "refund_eligible": bool(updated.get("refund_eligible")),
        "refund_eligible_until": updated.get("refund_eligible_until"),
    }
