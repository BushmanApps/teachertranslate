"""Google Play purchase verification via the Android Publisher API, and
Google Play's real-time developer notifications.

Unlike iOS — where the store hands the app a signed transaction we verify
offline against Apple's pinned root — Play purchases are opaque tokens
only the Developer API can validate. That needs a Play service account:
the user pastes its JSON once post-migration and it rides the normal
secret rails as IAP_GOOGLE_SA_JSON_B64 (base64 because the raw JSON is
multi-line, which .env files can't carry).

The SERVER tells Google a purchase is done, never the app: an unlock or a
subscription is acknowledged here once it is recorded, a credit pack is
consumed here once its credits are in the buyer's balance (consuming is what
lets the pack be bought again). The kit's purchase plugin is told never to do
either (`autoFinishTransactions: false`), so a purchase the server has not
seen stays pending on Google's side and is handed back at the app's next
launch — and an unacknowledged one is refunded by Google after three days,
which is the right end for a purchase that never reached the buyer.

A real-time developer notification is only a pointer ("this token changed"):
every one is re-read from the API before anything changes, so a forged
message grants nothing.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.errors import AppHTTPException
from app.core.google_service_account import access_token, load_service_account as _load_service_account

_API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
_SCOPE = "https://www.googleapis.com/auth/androidpublisher"

# subscriptionsv2 states that still entitle the user. CANCELED means
# auto-renew is off but the paid period runs until expiryTime.
_ENTITLED_SUB_STATES = {
    "SUBSCRIPTION_STATE_ACTIVE",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
    "SUBSCRIPTION_STATE_CANCELED",
}


def load_service_account(b64: str) -> dict:
    return _load_service_account(b64, "IAP_GOOGLE_SA_JSON_B64")


async def _headers(sa: dict) -> dict:
    return {"Authorization": f"Bearer {await access_token(sa, _SCOPE)}"}


async def verify_purchase(
    sa: dict, package: str, product_id: str, purchase_token: str, product_type: str
) -> dict:
    """Validate a Play purchase token and normalize it for `store`.

    `product_type` "consumable" reads like a one-time product and is NOT
    acknowledged here — `consume` (after the credits are granted) does both.
    """
    headers = await _headers(sa)
    async with httpx.AsyncClient(timeout=20) as client:
        if product_type == "subs":
            return await _verify_subscription(client, headers, package, product_id, purchase_token)
        return await _verify_product(client, headers, package, product_id, purchase_token, product_type)


async def consume(sa: dict, package: str, product_id: str, purchase_token: str) -> None:
    """Tell Google a credit pack has been delivered: it is acknowledged and
    can be bought again. A refused consume is judged by Google's own record
    of the purchase, never by the words of the refusal: one Google already
    counts as consumed (a second delivery of the same notification) is done."""
    headers = await _headers(sa)
    base = f"{_API}/{package}/purchases/products/{product_id}/tokens/{purchase_token}"
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(f"{base}:consume", headers=headers, json={})
        if res.status_code == 200:
            return
        check = await client.get(base, headers=headers)
    if check.status_code == 200 and check.json().get("consumptionState") == 1:
        return
    raise AppHTTPException(502, f"Google Play did not take the consume ({res.status_code}): {res.text[:200]}")


async def voided_purchase_tokens(sa: dict, package: str, since: datetime) -> list[str]:
    """The purchase tokens Google Play voided since `since` — a refund, a
    chargeback, a cancellation, of one-time products and subscriptions — every
    page of the Voided Purchases API (Google keeps 30 days). Needs the service
    account's "View financial data" permission, which in-app purchases already
    ask for."""
    headers = await _headers(sa)
    params: dict = {"type": 1, "maxResults": 1000, "startTime": int(since.replace(tzinfo=timezone.utc).timestamp() * 1000)}
    tokens: list[str] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for _ in range(20):
            res = await client.get(f"{_API}/{package}/purchases/voidedpurchases", headers=headers, params=params)
            if res.status_code != 200:
                raise AppHTTPException(502, f"Google Play did not list the voided purchases ({res.status_code}): {res.text[:200]}")
            body = res.json()
            tokens += [v["purchaseToken"] for v in body.get("voidedPurchases") or [] if v.get("purchaseToken")]
            next_page = (body.get("tokenPagination") or {}).get("nextPageToken")
            if not next_page:
                break
            params["token"] = next_page
    return tokens


async def _verify_subscription(client, headers, package, product_id, purchase_token) -> dict:
    res = await client.get(
        f"{_API}/{package}/purchases/subscriptionsv2/tokens/{purchase_token}", headers=headers
    )
    if res.status_code != 200:
        raise AppHTTPException(400, f"Google Play rejected the purchase token ({res.status_code}): {res.text[:200]}")
    data = res.json()

    state = data.get("subscriptionState")
    items = data.get("lineItems") or []
    item = next((i for i in items if i.get("productId") == product_id), items[0] if items else None)
    if item is None:
        raise AppHTTPException(400, "Subscription has no line items")

    if data.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING" and state in _ENTITLED_SUB_STATES:
        await client.post(
            f"{_API}/{package}/purchases/subscriptions/{item.get('productId', product_id)}"
            f"/tokens/{purchase_token}:acknowledge",
            headers=headers,
            json={},
        )

    account = (data.get("externalAccountIdentifiers") or {}).get("obfuscatedExternalAccountId")
    return {
        "product_id": item.get("productId") or product_id,
        "product_type": "subs",
        "transaction_key": purchase_token,
        "transaction_id": purchase_token,
        "purchased_at": _from_rfc3339(data.get("startTime")),
        "expires_at": _from_rfc3339(item.get("expiryTime")),
        "environment": "Sandbox" if "testPurchase" in data else "Production",
        # EXPIRED isn't revocation — the stored expiry already handles it.
        "revoked": state is not None
        and state not in _ENTITLED_SUB_STATES
        and state != "SUBSCRIPTION_STATE_EXPIRED",
        "quantity": 1,
        "auto_renew_disabled": state == "SUBSCRIPTION_STATE_CANCELED",
        "account_token": account.lower() if account else None,
    }


async def _verify_product(client, headers, package, product_id, purchase_token, product_type) -> dict:
    res = await client.get(
        f"{_API}/{package}/purchases/products/{product_id}/tokens/{purchase_token}", headers=headers
    )
    if res.status_code != 200:
        raise AppHTTPException(400, f"Google Play rejected the purchase token ({res.status_code}): {res.text[:200]}")
    data = res.json()

    purchase_state = data.get("purchaseState")  # 0 purchased, 1 canceled/refunded, 2 pending
    if purchase_state == 2:
        raise AppHTTPException(400, "Purchase is still pending on Google Play — try again once it completes")

    consumable = product_type == "consumable"
    if not consumable and data.get("acknowledgementState") == 0 and purchase_state == 0:
        await client.post(
            f"{_API}/{package}/purchases/products/{product_id}/tokens/{purchase_token}:acknowledge",
            headers=headers,
            json={},
        )

    purchased_ms = data.get("purchaseTimeMillis")
    account = data.get("obfuscatedExternalAccountId")
    return {
        "product_id": product_id,
        "product_type": "consumable" if consumable else "inapp",
        "transaction_key": purchase_token,
        "transaction_id": purchase_token,
        "purchased_at": (
            datetime.fromtimestamp(int(purchased_ms) / 1000, tz=timezone.utc) if purchased_ms else None
        ),
        "expires_at": None,
        "environment": "Sandbox" if data.get("purchaseType") == 0 else "Production",
        "revoked": purchase_state == 1,
        "quantity": int(data.get("quantity") or 1),
        "account_token": account.lower() if account else None,
        # Google's own record that the credits went out — a pack it already
        # counts as consumed is not granted again by a lost ledger.
        "consumed": data.get("consumptionState") == 1,
    }


@dataclass
class Notification:
    """One real-time developer notification, decoded (not yet trusted)."""

    message_id: str
    package: str
    kind: str  # "subscription" | "one_time" | "voided" | "test"
    purchase_token: str | None
    product_id: str | None
    # Google's numeric event code within its kind (2 RENEWED, 12 REVOKED, …).
    event: int | None


def parse_notification(body: dict) -> Notification:
    """The Pub/Sub push envelope → the Play notification inside it.

    Raises AppHTTPException(400) on an envelope that is not one — Pub/Sub then
    retries it, which is right for a malformed delivery and harmless for junk.
    """
    message = (body or {}).get("message") or {}
    try:
        data = json.loads(base64.b64decode(message.get("data") or ""))
    except Exception as e:
        raise AppHTTPException(400, "Not a Google Play notification") from e
    message_id = str(message.get("messageId") or message.get("message_id") or "")
    package = str(data.get("packageName") or "")
    if not message_id or not package:
        raise AppHTTPException(400, "Not a Google Play notification")

    if "subscriptionNotification" in data:
        n = data["subscriptionNotification"] or {}
        return Notification(message_id, package, "subscription", n.get("purchaseToken"), n.get("subscriptionId"), n.get("notificationType"))
    if "oneTimeProductNotification" in data:
        n = data["oneTimeProductNotification"] or {}
        return Notification(message_id, package, "one_time", n.get("purchaseToken"), n.get("sku"), n.get("notificationType"))
    if "voidedPurchaseNotification" in data:
        n = data["voidedPurchaseNotification"] or {}
        return Notification(message_id, package, "voided", n.get("purchaseToken"), None, n.get("productType"))
    if "testNotification" in data:
        return Notification(message_id, package, "test", None, None, None)
    raise AppHTTPException(400, "Google Play notification of an unknown kind")


# subscriptionNotification.notificationType 12: the subscription was revoked
# (refunded) before it expired — subscriptionsv2 then reads EXPIRED, which on
# its own would not say the access was taken back.
SUBSCRIPTION_REVOKED = 12
# oneTimeProductNotification.notificationType 1: a one-time product was bought.
ONE_TIME_PURCHASED = 1


def _from_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
