"""Connector helpers — config lookup, URL/scope interpolation, ProviderConfig builder."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.core import db
from app.core.oauth import ProviderConfig
from app.core.responses import utcnow_naive


def parse_object_id(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


async def find_app_config(integration_type: str) -> dict | None:
    return await db.coll("_connector_configs").find_one(
        {"type": integration_type, "scope": "app"}
    )


async def find_user_config(connector_oid: ObjectId) -> dict | None:
    return await db.coll("_connector_configs").find_one(
        {"_id": connector_oid, "scope": "user"}
    )


def _interpolate(value: str, ctx: dict) -> str:
    out = value.format(**ctx)
    assert "{" not in out and "}" not in out, (
        f"unresolved placeholder after interpolation: {out!r}"
    )
    return out


def template_placeholders(templates: list[str]) -> set[str]:
    """The `{name}`s a list of URL templates references."""
    import re
    return {m for t in templates for m in re.findall(r"\{([^{}]+)\}", t)}


def resolve_token_url(candidates: list[str], ctx: dict) -> str | None:
    """The token endpoint for this dance: the FIRST alternative whose
    placeholders all resolve from `ctx`, else None.

    The alternatives are the provider catalog's, in its order, seeded by the
    migrator (salesforce: the connection's own host first, the login host
    second; zoho: the regional host named by a config the app never
    collects first, then `{accounts-server}` — the region the provider
    itself names on its callback). At /connect time a callback-only
    placeholder is still unbound and None is correct: nothing needs the
    token endpoint before the callback arrives."""
    for template in candidates:
        try:
            return _interpolate(template, ctx)
        except (KeyError, IndexError):
            continue
    return None


def build_provider_config(
    cfg: dict,
    redirect_uri: str,
    connection_config: dict | None = None,
    scopes: list[str] | None = None,
    callback_params: dict | None = None,
) -> ProviderConfig:
    """Apply {placeholder} interpolation to URLs/scopes and assemble a ProviderConfig.

    Context merges client_id (for wix's `{client_id}` in auth_url) with the
    effective `connection_config` (for bamboohr's `{subdomain}`, sharepoint's
    scope `{subdomain}`) and, at the callback, the provider's own callback
    parameters (Zoho names the user's regional accounts server there —
    `accounts-server` — and its token exchange must go to it). For most
    connectors no placeholders exist and .format is a no-op.

    `connection_config` (optional kwarg) overrides cfg's stored
    connection_config — used by /connect and /callback to honor the
    per-pending-row connection_config supplied at /initiate time (F-CONN-17).
    When omitted, falls back to cfg.connection_config (the migrator-seeded
    default).

    `scopes` (optional kwarg) overrides cfg's stored scopes the same way —
    Base44 honors body-supplied scopes on /initiate as a REPLACEMENT for the
    default set (their CLI docs + the 2026-08-28 dance probes), carried on
    the pending row per-dance.

    The token endpoint is resolved from `cfg["token_urls"]` (see
    resolve_token_url) and may be None until the callback supplies what a
    template needs; the exchange refuses loudly if it is still None then.
    """
    effective_conn_config = connection_config if connection_config is not None else (cfg.get("connection_config") or {})
    ctx = {"client_id": cfg["client_id"], **effective_conn_config, **(callback_params or {})}
    auth_url = _interpolate(cfg["auth_url"], ctx)
    token_url = resolve_token_url(list(cfg["token_urls"]), ctx)
    effective_scopes = scopes if scopes else cfg["scopes"]
    scopes = _with_ensured_scopes([_interpolate(s, ctx) for s in effective_scopes], cfg["ensure_scopes"])

    # The per-type authorize shape and the token endpoint are DATA the
    # migrator derived for this app (Base44's own dance for the type + the
    # open provider catalog, 2026-09-07). No provider is special-cased here
    # or in the OAuth helper: tiktok's `client_key`, slack's `user_scope`,
    # meta's comma-joined scopes, google's offline+prompt extras, wix's
    # installer and zoho's regional token host all arrive as fields.
    return ProviderConfig(
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        redirect_uri=redirect_uri,
        scope=scopes,
        authorization_endpoint=auth_url,
        token_endpoint=token_url,
        client_id_param=cfg["client_id_param"],
        redirect_uri_param=cfg["redirect_uri_param"],
        scope_param=cfg["scope_param"],
        scope_separator=cfg["scope_separator"],
        authorize_standard_params=bool(cfg["authorize_standard_params"]),
        # Static extras may name a connection-config field (Wix's share-link id).
        authorize_params={k: _interpolate(v, ctx) for k, v in dict(cfg["authorize_params"]).items()},
        token_params=dict(cfg.get("token_params") or {}),
        token_path=cfg.get("token_path"),
        token_request_auth_method=cfg.get("token_request_auth_method"),
        # The refresh endpoint resolves from its own alternatives the way the
        # token endpoint does (the same placeholders, the same callback params).
        refresh_endpoint=resolve_token_url(list(cfg.get("refresh_urls") or []), ctx),
        refresh_params=dict(cfg.get("refresh_params") or {}),
        token_grant=cfg.get("token_grant") or "authorization_code",
        token_request_format=cfg.get("token_request_format") or "form",
        callback_instance_param=cfg.get("callback_instance_param"),
        callback_signature_param=cfg.get("callback_signature_param"),
    )


def callback_bound_config(cfg: dict, connection_config: dict | None, query: dict) -> dict | None:
    """The connection_config a token row keeps after the callback: the
    dance's config plus whichever callback parameters a token-URL template
    references (Zoho's `accounts-server`), so refresh resolves the same
    endpoint the exchange did. Nothing else from the callback is kept."""
    needed = template_placeholders([*cfg["token_urls"], *(cfg.get("refresh_urls") or [])])
    merged = {**(connection_config or {}), **{k: v for k, v in query.items() if k in needed}}
    return merged or None


def _with_ensured_scopes(scopes: list[str], ensure: list[str]) -> list[str]:
    """Scopes the provider config always carries, appended when absent — the
    google family's `email` (Base44 appends it to whatever the app requests;
    measured 2026-08-28 and on every google dance of the 2026-09-02 leak). A
    scope already present under its long userinfo spelling counts as present."""
    out = list(scopes)
    for s in ensure:
        if not any(x == s or x.endswith(f"userinfo.{s}") for x in out):
            out.append(s)
    return out


def missing_required_auth_field(cfg: dict, body_connection_config: dict | None) -> str | None:
    """Wave-3 finding F-CONN-17: Base44 validates per-connection required
    initiation fields at /external-auth/initiate, returning 400 with the
    friendly displayName when missing. Mirror that behavior.

    Returns the displayName of the first missing required field, or None if
    all required fields are satisfied. Resolution order for each field name:
    1. body's connection_config (the body-supplied per-call override)
    2. cfg.connection_config (the migrator-seeded default)

    If neither has the field, that's a 400. Composio's metadata for each
    toolkit (auth_config_details[0].fields.connected_account_initiation.required)
    is the source of truth — the migrator captures it into cfg.auth_fields.

    Note: cfg.auth_fields may be missing for connectors seeded by an older
    migrator version. In that case skip validation (graceful degradation —
    we'll still 500 later at /connect if a placeholder is unresolved, which
    is at least a real error rather than silently building a broken row)."""
    auth_fields = cfg.get("auth_fields")
    if not isinstance(auth_fields, list) or not auth_fields:
        return None
    provided: dict = {
        **(cfg.get("connection_config") or {}),
        **(body_connection_config or {}),
    }
    for f in auth_fields:
        if f.get("required") and f["name"] not in provided:
            return f.get("display_name") or f["name"]
    return None


def merged_connection_config(cfg: dict, body_connection_config: dict | None) -> dict | None:
    """Build the connection_config that will be carried on the pending row.
    Body overrides cfg defaults; result is None when nothing is set."""
    merged = {
        **(cfg.get("connection_config") or {}),
        **(body_connection_config or {}),
    }
    return merged if merged else None


def callback_redirect_uri(base_url: str) -> str:
    # Path matches Base44 production (wave-2 finding F-CONN-03, still true
    # 2026-08-28) — the OAuth provider must allow this exact path as a
    # redirect_uri. Base44's own dances use
    # `https://app.base44.com/api/external-auth/callback` (in-house engine;
    # their May-era Composio brokering survives only as a legacy-state
    # forward on that callback); we use the equivalent on our deployment's
    # BASE_URL.
    return f"{base_url}/api/external-auth/callback"


def effective_redirect_uri(cfg: dict, base_url: str) -> str:
    """The redirect_uri this config's OAuth dance uses.

    Shared-client configs (seeded with EB44's Google client) carry
    `callback_url` — the central forwarder URL registered on that client,
    which relays back to this deployment via the state's origin suffix (see
    make_pending_row). Bring-your-own-client configs use this deployment's
    own callback, registered on the builder's client directly. Same central-
    callback mechanism Base44 itself runs (app.base44.com → Composio)."""
    return cfg.get("callback_url") or callback_redirect_uri(base_url)


def expires_at_to_naive(value) -> datetime | None:
    """Authlib returns expires_at as epoch seconds; Mongo stores as naive UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)




