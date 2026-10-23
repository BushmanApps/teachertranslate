"""EscapeBase44 in-app purchases — /api/apps/{app_id}/eb44/iap/*.

Our own namespace (the `eb44` segment), not a Base44 replica surface:
Base44 has no IAP support, so there is nothing to be parity-faithful to
and no collision risk with their paths. The wrapped mobile app buys
through StoreKit / Play Billing (the `window.eb44.iap` helper injected
into the SPA), sends the store's proof here, and the verified purchase lands
on the signed-in user — an unlock or a subscription as an entitlement
readable from web and app alike, a credit pack as credits in the user's own
record. The stores' own servers report what changes later (a renewal, a
refund) to the two notification doors below.

iOS proof is a StoreKit 2 signed transaction (verified offline against
Apple's pinned root — zero Apple credentials needed). Android proof is a
purchase token (validated against the Play Developer API — needs the
IAP_GOOGLE_SA_JSON_B64 service account, see MOBILE.md).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import Depends, Request
from fastapi.routing import APIRouter
from pydantic import BaseModel

from app.config import Settings
from app.core.errors import AppHTTPException
from app.core.mobile_identity import android_package, ios_bundle_id
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings
from app.modules.iap import apple, google, packs, store

logger = logging.getLogger("escapebase44.iap")

router = APIRouter(prefix="/api/apps/{app_id}/eb44/iap", tags=["eb44-iap"])


class IapTransaction(BaseModel):
    product_id: str
    # The app's hint; the server decides from the store's own record (iOS)
    # and the declared credit packs (both).
    product_type: Literal["inapp", "subs", "consumable"] = "inapp"
    jws: str | None = None  # iOS: StoreKit 2 jwsRepresentation
    purchase_token: str | None = None  # Android: Play Billing purchase token


class VerifyRequest(BaseModel):
    platform: Literal["ios", "android"]
    transactions: list[IapTransaction]


def _require_user(ctx: AuthedContext) -> dict:
    if not ctx.user:
        raise AppHTTPException(401, "Sign in to use purchases")
    return ctx.user


def _sa(settings: Settings) -> dict:
    if not settings.IAP_GOOGLE_SA_JSON_B64:
        raise AppHTTPException(
            501,
            "Android purchases aren't enabled on this deployment yet — add the "
            "IAP_GOOGLE_SA_JSON_B64 repo secret and redeploy (MOBILE.md walks through it)",
        )
    return google.load_service_account(settings.IAP_GOOGLE_SA_JSON_B64)


async def config(
    app_id: str,
    ctx: AuthedContext = Depends(get_authed_context),
):
    """The signed-in user's store account token — what the app passes to the
    store with each purchase, so the store's own notifications name the buyer."""
    user = _require_user(ctx)
    return {"account_token": await store.account_token(user["id"])}


async def _verified(platform: str, tx: IapTransaction, settings: Settings, declared: dict) -> dict:
    """One app-sent proof → the store's own record of it, normalized."""
    if platform == "ios":
        if not tx.jws:
            raise AppHTTPException(400, "iOS transaction is missing its signed payload (jws)")
        normalized = apple.verify_transaction_jws(tx.jws, ios_bundle_id(settings))
        declared_pack = normalized["product_id"] in declared
        if normalized["product_type"] == "consumable" and not declared_pack:
            raise AppHTTPException(
                400,
                f"{normalized['product_id']!r} is a consumable in App Store Connect but not a declared credit pack "
                "(IAP_CREDIT_PACKS in .escapebase44/config.json) — it stays pending in the App Store until it is declared",
            )
        if declared_pack and normalized["product_type"] != "consumable":
            raise AppHTTPException(
                400,
                f"{normalized['product_id']!r} is declared as a credit pack, but App Store Connect sells it as a "
                f"{'subscription' if normalized['product_type'] == 'subs' else 'non-consumable'} — make it a Consumable there",
            )
        return normalized
    if not tx.purchase_token:
        raise AppHTTPException(400, "Android transaction is missing its purchase token")
    if tx.product_type == "subs":
        kind = "subs"
    else:
        kind = "consumable" if tx.product_id in declared else "inapp"
    return await google.verify_purchase(_sa(settings), android_package(settings), tx.product_id, tx.purchase_token, kind)


async def _settle(user_id: str | None, platform: str, normalized: dict, settings: Settings, declared: dict) -> str:
    """Record a verified purchase for its owner: a credit pack delivered, an
    unlock or a subscription granted. Returns what happened."""
    owner = await store.owner_of(user_id, platform, normalized)
    if normalized["product_type"] != "consumable":
        await store.grant(owner, platform, normalized)
        return "entitled"
    if owner is None:
        # A store notification about a pack nobody in this app has claimed and
        # whose token names no one: the app sends it at its next launch.
        return "unclaimed"
    outcome = await store.deliver(owner, platform, normalized, declared[normalized["product_id"]])
    if platform == "android" and outcome in ("delivered", "already") and not normalized.get("consumed"):
        try:
            await google.consume(_sa(settings), android_package(settings), normalized["product_id"], normalized["transaction_key"])
        except AppHTTPException:
            # Delivered, not yet consumed: Google hands it back at the next
            # launch, the delivery answers "already", and the consume runs again.
            logger.warning("consume of %s failed; retried at the next sync", normalized["product_id"], exc_info=True)
    return outcome


