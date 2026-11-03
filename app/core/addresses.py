"""Where the app's addresses come from.

The app does not carry its own URL as configuration. It has TWO kinds of
address, matching Base44's own behavior (measured on a live custom domain,
2026-08-31 — the single-home architecture handoff §12.1):

- **The arrival address** — the scheme+host the current request came in on.
  Everything produced while answering a visitor derives from it: the login
  redirect's return target, the ``Base44-Api-Url`` header handed to backend
  functions, the manifest/SEO base, links in emails sent during the visit.
  Base44 derives all of these from the arrival host; a user always comes
  back to the address they were on.

- **The canonical address** — the app's stored primary URL, used where no
  request exists (boot-time webhook registration, scheduled work) and for
  externally-REGISTERED URLs that must stay byte-stable across visits
  (OAuth redirect URIs registered at a provider). Its one home is the
  app's own settings document (``_app_settings.eb44_canonical_url``,
  seeded at migration, updated by the custom-domain flow). The ``BASE_URL``
  env var remains readable as the legacy source — deployments generated
  before the single-home architecture supply it and carry no settings
  field.

A host is only honored as an arrival address when the app recognizes it:
its canonical host, any ``*.<EB44_BASE_DOMAIN>`` host (the permanent
address zone we own), an attached custom domain, a loopback host (local
dev), or the host of the configured ``BASE_URL``. Anything else — a forged
Host header, a stray CDN probe — resolves to the canonical address, so
header spoofing can never plant a foreign host in a login redirect or an
email.

``BASE_URL`` is where the dev stack declares its browser-facing address:
vite fronts this backend and forwards the browser's host (``xfwd`` in
``vite.config.dev.ts``), but only sees its own plain-http leg — and the
builder's preview sits behind an edge that forwards nothing but the public
host. So a request whose forwarded host is ``BASE_URL``'s arrived at
``BASE_URL`` exactly, scheme included (``http://localhost:5173`` on a
laptop, ``https://5173-<sandbox>.e2b.app`` in the builder). In production
``BASE_URL`` is the app's own address and adds nothing.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request

from app.core import db

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def _bare_host(host: str) -> str:
    """The hostname without a port ("app.example.com:8443" → "app.example.com")."""
    if host.startswith("["):  # bracketed IPv6, maybe with port
        return host.split("]")[0] + "]"
    return host.split(":")[0]


async def canonical_base_url() -> str:
    """The app's stored primary URL, no trailing slash."""
    app_settings = await db.app_settings()
    stored = app_settings.get("eb44_canonical_url")
    if isinstance(stored, str) and stored.strip():
        return stored.strip().rstrip("/")
    from app.deps import get_settings

    legacy = get_settings().BASE_URL
    if legacy:
        return legacy.rstrip("/")
    raise RuntimeError(
        "No canonical address: _app_settings.eb44_canonical_url is unset and no BASE_URL env was supplied"
    )


def header_value(headers, name: str) -> str | None:
    """Case-insensitive header lookup that works on Starlette Headers AND on
    the plain dicts the function proxy / agent loop carry around."""
    getter = getattr(headers, "get", None)
    value = getter(name) if getter else None
    if value is not None:
        return value
    lower = name.lower()
    for key in headers:
        if str(key).lower() == lower:
            return headers[key]
    return None


async def arrival_base_url_from_headers(headers) -> str:
    """The scheme+host the carried request arrived on, validated; canonical
    otherwise (which is also what a header set with no Host at all — a
    synthetic offline caller — resolves to)."""
    from app.deps import get_settings

    settings = get_settings()
    canonical = await canonical_base_url()
    canonical_host = urlparse(canonical).netloc.lower()
    eb44_suffix = "." + settings.EB44_BASE_DOMAIN.lower()
    configured = (settings.BASE_URL or "").strip().rstrip("/")
    configured_host = urlparse(configured).netloc.lower() if configured else ""
    app_settings = await db.app_settings()
    custom_domains = {
        str(d).strip().lower() for d in app_settings.get("custom_domains") or [] if str(d).strip()
    }

    for candidate in (header_value(headers, "x-forwarded-host"), header_value(headers, "host")):
        if not candidate:
            continue
        # Proxies may append hops comma-separated; the first is the client-facing one.
        host = candidate.split(",")[0].strip().lower()
        if not host:
            continue
        bare = _bare_host(host)
        if configured_host and host == configured_host:
            return configured
        if (
            host == canonical_host
            or bare == _bare_host(canonical_host)
            or bare.endswith(eb44_suffix)
            or bare in custom_domains
            or bare in _LOCAL_HOSTS
        ):
            proto_header = header_value(headers, "x-forwarded-proto")
            proto = proto_header.split(",")[0].strip().lower() if proto_header else ""
            if proto not in ("http", "https"):
                proto = "http" if bare in _LOCAL_HOSTS else "https"
            return f"{proto}://{host}"

    return canonical


async def arrived_at_dev_stack(headers) -> bool:
    """True when the carried request came in on the dev stack's own address:
    a loopback host, or the configured ``BASE_URL`` where that is none of the
    app's published addresses (the builder's preview host). The published app
    — the canonical address, the ``*.<EB44_BASE_DOMAIN>`` zone, a custom
    domain — and any host the app does not recognize answer False."""
    from app.deps import get_settings

    settings = get_settings()
    app_settings = await db.app_settings()
    published = {
        str(d).strip().lower() for d in app_settings.get("custom_domains") or [] if str(d).strip()
    }
    stored = app_settings.get("eb44_canonical_url")
    if isinstance(stored, str) and stored.strip():
        published.add(_bare_host(urlparse(stored.strip()).netloc.lower()))
    eb44_suffix = "." + settings.EB44_BASE_DOMAIN.lower()
    configured = _bare_host(urlparse((settings.BASE_URL or "").strip()).netloc.lower())

    for candidate in (header_value(headers, "x-forwarded-host"), header_value(headers, "host")):
        host = (candidate or "").split(",")[0].strip().lower()
        if not host:
            continue
        bare = _bare_host(host)
        if bare in published or bare.endswith(eb44_suffix):
            return False
        return bare in _LOCAL_HOSTS or (bool(configured) and bare == configured)
    return False


async def arrival_base_url(request: Request) -> str:
    """The scheme+host this request arrived on, validated; canonical otherwise."""
    return await arrival_base_url_from_headers(request.headers)
