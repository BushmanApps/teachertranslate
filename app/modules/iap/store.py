"""What the stores sold this app's users — the `_iap_*` system collections.

Underscore-prefixed, so they are invisible to the entity surface (not in
`_entity_schemas` → unreachable and un-writable through entity routes; users
cannot self-grant). The app reads entitlements only through
GET /eb44/iap/entitlements (or the injected `window.eb44.iap` helper); a
credit pack lands in the app's own data, on the buyer's User record.

`_iap_entitlements` — one doc per store purchase, keyed (platform,
transaction_key) uniquely:
    user_id (None while a notification knows a purchase no app has
    claimed yet), platform ("ios"|"android"), product_id, product_type
    ("inapp" | "subs" | "consumable"), transaction_key (an unlock or a
    subscription: Apple's originalTransactionId / Play's purchaseToken; a
    credit pack: its own transactionId / purchaseToken), purchased_at,
    expires_at, environment, revoked, account_token, created_date,
    updated_date — and for a credit pack: quantity, credits {field,
    amount}, claimed_at, granted_at, refunded_at.

`_iap_accounts` — the store account token of each user (the UUID the app
passes to Apple as appAccountToken and to Google as the obfuscated account
id), so a purchase a notification reports is found its buyer even if the
app never got to send it.

`_iap_notifications` — every store notification taken in, by its own id
(Apple's notificationUUID, Pub/Sub's messageId): a redelivery is acknowledged
and changes nothing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.core import db
from app.core.errors import AppHTTPException
from app.core.responses import utcnow_naive
from app.modules.iap.packs import Pack

logger = logging.getLogger("escapebase44.iap")

COLLECTION = "_iap_entitlements"
ACCOUNTS = "_iap_accounts"
NOTIFICATIONS = "_iap_notifications"
# When Google's voided purchases were last read, and from when the next read
# starts (one document).
SYNC = "_iap_sync"
# How often they are read (Google's quota: 6,000 calls a day per app).
VOIDED_EVERY = timedelta(minutes=5)

# A credit pack's claim that never reached "granted" this long after it was
# taken is a delivery whose process died between two writes; the next one
# takes it over. (The one window where a grant can repeat: the process ended
# after the credits were added and before the row said so — two consecutive
# awaits.)
CLAIM_STALE_AFTER = timedelta(minutes=2)


async def ensure_indexes() -> None:
    await db.coll(COLLECTION).create_index([("platform", 1), ("transaction_key", 1)], unique=True)
    await db.coll(COLLECTION).create_index([("user_id", 1)])
    await db.coll(ACCOUNTS).create_index([("user_id", 1)], unique=True)
    await db.coll(ACCOUNTS).create_index([("token", 1)], unique=True)
    await db.coll(NOTIFICATIONS).create_index([("source", 1), ("id", 1)], unique=True)


# ── the store account token ──────────────────────────────────────────────


async def account_token(user_id: str) -> str:
    """This user's store account token — minted once, the same ever after."""
    coll = db.coll(ACCOUNTS)
    doc = await coll.find_one({"user_id": user_id})
    if doc:
        return doc["token"]
    try:
        await coll.insert_one({"user_id": user_id, "token": str(uuid.uuid4()), "created_date": utcnow_naive()})
    except DuplicateKeyError:
        pass  # a second request minted it first
    return (await coll.find_one({"user_id": user_id}))["token"]


async def user_for_token(token: str | None) -> str | None:
    if not token:
        return None
    doc = await db.coll(ACCOUNTS).find_one({"token": token.lower()})
    return doc["user_id"] if doc else None


async def owner_of(user_id: str | None, platform: str, tx: dict) -> str | None:
    """Who a purchase belongs to: whoever already holds it, else the account
    its store token names, else the caller. Raises 409 when the caller is not
    that person — one purchase never becomes two people's."""
    existing = await db.coll(COLLECTION).find_one({"platform": platform, "transaction_key": tx["transaction_key"]})
    holder = existing.get("user_id") if existing else None
    named = await user_for_token(tx.get("account_token"))
    owner = holder or named or user_id
    if user_id is not None and owner != user_id:
        raise AppHTTPException(409, "This purchase is already linked to a different account")
    return owner


