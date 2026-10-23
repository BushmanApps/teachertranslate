"""Vend a fresh access token from a stored _connector_tokens row.

Refreshes if expired and a refresh_token exists. Concurrent-refresh-safe via
`update_one` filtered on the old refresh_token — only one writer matches.
The loser re-reads to pick up the winner's row.
"""

from __future__ import annotations

from datetime import timedelta

from app.core import db
from app.core.oauth import mint_client_credentials_token, refresh_access_token
from app.core.responses import utcnow_naive

from app.modules.connectors.helpers import (
    _normalize_scopes,
    build_provider_config,
    effective_redirect_uri,
    expires_at_to_naive,
)

REFRESH_MARGIN_SECONDS = 60


async def vend_access_token(token_doc: dict, cfg: dict, base_url: str) -> str:
    if cfg.get("token_grant") == "client_credentials":
        return await _vend_instance_token(token_doc, cfg, base_url)
    expires_at = token_doc.get("expires_at")
    refresh_token = token_doc.get("refresh_token")

    if expires_at is None or not refresh_token:
        return token_doc["access_token"]

    if utcnow_naive() < expires_at - timedelta(seconds=REFRESH_MARGIN_SECONDS):
        return token_doc["access_token"]

    # F-CONN-17: use token_doc.connection_config (persisted at OAuth time)
    # so refresh interpolation honors the original body-supplied overrides.
    provider = build_provider_config(
        cfg,
        effective_redirect_uri(cfg, base_url),
        connection_config=token_doc.get("connection_config"),
    )
    coll = db.coll("_connector_tokens")

    try:
        new_token = await refresh_access_token(provider, refresh_token)
    except Exception:
        # A concurrent refresher may have invalidated our refresh_token at the provider.
        # If the DB row has moved on, return the winner's access_token.
        fresh = await coll.find_one({"_id": token_doc["_id"]})
        if fresh and fresh.get("refresh_token") != refresh_token:
            return fresh["access_token"]
        raise

    update_fields = {
        "access_token": new_token["access_token"],
        "expires_at": expires_at_to_naive(new_token.get("expires_at")),
        "token_type": new_token.get("token_type", "Bearer"),
        "scope_granted": _normalize_scopes(new_token.get("scope")),
        "updated_at": utcnow_naive(),
    }
    if "refresh_token" in new_token:
        update_fields["refresh_token"] = new_token["refresh_token"]

    await coll.update_one(
        {"_id": token_doc["_id"], "refresh_token": refresh_token},
        {"$set": update_fields},
    )
    fresh = await coll.find_one({"_id": token_doc["_id"]})
    return fresh["access_token"] if fresh else new_token["access_token"]


async def _vend_instance_token(token_doc: dict, cfg: dict, base_url: str) -> str:
    """An installed-instance grant (Wix) has no refresh token: past expiry the
    token is simply minted again from client id + secret + the instance id
    the callback stored on the row. Last writer wins — every mint is valid."""
    expires_at = token_doc.get("expires_at")
    if expires_at is not None and utcnow_naive() < expires_at - timedelta(seconds=REFRESH_MARGIN_SECONDS):
        return token_doc["access_token"]
    connection_config = token_doc.get("connection_config") or {}
    provider = build_provider_config(
        cfg,
        effective_redirect_uri(cfg, base_url),
        connection_config=connection_config,
    )
    new_token = await mint_client_credentials_token(provider, instance_id=connection_config["instance_id"])
    await db.coll("_connector_tokens").update_one(
        {"_id": token_doc["_id"]},
        {"$set": {
            "access_token": new_token["access_token"],
            "expires_at": expires_at_to_naive(new_token.get("expires_at")),
            "token_type": new_token.get("token_type", "Bearer"),
            "updated_at": utcnow_naive(),
        }},
    )
    return new_token["access_token"]
