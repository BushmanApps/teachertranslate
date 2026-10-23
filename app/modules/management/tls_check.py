"""On-demand TLS authorization for the VPS Caddy reverse proxy.

Caddy serves every hostname via on-demand TLS — it issues a Let's Encrypt
certificate on the first TLS handshake for a host it doesn't already have.
To stop a stranger pointing an arbitrary domain at the box (and burning our
ACME rate limit), Caddy is configured with `on_demand_tls { ask <this> }`:
before issuing, it GETs this endpoint with `?domain=<host>` and only proceeds
on a 2xx.

A host is authorized if it is the app's own canonical host, any
`*.<EB44_BASE_DOMAIN>` host (the app's eb44 address is PERMANENT: it keeps
serving after a custom domain is attached — the mobile wrapper is pinned to
it and old links keep working — and nobody but us can point an eb44.app name
at this box, since we own that zone), or a custom domain the builder attached
after migration (`_app_settings.custom_domains`). That is why attaching a
custom domain is a pure data change — no redeploy, no Caddyfile edit: the
domain lands in the allow-list and the next handshake issues its cert.

Reachable at `GET /_internal/tls-allowed?domain=<host>` (Caddy calls it over
the docker network at `http://backend:8000/...`). The check is fast-pathed on
the canonical host so the common case never touches Mongo; custom domains are
read fresh each call (only the first handshake per host hits this, then Caddy
caches the cert for weeks, so the query is rare).
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request, Response

from app.config import Settings
from app.core import addresses, db


async def tls_allowed(domain: str, request: Request) -> Response:
    host = domain.strip().lower()
    settings: Settings = request.app.state.settings
    canonical = (urlparse(await addresses.canonical_base_url()).hostname or "").lower()
    if host and host == canonical:
        return Response(status_code=200)
    if host.endswith("." + settings.EB44_BASE_DOMAIN.lower()):
        return Response(status_code=200)

    doc = await db.coll("_app_settings").find_one({}, {"custom_domains": 1})
    customs = {str(d).strip().lower() for d in (doc or {}).get("custom_domains") or []}
    if host in customs:
        return Response(status_code=200)

    return Response(status_code=403)