# ── unlocks and subscriptions ────────────────────────────────────────────


async def grant(user_id: str | None, platform: str, tx: dict) -> None:
    """Upsert a verified unlock or subscription as its owner's entitlement.

    `user_id` is None when a store notification reports a purchase whose buyer
    is not known yet: it is kept unbound and bound by the first account that
    verifies it (owner_of has already refused anyone else).
    """
    coll = db.coll(COLLECTION)
    key = {"platform": platform, "transaction_key": tx["transaction_key"]}
    now = _now()
    fields = {
        "product_id": tx["product_id"],
        "product_type": tx["product_type"],
        "purchased_at": tx["purchased_at"],
        "expires_at": tx["expires_at"],
        "environment": tx["environment"],
        "revoked": tx["revoked"],
        "updated_date": now,
    }
    if tx.get("account_token"):
        fields["account_token"] = tx["account_token"]
    if "auto_renew_disabled" in tx:
        fields["auto_renew_disabled"] = tx["auto_renew_disabled"]
    if user_id is not None:
        fields["user_id"] = user_id
    await coll.update_one(
        key,
        {"$set": fields, "$setOnInsert": {"created_date": now, **({} if user_id is not None else {"user_id": None})}},
        upsert=True,
    )


async def revoke(platform: str, transaction_key: str) -> dict | None:
    """Take a purchase back (a refund, a revoke): an entitlement stops
    entitling; a credit pack's credits come off the balance, once."""
    doc = await db.coll(COLLECTION).find_one_and_update(
        {"platform": platform, "transaction_key": transaction_key},
        {"$set": {"revoked": True, "updated_date": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if doc and doc.get("product_type") == "consumable":
        await _take_back(doc)
    return doc


# ── credit packs ─────────────────────────────────────────────────────────


async def deliver(user_id: str, platform: str, tx: dict, pack: Pack) -> str:
    """Add a credit pack's credits to its buyer's balance, exactly once.

    Returns "delivered" (added now), "already" (added before — a resend from
    the launch sync, a notification arriving after the app) or "refunded"
    (the store took the purchase back before it was ever added). Raises 409
    while another request is delivering the same purchase (the app retries at
    its next launch; the store still holds it), and on a balance field that is
    not a number.
    """
    coll = db.coll(COLLECTION)
    key = {"platform": platform, "transaction_key": tx["transaction_key"]}
    amount = pack.amount * max(int(tx.get("quantity") or 1), 1)
    now = _now()

    row = await coll.find_one(key)
    if row and row.get("granted_at"):
        return "already"
    if (row and row.get("revoked")) or tx["revoked"]:
        await coll.update_one(key, {"$set": {"revoked": True, "updated_date": now}}, upsert=False)
        return "refunded"

    claim = {
        "user_id": user_id,
        "product_id": tx["product_id"],
        "product_type": "consumable",
        "purchased_at": tx["purchased_at"],
        "expires_at": None,
        "environment": tx["environment"],
        "revoked": False,
        "quantity": max(int(tx.get("quantity") or 1), 1),
        "credits": {"field": pack.field, "amount": amount},
        "account_token": tx.get("account_token"),
        "claimed_at": now,
        "granted_at": None,
        "refunded_at": None,
        "updated_date": now,
    }
    if row is None:
        try:
            await coll.insert_one({**key, **claim, "created_date": now})
            claimed = True
        except DuplicateKeyError:
            claimed = False
    else:
        claimed = False
    if not claimed:
        taken = await coll.find_one_and_update(
            {**key, "granted_at": None, "revoked": {"$ne": True},
             "$or": [{"claimed_at": None}, {"claimed_at": {"$lt": now - CLAIM_STALE_AFTER}}]},
            {"$set": claim},
        )
        if taken is None:
            again = await coll.find_one(key)
            if again and again.get("granted_at"):
                return "already"
            raise AppHTTPException(409, "This purchase is being delivered — it will be in the balance in a moment")

    try:
        before = await _add_to_balance(user_id, pack.field, amount)
    except Exception:
        # Not added — release the claim so the store's redelivery can try again.
        await coll.update_one(key, {"$set": {"claimed_at": None}})
        raise
    await coll.update_one(key, {"$set": {"granted_at": _now(), "updated_date": _now()}})
    await _user_changed(before, pack.field, amount)
    return "delivered"


async def _take_back(doc: dict) -> None:
    """A refunded credit pack's credits off the balance — once. A pack that was
    never added (refunded before delivery) takes nothing."""
    taken = await db.coll(COLLECTION).find_one_and_update(
        {"_id": doc["_id"], "granted_at": {"$ne": None}, "refunded_at": None},
        {"$set": {"refunded_at": _now()}},
    )
    if taken and taken.get("user_id"):
        credits = taken.get("credits") or {}
        try:
            before = await _add_to_balance(taken["user_id"], credits["field"], -int(credits["amount"]))
            await _user_changed(before, credits["field"], -int(credits["amount"]))
        except Exception:
            logger.warning("refund of %s could not take the credits back", taken.get("product_id"), exc_info=True)


async def _add_to_balance(user_id: str, field: str, amount: int) -> dict:
    """One atomic increment on the user's own record; returns the record as
    it was before. The field is created at the amount when the user has none."""
    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError) as e:
        raise AppHTTPException(404, "User not found") from e
    try:
        before = await db.coll("User").find_one_and_update(
            {"_id": oid},
            {"$inc": {field: amount}, "$set": {"updated_date": utcnow_naive()}},
            return_document=ReturnDocument.BEFORE,
        )
    except OperationFailure as e:
        raise AppHTTPException(
            409,
            f"The user's {field} is not a number, so the credits could not be added — "
            "the app has to keep it as a number (IAP_CREDIT_PACKS in .escapebase44/config.json names it)",
        ) from e
    if before is None:
        raise AppHTTPException(404, "User not found")
    return before


async def _user_changed(before: dict, field: str, amount: int) -> None:
    """The user's record changed: the app's own User automations and workflows
    hear it like any single-record update (Base44's rule: single writes fire,
    service role included). Never fatal to the purchase."""
    try:
        from app.core.automations import dispatch_entity
        from app.modules.entities.services import serialize_for_automation

        after = dict(before)
        after[field] = (before.get(field) or 0) + amount
        after["updated_date"] = utcnow_naive()
        await dispatch_entity(
            "User",
            "update",
            serialize_for_automation("User", after),
            SimpleNamespace(token_payload=None, user=None),
            old_data=serialize_for_automation("User", before),
        )
    except Exception:
        logger.debug("User automations after a credit grant failed (non-fatal)", exc_info=True)


# ── store notifications ──────────────────────────────────────────────────


async def find_notification(source: str, notification_id: str) -> bool:
    """Whether this store notification was taken in before (a redelivery)."""
    return await db.coll(NOTIFICATIONS).find_one({"source": source, "id": notification_id}) is not None


async def first_sight(source: str, notification_id: str, meta: dict) -> bool:
    """Record a store notification once it has been acted on; False when it
    had been taken in before."""
    try:
        await db.coll(NOTIFICATIONS).insert_one({"source": source, "id": notification_id, "received_at": _now(), **meta})
        return True
    except DuplicateKeyError:
        return False


async def last_received(source: str) -> dict | None:
    """The newest notification from a store — the card's "it arrives" check
    (two in one millisecond: the one taken in last)."""
    doc = await db.coll(NOTIFICATIONS).find_one({"source": source}, sort=[("received_at", -1), ("_id", -1)])
    if not doc:
        return None
    received = doc["received_at"]
    return {"type": doc.get("type"), "received_at": _aware(received).isoformat()}


async def find(platform: str, transaction_key: str) -> dict | None:
    return await db.coll(COLLECTION).find_one({"platform": platform, "transaction_key": transaction_key})


# ── reading ──────────────────────────────────────────────────────────────


async def active_for_user(user_id: str, settings) -> list[dict]:
    """The user's currently-active entitlements, oldest first (credit packs
    are not entitlements — their credits are in the user's own record).

    Expired Android subscriptions get one lazy re-check against Google
    (renewals happen store-side; the stored purchase token stays valid) so a
    web session sees a renewal even where no notification reached the app;
    what Google voided is taken back first (sync_voided).
    """
    await sync_voided(settings)
    docs = await db.coll(COLLECTION).find(
        {"user_id": user_id, "product_type": {"$ne": "consumable"}}
    ).sort("created_date", 1).to_list(200)

    out = []
    for doc in docs:
        if (
            doc["platform"] == "android"
            and doc["product_type"] == "subs"
            and not doc.get("revoked")
            and _expired(doc.get("expires_at"))
            and settings.IAP_GOOGLE_SA_JSON_B64
        ):
            doc = await _refresh_android_subscription(doc, settings)
        if _is_active(doc):
            out.append(_serialize(doc))
    return out


async def sync_voided(settings) -> None:
    """Google's refunds, chargebacks and cancellations, pulled from Google
    Play's own list of the purchases it voided: an unlock stops entitling and
    a credit pack's credits come off, with nothing for the owner to set up
    (Google's push notifications, when an owner points them here, bring the
    same news sooner; both end in `revoke`, which acts once).

    Read at most every five minutes, by one request at a time, once the app
    has sold anything on Android. A read that fails is logged and tried again
    five minutes later; the read of entitlements it rides on never fails for it.
    """
    if not settings.IAP_GOOGLE_SA_JSON_B64:
        return
    if not await db.coll(COLLECTION).find_one({"platform": "android", "revoked": {"$ne": True}}, {"_id": 1}):
        return
    now = _now()
    try:
        last = await db.coll(SYNC).find_one_and_update(
            {"_id": "google-voided", "checked_at": {"$lt": now - VOIDED_EVERY}},
            {"$set": {"checked_at": now}},
            upsert=True,
        )
    except DuplicateKeyError:
        return  # read in the last five minutes, or being read right now
    from app.core.mobile_identity import android_package
    from app.modules.iap import google

    try:
        sa = google.load_service_account(settings.IAP_GOOGLE_SA_JSON_B64)
        tokens = await google.voided_purchase_tokens(sa, android_package(settings), (last or {}).get("since") or now - timedelta(days=30))
    except Exception as e:
        logger.warning("Google's voided purchases could not be read: %s", e)
        return
    live = await db.coll(COLLECTION).find(
        {"platform": "android", "transaction_key": {"$in": tokens}, "revoked": {"$ne": True}}, {"transaction_key": 1}
    ).to_list(None) if tokens else []
    for doc in live:
        await revoke("android", doc["transaction_key"])
    # The next read starts a little before this one (a purchase Google files
    # as voided late is still caught; taking back twice does nothing).
    await db.coll(SYNC).update_one({"_id": "google-voided"}, {"$set": {"since": now - timedelta(minutes=10)}})


async def _refresh_android_subscription(doc: dict, settings) -> dict:
    from app.core.mobile_identity import android_package
    from app.modules.iap import google

    try:
        sa = google.load_service_account(settings.IAP_GOOGLE_SA_JSON_B64)
        tx = await google.verify_purchase(sa, android_package(settings), doc["product_id"], doc["transaction_key"], "subs")
    except Exception as e:
        # Store-side check failed (Google hiccup, token voided...). The
        # entitlement stays expired until the next successful check, the next
        # notification or the app's next launch sync — never grants on doubt.
        logger.warning("android subscription re-check failed for %s: %s", doc["product_id"], e)
        return doc

    await grant(doc["user_id"], "android", tx)
    return {**doc, **tx}


def _is_active(doc: dict) -> bool:
    return not doc.get("revoked") and not _expired(doc.get("expires_at"))


def _expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    return _aware(expires_at) <= datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    # Motor returns naive-UTC datetimes; normalize before comparing.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _now() -> datetime:
    return utcnow_naive()


def _serialize(doc: dict) -> dict:
    expires_at = doc.get("expires_at")
    purchased_at = doc.get("purchased_at")
    return {
        "product_id": doc["product_id"],
        "platform": doc["platform"],
        "product_type": doc["product_type"],
        "purchased_at": _aware(purchased_at).isoformat() if purchased_at else None,
        "expires_at": _aware(expires_at).isoformat() if expires_at else None,
        "environment": doc.get("environment", "Production"),
    }