def _gen_state_token(cfg: dict, base_url: str | None) -> str:
    """OAuth state token — 32 lowercase hex chars. 128 bits of entropy.

    2026-08-28 note: Base44's connect/{token} URL still carries a bare
    32-hex token, but the OAuth `state` they send to providers is now a
    signed JWT (`base44:eyJ…` carrying the connection id). Ours stays the
    pending-row token — state is opaque to providers per the OAuth spec, and
    nothing parses ours except us and the forwarder. Conscious cosmetic
    divergence; do not "fix" it toward their JWT shape.

    Shared-client configs get `.{base64url(base_url)}` appended: the token
    doubles as the OAuth `state`, and the central forwarder needs to know
    which deployment to relay the provider's callback to."""
    token = uuid.uuid4().hex
    if cfg.get("callback_url") and base_url:
        import base64
        suffix = base64.urlsafe_b64encode(base_url.encode()).decode().rstrip("=")
        token = f"{token}.{suffix}"
    return token


def _gen_connection_id() -> str:
    """Connection id — `base44_<24-hex ObjectId>` (Base44 wire, measured
    2026-08-28: `base44_6a9149bd…` on every initiate). May's `ca_<12>` shape
    (F-CONN-05) is dead — Composio's "connector account" ids went with the
    Composio brokering."""
    return f"base44_{ObjectId()}"