async def verify(
    app_id: str,
    body: VerifyRequest,
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    """Verify store transactions and record them for the signed-in user.

    Per-transaction failures don't abort the batch (the app's launch sync
    sends every pending and current purchase at once — one stale item must
    not block the rest): rejects are reported alongside whatever verified.
    `settled` names every transaction the app may now finish with the store
    (iOS — Android's are acknowledged or consumed here); a rejected one is
    left pending so the store hands it back.
    """
    user = _require_user(ctx)
    if not body.transactions:
        raise AppHTTPException(400, "No transactions to verify")
    if body.platform == "android":
        _sa(settings)  # config-level: fail the whole batch, honestly
    declared = packs.parse(settings.IAP_CREDIT_PACKS)

    delivered: list[dict] = []
    settled: list[str] = []
    rejected: list[dict] = []
    for tx in body.transactions:
        try:
            normalized = await _verified(body.platform, tx, settings, declared)
            outcome = await _settle(user["id"], body.platform, normalized, settings, declared)
            settled.append(normalized["transaction_id"])
            if outcome == "delivered":
                pack = declared[normalized["product_id"]]
                delivered.append({
                    "product_id": normalized["product_id"],
                    "transaction_id": normalized["transaction_id"],
                    "field": pack.field,
                    "amount": pack.amount * max(int(normalized.get("quantity") or 1), 1),
                })
        except AppHTTPException as e:
            rejected.append({"product_id": tx.product_id, "reason": e.message})

    return {
        "entitlements": await store.active_for_user(user["id"], settings),
        "delivered": delivered,
        "settled": settled,
        "rejected": rejected,
    }


async def entitlements(
    app_id: str,
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    user = _require_user(ctx)
    return {"entitlements": await store.active_for_user(user["id"], settings)}


# ── the stores' own servers ──────────────────────────────────────────────
#
# Public by construction: neither store has a session. Apple signs every
# notification (verified offline, like a transaction); a Google notification
# is only a pointer, re-read from Google before anything changes. Both are
# processed BEFORE they are recorded, so a delivery that fails half way is
# retried by the store and every step is idempotent.


async def apple_notifications(app_id: str, request: Request, settings: Settings = Depends(get_settings)):
    body = await request.json()
    n = apple.verify_notification(str((body or {}).get("signedPayload") or ""), ios_bundle_id(settings))
    if await store.find_notification("apple", n.uuid):
        return {"ok": True}
    tx = n.transaction
    if tx is not None:
        declared = packs.parse(settings.IAP_CREDIT_PACKS)
        if n.type == "REVOKE":
            tx = {**tx, "revoked": True}
        if tx["product_type"] == "consumable":
            if tx["revoked"] or n.type in ("REFUND", "REVOKE"):
                await store.revoke("ios", tx["transaction_key"])
            elif n.type == "ONE_TIME_CHARGE" and tx["product_id"] in declared:
                await _settle(None, "ios", tx, settings, declared)
        else:
            owner = await store.owner_of(None, "ios", tx)
            await store.grant(owner, "ios", tx)
    await store.first_sight("apple", n.uuid, {"type": n.type, "subtype": n.subtype, "environment": n.environment})
    return {"ok": True}


async def google_notifications(app_id: str, request: Request, settings: Settings = Depends(get_settings)):
    n = google.parse_notification(await request.json())
    if n.package != android_package(settings):
        logger.warning("Play notification for %s, but this app is %s — ignored", n.package, android_package(settings))
        return {"ok": True}
    if await store.find_notification("google", n.message_id):
        return {"ok": True}
    if n.kind != "test":
        if not settings.IAP_GOOGLE_SA_JSON_B64:
            logger.warning("Play notification received with no service account to read it with — ignored")
            return {"ok": True}
        await _play_event(n, settings)
    await store.first_sight("google", n.message_id, {"type": n.kind, "event": n.event})
    return {"ok": True}


async def _play_event(n: google.Notification, settings: Settings) -> None:
    sa = _sa(settings)
    package = android_package(settings)
    declared = packs.parse(settings.IAP_CREDIT_PACKS)
    if n.kind == "voided":
        await store.revoke("android", n.purchase_token)
        return
    if n.kind == "subscription":
        tx = await google.verify_purchase(sa, package, n.product_id, n.purchase_token, "subs")
        if n.event == google.SUBSCRIPTION_REVOKED:
            tx = {**tx, "revoked": True}
        owner = await store.owner_of(None, "android", tx)
        await store.grant(owner, "android", tx)
        return
    if n.kind == "one_time" and n.event == google.ONE_TIME_PURCHASED:
        kind = "consumable" if n.product_id in declared else "inapp"
        tx = await google.verify_purchase(sa, package, n.product_id, n.purchase_token, kind)
        await _settle(None, "android", tx, settings, declared)


async def notifications_status(app_id: str):
    """When each store last reached this app — what the App Store card shows
    to say the notification address is set up and working."""
    return {"apple": await store.last_received("apple"), "google": await store.last_received("google")}


router.add_api_route("/config", config, methods=["GET"])
router.add_api_route("/verify", verify, methods=["POST"])
router.add_api_route("/entitlements", entitlements, methods=["GET"])
router.add_api_route("/apple/notifications", apple_notifications, methods=["POST"])
router.add_api_route("/google/notifications", google_notifications, methods=["POST"])
router.add_api_route("/notifications", notifications_status, methods=["GET"])
