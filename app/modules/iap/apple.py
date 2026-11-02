"""StoreKit 2 transactions and App Store Server Notifications — verified
offline, zero Apple credentials.

Everything Apple signs for an app arrives as a JWS whose x5c header carries
the full certificate chain: the transaction the purchase plugin hands the web
layer (`jwsRepresentation`), and the notification Apple's server POSTs to the
app the moment something changes (V2 `signedPayload`, with the transaction
inside it signed the same way). We verify the chain down to Apple's pinned
Root CA G3 and the JWS signature with the leaf key, so nothing can be forged —
and the deployment needs no App Store Connect key for any of it.

Freshness: the notification is the moment (a renewal, a refund, an expiry
reach the backend as they happen — the App Store card's build sets the app's
notification address in App Store Connect); the app's launch sync re-sends
current transactions too, so an app whose address was never set still
converges the next time someone opens it.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey

from app.core.errors import AppHTTPException

# Apple Root CA - G3 (https://www.apple.com/certificateauthority/) — the
# trust anchor every StoreKit 2 transaction chain terminates at. Public
# certificate, valid through 2039.
APPLE_ROOT_CA_G3_PEM = b"""-----BEGIN CERTIFICATE-----
MIICQzCCAcmgAwIBAgIILcX8iNLFS5UwCgYIKoZIzj0EAwMwZzEbMBkGA1UEAwwS
QXBwbGUgUm9vdCBDQSAtIEczMSYwJAYDVQQLDB1BcHBsZSBDZXJ0aWZpY2F0aW9u
IEF1dGhvcml0eTETMBEGA1UECgwKQXBwbGUgSW5jLjELMAkGA1UEBhMCVVMwHhcN
MTQwNDMwMTgxOTA2WhcNMzkwNDMwMTgxOTA2WjBnMRswGQYDVQQDDBJBcHBsZSBS
b290IENBIC0gRzMxJjAkBgNVBAsMHUFwcGxlIENlcnRpZmljYXRpb24gQXV0aG9y
aXR5MRMwEQYDVQQKDApBcHBsZSBJbmMuMQswCQYDVQQGEwJVUzB2MBAGByqGSM49
AgEGBSuBBAAiA2IABJjpLz1AcqTtkyJygRMc3RCV8cWjTnHcFBbZDuWmBSp3ZHtf
TjjTuxxEtX/1H7YyYl3J6YRbTzBPEVoA/VhYDKX1DyxNB0cTddqXl5dvMVztK517
IDvYuVTZXpmkOlEKMaNCMEAwHQYDVR0OBBYEFLuw3qFYM4iapIqZ3r6966/ayySr
MA8GA1UdEwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgEGMAoGCCqGSM49BAMDA2gA
MGUCMQCD6cHEFl4aXTQY2e3v9GwOAEZLuN+yRhHFD/3meoyhpmvOwgPUnPWTxnS4
at+qIxUCMG1mihDK1A3UT82NQz60imOlM27jbdoXt2QfyFMm+YhidDkLF1vLUagM
6BgD56KyKA==
-----END CERTIFICATE-----"""

_APPLE_ROOT_FINGERPRINT = x509.load_pem_x509_certificate(
    APPLE_ROOT_CA_G3_PEM
).fingerprint(hashes.SHA256())

# A consumable is a credit pack: each purchase is its own transaction (its
# transactionId), granted once into the buyer's balance (store.deliver). A
# non-consumable or a subscription is an entitlement keyed by its ORIGINAL
# transaction, which every renewal and restore shares. A non-renewing
# subscription carries no expiry in the JWS (its length is the app's own
# logic) — refused rather than mis-granted as a forever-entitlement.
_SUPPORTED_TYPES = {
    "Consumable": "consumable",
    "Non-Consumable": "inapp",
    "Auto-Renewable Subscription": "subs",
}


def _verified_payload(token: str, what: str) -> dict:
    """The claims of a JWS Apple signed, after its chain and signature are
    verified. Raises AppHTTPException(400) on anything that is not Apple's."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as e:
        raise AppHTTPException(400, f"Malformed App Store {what}") from e

    x5c = header.get("x5c") or []
    if len(x5c) < 2:
        raise AppHTTPException(400, f"App Store {what} is missing its certificate chain")

    try:
        certs = [x509.load_der_x509_certificate(base64.b64decode(c)) for c in x5c]
    except Exception as e:
        raise AppHTTPException(400, f"App Store {what} carries an unreadable certificate chain") from e

    _verify_chain(certs)

    try:
        return jwt.decode(
            token,
            key=certs[0].public_key(),
            algorithms=["ES256"],
            options={"verify_aud": False},
        )
    except jwt.InvalidTokenError as e:
        raise AppHTTPException(400, f"App Store {what} signature is invalid") from e