def _gen_code_verifier() -> str:
    """PKCE code_verifier — RFC 7636 (43–128 URL-safe chars; token_urlsafe(48)
    yields 64). Minted per dance for the types Base44 itself sends PKCE to
    (`cfg.pkce` — 50 of 82 on the 2026-09-02 leak; none to notion, linkedin,
    wix, meta_ads, …), stored on the pending row, spent at the callback's
    code exchange. Newly-created HubSpot apps and public-client providers
    (linear, posthog) hard-require it."""
    return secrets.token_urlsafe(48)


def make_pending_row(
    cfg: dict,
    scope: str,
    user_id: str | None,
    connection_config: dict | None = None,
    authorized_by_email: str | None = None,
    base_url: str | None = None,
    scopes: list[str] | None = None,
) -> dict:
    """Create a `_connector_pending` row.

    `connection_config` (kwarg) carries the body-supplied or stored-default
    connection_config for this specific OAuth dance (F-CONN-17). When the
    OAuth flow lands at /connect, the row's connection_config is read out
    and used for {placeholder} interpolation. Stored independently from
    cfg.connection_config so concurrent dances with different inputs
    can coexist.

    `scopes` (kwarg) carries body-supplied scopes for this dance — Base44
    semantics: they REPLACE the stored default set (2026-08-28). None means
    the dance uses cfg.scopes.

    `authorized_by_email` is the email of the user authorizing this
    connection (the Tier A / Tier C caller at /initiate). Base44's
    `/external-auth/list.user_email` is this value — captured at authorize
    time and stored on the resulting token row — not anything from the OAuth
    provider (F-CONN-29).

    `base_url` is this deployment's own address — needed only for shared-client
    configs, where the state token carries the deployment's origin for the
    central forwarder (see _gen_state_token)."""
    return {
        "token": _gen_state_token(cfg, base_url),
        "connection_id": _gen_connection_id(),
        "type": cfg["type"],
        "scope": scope,
        "connector_id": cfg["_id"] if scope == "user" else None,
        "user_id": user_id,
        "config_id": cfg["_id"],
        "connection_config": connection_config,
        "scopes": scopes,
        "code_verifier": _gen_code_verifier() if cfg["pkce"] else None,
        "authorized_by_email": authorized_by_email,
        "status": "PENDING",
        "error": None,
        "error_message": None,
        "created_at": utcnow_naive(),
    }


