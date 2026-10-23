"""The ids the stores know this app by, one per platform — and the files the
phones and the ad network read off the app's own address, derived from them.

The mobile kit writes the ids as facts (MOBILE_IOS_BUNDLE_ID,
MOBILE_ANDROID_PACKAGE) when the owner sets them; the runner derives them
from the native project's namespace otherwise. MOBILE_BUNDLE_ID is the single
name a fork deployed before the per-platform pair read; the default is what
the kit generates for every app.

Derived, never typed: a phone asks the app's address which app may open its
links (Apple's apple-app-site-association, Google's assetlinks.json — served
when the app's mobile/native.json turns links on, which the runner tells the
backend as MOBILE_APP_LINKS), and an ad network asks which publisher may sell
its ad space (app-ads.txt — the publisher is the one inside the app's AdMob
app ids). An app that ships its own file always wins (seo/router.py).

The Android app is signed twice over: the repo's upload key signs what the
build makes (the APK a phone installs from the Mobile builds release), and
Google Play re-signs what it hands out with its own key. Both certificates
open links: the upload key's is a fact (MOBILE_ANDROID_UPLOAD_CERT), Play's is
read from Play with the service account the app already holds for purchases
— the newest version on any track, through Play's own list of the APKs it
generated (Play has no other read of it; measured 2026-10-21)."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import logging
import re
import time

import httpx

from app.config import Settings
from app.core.google_service_account import access_token, load_service_account

logger = logging.getLogger("escapebase44.mobile")

# Paths of the app's own address that are never a page to open in the app:
# the backend's API (a sign-in's return lands there) and its functions.
_NOT_PAGES = ("/api/*", "/functions/*")

# Google's certification-authority id for AdMob/AdSense — the fourth field of
# every Google line in an ads.txt / app-ads.txt (Google's own spec).
_GOOGLE_TAG_ID = "f08c47fec0942fa0"
_ADMOB_APP_ID = re.compile(r"^ca-app-pub-(\d{16})~\d+$")


def default_bundle_id(settings: Settings) -> str:
    return f"com.eb44.app{settings.APP_ID}"


def ios_bundle_id(settings: Settings) -> str:
    return settings.MOBILE_IOS_BUNDLE_ID or settings.MOBILE_BUNDLE_ID or default_bundle_id(settings)


def android_package(settings: Settings) -> str:
    return settings.MOBILE_ANDROID_PACKAGE or settings.MOBILE_BUNDLE_ID or default_bundle_id(settings)


def apple_app_site_association(settings: Settings) -> dict | None:
    """Universal links: this address opens in the iPhone app (every page but
    the backend's own paths). None while links are off or the Apple team is
    not known yet (the App Store card's key step records it)."""
    if not settings.MOBILE_APP_LINKS or not settings.APPLE_TEAM_ID:
        return None
    app_id = f"{settings.APPLE_TEAM_ID}.{ios_bundle_id(settings)}"
    components = [{"/": path, "exclude": True} for path in _NOT_PAGES] + [{"/": "*"}]
    return {
        "applinks": {"details": [{"appIDs": [app_id], "components": components}]},
        # Password AutoFill offers the app's saved logins inside the app too.
        "webcredentials": {"apps": [app_id]},
    }


def _fingerprint(digest: bytes) -> str:
    return ":".join(f"{b:02X}" for b in digest)


def upload_certificate_fingerprint(settings: Settings) -> str | None:
    """The SHA-256 of the repo's Play upload certificate (base64 DER)."""
    raw = (settings.MOBILE_ANDROID_UPLOAD_CERT or "").strip()
    if not raw:
        return None
    try:
        return _fingerprint(hashlib.sha256(base64.b64decode(raw, validate=True)).digest())
    except (binascii.Error, ValueError):
        logger.warning("MOBILE_ANDROID_UPLOAD_CERT is not base64 — left out of assetlinks.json")
        return None


def _hash_as_fingerprint(value: str) -> str | None:
    """Play's certificate hash, as hex (with or without colons) or base64."""
    hexed = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(hexed) == 64 and re.fullmatch(r"[0-9A-Fa-f:\s]+", value):
        return _fingerprint(bytes.fromhex(hexed))
    try:
        digest = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_" if ("-" in value or "_" in value) else None)
    except (binascii.Error, ValueError):
        return None
    return _fingerprint(digest) if len(digest) == 32 else None


_API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
_PLAY_CACHE_SECONDS = 6 * 3600
# package → (fingerprints, read at); kept when a later read fails.
_play_cache: dict[str, tuple[list[str], float]] = {}


async def _read_play_certificates(sa: dict, package: str) -> list[str]:
    headers = {"Authorization": f"Bearer {await access_token(sa, _SCOPE)}"}
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.post(f"{_API}/{package}/edits", headers=headers)
        if r.status_code == 404:
            return []  # not on Google Play (yet)
        r.raise_for_status()
        edit = r.json()["id"]
        try:
            r = await client.get(f"{_API}/{package}/edits/{edit}/tracks", headers=headers)
            r.raise_for_status()
            codes = [int(c) for t in r.json().get("tracks", []) for rel in t.get("releases", []) for c in rel.get("versionCodes", [])]
        finally:
            await client.delete(f"{_API}/{package}/edits/{edit}", headers=headers)
        if not codes:
            return []
        r = await client.get(f"{_API}/{package}/generatedApks/{max(codes)}", headers=headers)
        r.raise_for_status()
        found = [_hash_as_fingerprint(g.get("certificateSha256Hash", "")) for g in r.json().get("generatedApks", [])]
        return sorted({f for f in found if f})


async def play_signing_certificates(settings: Settings) -> list[str]:
    """Google Play's own signing certificate(s) for the Android app, or none
    when there is no service account or the app is not on Play yet."""
    if not settings.IAP_GOOGLE_SA_JSON_B64:
        return []
    package = android_package(settings)
    cached = _play_cache.get(package)
    if cached and time.time() - cached[1] < _PLAY_CACHE_SECONDS:
        return cached[0]
    try:
        sa = load_service_account(settings.IAP_GOOGLE_SA_JSON_B64, "IAP_GOOGLE_SA_JSON_B64")
        fingerprints = await asyncio.wait_for(_read_play_certificates(sa, package), timeout=10)
    except Exception:
        logger.warning("Google Play's signing certificate could not be read for %s", package, exc_info=True)
        return cached[0] if cached else []
    _play_cache[package] = (fingerprints, time.time())
    return fingerprints


async def asset_links(settings: Settings) -> list | None:
    """App links: this address opens in the Android app, for the certificates
    that sign it (the upload key's, and Google Play's own once the app is
    there). None while links are off or no certificate is known."""
    if not settings.MOBILE_APP_LINKS:
        return None
    fingerprints = [f for f in [upload_certificate_fingerprint(settings)] if f]
    for f in await play_signing_certificates(settings):
        if f not in fingerprints:
            fingerprints.append(f)
    if not fingerprints:
        return None
    return [{
        "relation": ["delegate_permission/common.handle_all_urls", "delegate_permission/common.get_login_creds"],
        "target": {"namespace": "android_app", "package_name": android_package(settings), "sha256_cert_fingerprints": fingerprints},
    }]


def app_ads_txt(settings: Settings) -> str | None:
    """The publisher allowed to sell this app's ad space: the one inside its
    AdMob app ids. None for an app with no AdMob app id."""
    publishers: list[str] = []
    for app_id in (settings.ADMOB_APP_ID_IOS, settings.ADMOB_APP_ID_ANDROID):
        m = _ADMOB_APP_ID.match((app_id or "").strip())
        if m and m.group(1) not in publishers:
            publishers.append(m.group(1))
    if not publishers:
        return None
    return "".join(f"google.com, pub-{p}, DIRECT, {_GOOGLE_TAG_ID}\n" for p in publishers)
