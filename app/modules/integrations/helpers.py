"""Integrations Core/* validation helper.

`validate_body` is the centralized envelope-#3 emitter for all integration
endpoints. Per D-005 + findings L2222-2240, integration handlers manually
validate the body via `Model(**body)`, catch `ValidationError`, and raise
`AppHTTPException(422, message=str(detail_dict), detail=detail_dict)` where
`detail` is a Python **dict** (not string). FastAPI's `AppHTTPException`
handler preserves dict-detail as-is, producing the wire envelope #3 shape:
`{error_type: "HTTPException", message: "<dict-as-str>", detail: {...},
traceback: "", request_id: null}`.

The pre-Pydantic `ModelAlias` / `VALID_MODEL_ENUM` lived here until Phase 4.
Replaced by `InvokeLLMRequest.validate_model` in `app/core/models/integrations.py`
— `@field_validator` raising `ValueError` produces wire `value_error` type,
whereas `Literal[...]` produces `literal_error` (probe-locked diff, own-probes §7).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from app.core.errors import AppHTTPException, core_validation


def validate_body(model_class, body: dict):
    try:
        return model_class(**body)
    except ValidationError as e:
        message, detail = core_validation(e.errors())
        raise AppHTTPException(422, message=message, detail=detail)


# ── The file-URL helpers ExtractDataFromUploadedFile and TranscribeAudio share ──
# (hoisted out of extract_data.py on 2026-09-17 when the second caller arrived).

def file_extension(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    filename = path.split("/")[-1] if "/" in path else path
    if "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    return ""


_PRIVATE_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


def is_well_formed_http_url(url: str) -> bool:
    """Base44 validates URL shape + host upfront — non-http(s), missing host,
    leading whitespace, empty string, private/loopback IPs (SSRF defense), etc.
    all get a generic 400 "Invalid file attachment". Storage URIs
    (mp/private/..., private/..., mp/public/..., public/...) pass — they get
    resolved to absolute URLs later. (probe-locked own-probes 2026-05-21 X1/X2/
    X5/X12/Y7-Y14/Z9-Z13/C3-C5/C9)
    """
    if url.startswith(("mp/private/", "private/", "mp/public/", "public/")):
        return True
    if url != url.strip():
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in _PRIVATE_HOSTNAMES:
        return False
    # SSRF guard — reject private / loopback / link-local IPs at the URL layer.
    # Matches Base44's "Invalid file attachment" for 127.0.0.1, 10.x, 192.168.x,
    # 169.254.x, 0.0.0.0 (probe-locked own-probes 2026-05-21 C3/C4/C5/C9).
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # hostname (not an IP literal) — DNS-resolves at fetch time
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_unspecified or ip.is_reserved or ip.is_multicast:
        return False
    return True


async def download_file(url: str) -> bytes:
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content