# initiate_started / initiate_already_authorized removed in Phase 6 —
# callers now construct InitiateResponse(...).model_dump() directly.


def token_filter_app(integration_type: str) -> dict:
    return {"type": integration_type, "scope": "app"}


def token_filter_user(connector_oid: ObjectId, user_id: str) -> dict:
    return {"connector_id": connector_oid, "user_id": user_id, "scope": "user"}


def _normalize_scopes(value) -> list[str]:
    """Provider scope responses come in three flavors:
    - already a list (most providers' authlib-parsed token dicts)
    - space-separated string (Google, OAuth2 spec default)
    - comma-separated string (GitHub — wave-3 finding F-CONN-21)

    Normalize to list. Used for the internal `_connector_tokens.scope_granted`
    field; the public-facing `/external-auth/list` shape is fed from
    `cfg.scopes` (the migrator-seeded list of requested scopes per F-CONN-13),
    so this normalization is for audit/debugging consistency."""
    import re
    if value is None:
        return []
    if isinstance(value, list):
        return [str(s) for s in value]
    if isinstance(value, str):
        return [s.strip() for s in re.split(r"[,\s]+", value) if s.strip()]
    return []


def build_token_doc(
    cfg: dict,
    scope: str,
    user_id: str | None,
    token: dict,
    user_email: str | None = None,
    integration_account_identifier: str | None = None,
    connection_config: dict | None = None,
) -> dict:
    """Build a `_connector_tokens` row from a freshly-issued OAuth token.

    `user_email` is the authorizing user's email (from the pending row).
    `integration_account_identifier` is the OIDC id_token email or `None`
    for non-OIDC providers — stored as `None` (not `""`) so
    `/external-auth/list` emits `null`, matching Base44 prod (F-CONN-29).

    `connection_config` carries the merged (cfg-default + body-supplied)
    config that was active at OAuth time (F-CONN-17). Persisted on the
    token row so refresh.py can interpolate placeholders (e.g. bamboohr's
    {subdomain} in token_url) without re-reading the pending row."""
    now = utcnow_naive()
    return {
        "type": cfg["type"],
        "scope": scope,
        "connector_id": cfg["_id"] if scope == "user" else None,
        "user_id": user_id,
        "user_email": user_email or "",
        # None (not "") for non-OIDC providers → /external-auth/list emits null.
        "integration_account_identifier": integration_account_identifier,
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "expires_at": expires_at_to_naive(token.get("expires_at")),
        "token_type": token.get("token_type", "Bearer"),
        "scope_granted": _normalize_scopes(token.get("scope")),
        "connection_config": connection_config,
        "created_at": now,
        "updated_at": now,
    }