def verify_transaction_jws(jws_token: str, expected_bundle_id: str) -> dict:
    """Verify a StoreKit 2 signed transaction and normalize it.

    Returns the normalized transaction `store` expects. Raises
    AppHTTPException(400) on anything structurally wrong (bad chain, wrong
    app, unsupported product type). A refunded transaction is NOT an error —
    it returns with revoked=True so the stored state follows it.
    """
    return _normalize(_verified_payload(jws_token, "transaction"), expected_bundle_id)


def _normalize(payload: dict, expected_bundle_id: str) -> dict:
    if payload.get("bundleId") != expected_bundle_id:
        raise AppHTTPException(
            400,
            f"Transaction belongs to bundle {payload.get('bundleId')!r}, "
            f"but this app is {expected_bundle_id!r} (the App Store bundle id on your EscapeBase44 page decides this)",
        )

    tx_type = payload.get("type")
    product_type = _SUPPORTED_TYPES.get(tx_type)
    if product_type is None:
        raise AppHTTPException(
            400,
            f"Unsupported purchase type {tx_type!r} — credit packs, one-time unlocks and auto-renewable subscriptions are supported",
        )

    transaction_id = str(payload["transactionId"])
    original = str(payload.get("originalTransactionId") or transaction_id)
    token = payload.get("appAccountToken")
    return {
        "product_id": payload["productId"],
        "product_type": product_type,
        # The key a purchase is stored and found under: each credit pack its
        # own; an unlock or a subscription its first transaction, which
        # renewals, restores and notifications all name.
        "transaction_key": transaction_id if product_type == "consumable" else original,
        "transaction_id": transaction_id,
        "purchased_at": _from_ms(payload.get("purchaseDate")),
        "expires_at": _from_ms(payload.get("expiresDate")),
        "environment": payload.get("environment", "Production"),
        "revoked": payload.get("revocationDate") is not None,
        "quantity": int(payload.get("quantity") or 1),
        "account_token": str(token).lower() if token else None,
    }


@dataclass
class Notification:
    """One App Store Server Notification (V2), verified."""

    uuid: str
    type: str
    subtype: str | None
    environment: str
    # The transaction it is about, normalized like a verified purchase —
    # None for a notification that carries none (TEST, the summary ones).
    transaction: dict | None
    auto_renew_disabled: bool | None


def verify_notification(signed_payload: str, expected_bundle_id: str) -> Notification:
    """Verify the V2 `signedPayload` Apple POSTs and the transaction inside it.

    A notification about another app (a shared address, a stale config) is
    refused like a foreign transaction. A transaction of a type the module does
    not keep (a non-renewing subscription) is not an error here: the
    notification is still Apple's and is acknowledged; it simply changes
    nothing.
    """
    payload = _verified_payload(signed_payload, "notification")
    data = payload.get("data") or {}
    if data.get("bundleId") not in (None, expected_bundle_id):
        raise AppHTTPException(
            400,
            f"Notification is for bundle {data.get('bundleId')!r}, but this app is {expected_bundle_id!r}",
        )
    transaction = None
    auto_renew_disabled = None
    renewal = data.get("signedRenewalInfo")
    if renewal:
        renewal_info = _verified_payload(renewal, "renewal info")
        if renewal_info.get("autoRenewStatus") is not None:
            auto_renew_disabled = str(renewal_info["autoRenewStatus"]) == "0"
    signed = data.get("signedTransactionInfo")
    if signed:
        inner = _verified_payload(signed, "transaction")
        if inner.get("type") in _SUPPORTED_TYPES:
            transaction = _normalize(inner, expected_bundle_id)
    uuid = payload.get("notificationUUID")
    if not uuid:
        raise AppHTTPException(400, "App Store notification has no notificationUUID")
    return Notification(
        uuid=str(uuid),
        type=str(payload.get("notificationType") or ""),
        subtype=payload.get("subtype"),
        environment=str(data.get("environment") or "Production"),
        transaction=transaction,
        auto_renew_disabled=auto_renew_disabled,
    )


def _verify_chain(certs: list[x509.Certificate]) -> None:
    now = datetime.now(timezone.utc)
    for cert in certs:
        if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
            raise AppHTTPException(400, "App Store certificate chain contains an expired certificate")

    for child, issuer in zip(certs, certs[1:]):
        _verify_cert_signature(child, issuer)

    if certs[-1].fingerprint(hashes.SHA256()) != _APPLE_ROOT_FINGERPRINT:
        raise AppHTTPException(400, "App Store transaction does not chain to Apple's root CA")


def _verify_cert_signature(child: x509.Certificate, issuer: x509.Certificate) -> None:
    pub = issuer.public_key()
    try:
        if isinstance(pub, EllipticCurvePublicKey):
            pub.verify(child.signature, child.tbs_certificate_bytes, ec.ECDSA(child.signature_hash_algorithm))
        else:
            # Apple's chain is all-EC today; RSA handled for chain rotations.
            pub.verify(child.signature, child.tbs_certificate_bytes, padding.PKCS1v15(), child.signature_hash_algorithm)
    except Exception as e:
        raise AppHTTPException(400, "App Store certificate chain failed verification") from e


def _from_ms(ms) -> datetime | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
