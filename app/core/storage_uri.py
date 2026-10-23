"""Resolve a Base44-shaped storage URI to a fetchable absolute URL.

Base44 production's LLM-receiving paths (`InvokeLLM.file_urls`,
`ExtractDataFromUploadedFile` for image/PDF/HTML) accept the same URI
shapes that come back from `UploadFile` / `UploadPrivateFile` and out of
entity records — `mp/private/{appId}/{file}`, `private/{key}`, etc. —
and resolve them internally before constructing the LLM provider message
(probe-locked own-probes 2026-05-21). Their DuckDB CSV path is the one
exception: it passes the URI verbatim to `read_csv_auto`, which then
IO-fails for relative paths.

We mirror the same decision: this helper turns storage URIs into
absolute URLs; the integration handlers call it in the LLM-facing paths
but not the CSV path.
"""

from __future__ import annotations

from app.core.errors import AppHTTPException


_PRIVATE_PREFIXES = ("mp/private/", "private/")
_PUBLIC_PREFIXES = ("mp/public/", "public/")


async def resolve_storage_uri(uri: str, storage, ttl: int = 300) -> str:
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    if any(uri.startswith(p) for p in _PRIVATE_PREFIXES):
        if storage is None:
            raise AppHTTPException(500, "Storage provider not configured")
        return await storage.sign(uri, ttl=ttl)
    if any(uri.startswith(p) for p in _PUBLIC_PREFIXES):
        if storage is None:
            raise AppHTTPException(500, "Storage provider not configured")
        return storage.public_url_for(uri)
    return uri



def own_key(reference: str, app_id: str) -> str | None:
    """The storage key a bare reference names when it is a file of THIS app,
    else None. Two shapes live on an app's storage: Base44's own,
    `mp/{public|private}/{app}/{file}` (what the migration copied, key
    preserved — Base44 reads it with or without the `mp/`), and the one the
    uploads of this backend mint, `{public|private}/{file}` — one segment.
    A key whose owner segment is anything but this app is not this app's
    (Base44 refuses `private/other-app/x.png` the same way)."""
    bare = reference.removeprefix("mp/")
    visibility, _, rest = bare.partition("/")
    if visibility not in ("public", "private") or not rest:
        return None
    owner, _, file = rest.partition("/")
    if file:
        return f"mp/{bare}" if owner == app_id else None
    return bare if bare == reference else None


def own_url(reference: str, app_id: str, storage) -> tuple[str, bool] | None:
    """Where a file of THIS app is read from — (what to resolve, whether it
    is private) — or None when the reference is not a file this app stores:
    a bare key of another app, a URL anywhere but the app's own storage."""
    if reference.startswith(("http://", "https://")):
        return (reference, False) if reference.startswith(storage.public_url_for("")) else None
    key = own_key(reference, app_id)
    return None if key is None else (key, key.removeprefix("mp/").startswith("private/"))
