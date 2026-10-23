"""Shared helpers for the auth module."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone, timedelta

import bcrypt
from bson import ObjectId

from app.core import db
from app.core.responses import utcnow


OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
RESET_TOKEN_LENGTH = 32


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def generate_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)


def generate_reset_token() -> str:
    return secrets.token_hex(16)


def derive_full_name(email: str) -> str:
    match = re.match(r"^([^@]+)", email)
    return match.group(1) if match else email


def otp_expiry_time() -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
    return exp.strftime("%Y-%m-%dT%H:%M:%S.%f")


async def find_user_by_email(email: str, app_id: str) -> dict | None:
    return await db.coll("User").find_one({"email": email, "app_id": app_id})


async def find_private_user(query: dict) -> dict | None:
    return await db.coll("_private_users").find_one(query)


async def get_auth_config() -> dict:
    settings_doc = await db.app_settings()
    return settings_doc.get("auth_config") or {}


async def get_app_visibility_mode() -> str:
    settings_doc = await db.app_settings()
    return settings_doc.get("public_settings", "public_without_login")


async def is_user_invited(email: str, app_id: str) -> bool:
    # `invited_users` is the one _app_settings field a runtime request mutates
    # (invite_user), so read it fresh — projected to just that field so this
    # stays cheap and never pulls the whole document.
    settings_doc = await db.coll("_app_settings").find_one({}, {"invited_users": 1}) or {}
    invited_users = settings_doc.get("invited_users") or []
    return email.lower() in [u.lower() for u in invited_users if isinstance(u, str)]


# Doc keys present on User Mongo rows but NOT echoed on Base44's normalized
# User response. `environment` is the only one we still need to strip here:
# the migrator + entity-create path stamp it (`Optional[str]` filterable via
# `?q={"environment": null}`), and generic entity serialization excludes it
# via `model_dump(exclude={"environment"})`. The User-specific path uses
# `UserResource` directly, so we strip it here.
_USER_SERVER_INTERNAL_FIELDS = frozenset({"environment"})

# Canonical User field order at fresh-register (Base44 stamps in this order on
# register; probed 2026-05-22 against AuthRolesLab — matches +pmc storage from
# session-4 +M-002 fix). Used to detect which canonicals are still in their
# "untouched post-id" position vs which have been moved into the "pre-id
# extras zone" via Base44's PUT mechanism.
#
# Empirical mechanism (M-009, deeply probed 2026-05-22 against +a1):
# - On PUT body key K that's NOT in ANCHORED, K is removed from current storage
#   position and re-inserted at the end of the pre-id extras zone (right before
#   `id`). New orphans also land at end of pre-id, in body order.
# - On PUT body key K in ANCHORED, K's value updates (if mutable) but position
#   doesn't change.
# - `id`'s position is dynamic: it sits at the boundary between the pre-id
#   extras zone and the un-touched canonical suffix. Whenever a movable
#   canonical is touched, it crosses the boundary, pushing `id` further down.
#
# `id` in the wire is therefore at the position right BEFORE the longest
# contiguous suffix of canonical fields that are still in their original
# Base44-register order. The algorithm: walk storage keys from end backwards;
# while the next key is a canonical with index strictly less than the
# previously-seen canonical's index, keep going. Stop at the first violation —
# that's where `id` is emitted.
_USER_CANONICAL_ORDER: tuple[str, ...] = (
    "created_date", "updated_date", "email", "full_name",
    "disabled", "disabled_reason", "is_verified", "force_password_reset",
    "app_id", "is_service", "collaborator_role", "_app_role",
)
_USER_CANONICAL_INDEX = {k: i for i, k in enumerate(_USER_CANONICAL_ORDER)}


def _user_id_boundary(keys: list[str]) -> int:
    """Compute the index in `keys` where `id` should be inserted in the wire.

    `keys` is the list of user_doc storage keys with `_id` and `environment`
    already filtered out. Returns an integer N such that emitting `id` between
    keys[N-1] and keys[N] produces Base44's exact wire field order.

    The boundary is the start of the longest contiguous suffix of `keys` that
    consists of canonical fields appearing in `_USER_CANONICAL_ORDER` order
    (i.e., each canonical's order-index strictly less than the next's). Any
    non-canonical key (orphan, custom, `_id` extra) breaks the suffix. Any
    canonical out of order breaks the suffix — those are touched canonicals
    that Base44 moved to the pre-id zone.
    """
    boundary = len(keys)
    next_canonical_idx = len(_USER_CANONICAL_ORDER)
    for i in range(len(keys) - 1, -1, -1):
        key = keys[i]
        idx = _USER_CANONICAL_INDEX.get(key)
        if idx is None or idx >= next_canonical_idx:
            break
        next_canonical_idx = idx
        boundary = i
    return boundary


def user_doc_to_userresource_input(user_doc: dict) -> dict:
    """Map a Mongo `User` document to the dict shape `UserResource` expects.

    Output dict insertion order matches Base44's wire structure (probed
    2026-05-22 against AuthRolesLab Daniel-side via 14+ paired probes):

        role, [pre-id zone: orphans/customs + touched canonicals in storage
        order], id, [post-id zone: untouched canonical suffix in storage order]

    For a fresh-registered user with no customs/no orphans/no PUTs, the wire
    collapses to `role, id, created_date, updated_date, email, full_name,
    disabled, disabled_reason, is_verified, force_password_reset, app_id,
    is_service, collaborator_role, _app_role`.

    Implementation: iterate `user_doc` in storage order. Skip `_id` and
    `environment`. Emit `role` first. Compute the id-boundary via
    `_user_id_boundary` and inject `id` at that position. The `id` value
    comes from a stored `id` field if present (Base44 stores `id` as a doc
    field; the migrator preserves it). Falls back to `str(_id)` for docs
    that don't have a stored `id` (legacy docs from before
    `transformUserRecord` kept `id`).

    `UserResource` declares only `role` + per-app custom-schema fields;
    everything else flows via `extra="allow"`. The `**` insertion order
    seeds Pydantic's `__pydantic_extra__` in our exact order, which
    `model_dump(mode="json")` emits verbatim after declared fields.

    Sensitive fields from `_private_users` (hashed_password, api_key,
    otp_code, etc.) are intentionally NOT touched here — they live in
    a separate collection.
    """
    keys = [k for k in user_doc.keys() if k not in ("_id", "environment")]
    if "role" in keys:
        keys.remove("role")
    boundary = _user_id_boundary(keys)

    stored_id = user_doc.get("id")
    id_value = stored_id if isinstance(stored_id, str) else str(user_doc.get("_id", ""))

    out: dict = {"role": user_doc.get("role", "user")}
    for i, key in enumerate(keys):
        if key == "id":
            continue  # emitted at boundary, not at storage position
        if i == boundary:
            out["id"] = id_value
        out[key] = user_doc[key]
    if "id" not in out:
        out["id"] = id_value

    return out


def build_new_user_doc(email: str, full_name: str, app_id: str) -> dict:
    """Build a fresh User doc for the register-flow path.

    Base44 does NOT stamp `created_by`/`created_by_id`/`is_sample` on User
    docs (probed 2026-05-20; coordinated with entities agent E-015). User is
    special among entities — `created_by` would be tautological with `email`,
    `created_by_id` with `id`, and `is_sample` is meaningless for a real
    registered user. Same-decisions: don't stamp them. With nothing on the
    doc, `UserResource(extra=allow)` echoes nothing extra on the wire.

    `disabled_reason: None` IS stamped — Base44's normalized response
    always emits `"disabled_reason": null`, and without initializing it
    here, `model_dump(exclude_unset=True)` drops the field on register-flow
    users.

    Storage order matches Base44 — verified 2026-05-21 session 4 by
    inspecting +a1 (migrator-imported; preserves Base44's insertion order
    via transformUserRecord) directly in Atlas:
        _id, role, id, [orphans/customs would land here on later PUTs],
        created_date, updated_date, email, full_name, disabled,
        disabled_reason, is_verified, force_password_reset, app_id,
        is_service, collaborator_role, _app_role [, environment]

    `id` is stamped as a Mongo doc field at position 3 (right after `role`,
    right before `created_date`) — Base44 stores it as a regular field at
    this initial position, then on later PUTs new orphans / touched
    canonicals get inserted right before `id`, pushing `id`'s absolute
    position further down (probed 2026-05-22, M-009 mechanism). The
    serializer `user_doc_to_userresource_input` honors the stored `id`,
    falling back to `str(_id)` only for legacy docs that don't have it.
    Without this stamping, every fresh-registered user's wire put `id`
    immediately after `role`, diverging from Base44's `id`-at-boundary
    position once any extras existed.
    """
    user_id = ObjectId()
    return {
        "_id": user_id,
        "role": "user",
        "id": str(user_id),
        "created_date": utcnow(),
        "updated_date": utcnow(),
        "email": email,
        "full_name": full_name,
        "disabled": None,
        "disabled_reason": None,
        "is_verified": False,
        "force_password_reset": False,
        "app_id": app_id,
        "is_service": False,
        "collaborator_role": None,
        "_app_role": "user",
    }


def build_private_user_doc(
    email: str, app_id: str, user_id: str, hashed_password: str | None = None,
) -> dict:
    return {
        "email": email,
        "app_id": app_id,
        "user_id": user_id,
        "hashed_password": hashed_password,
        "hashed_reset_token": None,
        "otp_code": None,
        "otp_expires_at": None,
        "otp_attempts": 0,
        "api_key": secrets.token_hex(16),
        "phone_number": None,
        "granted_by_support_access": False,
        "support_access_expires_at": None,
        "registered_by_platform_access": False,
    }


def get_country_code_from_request(request) -> str:
    """Resolve the caller's country from edge-proxy IP-geolocation headers.

    Base44 uses Cloudflare (`CF-IPCountry`). Same-decisions on our stack
    means honoring whichever IP-country header the deployed edge proxy
    sets:

    - `CF-IPCountry` — Cloudflare (Base44, plus any of our deploys behind
      a Cloudflare custom domain).
    - `x-vercel-ip-country` — Vercel's equivalent (`@vercel/python`
      forwards this to the function on every request). Probed 2026-05-22:
      Vercel deploys were returning `country_code:"US"` while Base44
      returned `IL` for the same Israel-located client, because we never
      read Vercel's header.
    - `X-Country-Code`, `X-Real-Country` — generic fallbacks (e.g. when
      operators put a custom proxy in front).

    `XX` is Cloudflare's sentinel for "unknown / Tor" and is treated as
    absent (matches B44 wire — Tor/unresolved clients fall through).
    """
    for header in (
        "CF-IPCountry",
        "x-vercel-ip-country",
        "X-Country-Code",
        "X-Real-Country",
    ):
        val = request.headers.get(header)
        if val and val != "XX":
            return val.upper()
    return "US"
