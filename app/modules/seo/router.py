"""Static-file SEO endpoints (auto-discovered by main.py).

These serve the SEO files the migrator captured from Base44 into the
`_seo_files` Mongo collection — verbatim. Every URL inside them was already
rewritten by the migration's reference pass (file hosts → the user's storage,
the app's own Base44 origin → its eb44 address) and is rewritten again by the
custom-domain switch, so nothing is substituted here at serve time. Read live
per request — these paths are hit rarely (crawlers, installs), and live reads
mean a rewrite of the stored files (the canonical-URL switch) serves
immediately.

Precedence, matching Base44: a file the app SHIPS in its build output
(`public/manifest.json`, its own robots.txt, …) is served as that file; the
captured copy is only for apps that don't ship one. Absent paths return 404 —
mirroring Base44 (e.g. apps without seo_settings have no sitemap.xml or
llms.txt).

The favicon / apple-touch-icon endpoints 302 to `_app_settings.logo_url`
(unless the app ships the file).

The HTML catch-all is NOT here — it lives in `app/main.py`'s `_mount_fallback`
because there's already a catch-all there. See render.py for the algorithm.
"""

from __future__ import annotations

import inspect
import json

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from app.core import db, mobile_identity
from app.core.errors import AppHTTPException
from app.core.static_files import try_serve_static


router = APIRouter(tags=["seo"])


async def _serve_seo_file(request: Request, path: str, content_type: str) -> Response:
    """Serve `path`: the app's own file if it ships one, else the captured
    copy from `_seo_files`, else 404 with an empty body and the route's own
    `content_type`.

    `body` is coerced to bytes regardless of whether it is stored as text
    (every migration since 2026-08-30) or as Mongo Binary (older ones).

    Why content-type comes from the route rather than the entry:
    - When the migrator captured the file (entry present), it stored Base44's
      actual content-type at capture time — we use that verbatim.
    - When the file is missing (entry absent, e.g. /sitemap.xml on apps with
      no `seo_settings`), Base44 still emits the path's natural content-type
      with an empty body. We don't have a captured value to fall back on, so
      the route declares its own.
    The single source of truth is the route declaration below.
    """
    static = try_serve_static(request.app.state.settings.FRONTEND_DIR, path)
    if static is not None:
        return static
    doc = await db.coll("_seo_files").find_one({"path": path})
    body = doc.get("body") if doc else None
    if body is None:
        return Response(content=b"", status_code=404, media_type=content_type)
    body = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    return Response(content=body, media_type=doc.get("content_type") or "application/octet-stream")


async def _icon_redirect(request: Request, path: str) -> Response:
    static = try_serve_static(request.app.state.settings.FRONTEND_DIR, path)
    if static is not None:
        return static
    app_settings = await db.app_settings()
    logo_url = (app_settings.get("logo_url") or "").strip()
    if not logo_url:
        raise AppHTTPException(404, "Not found")
    return RedirectResponse(logo_url, status_code=302)


@router.api_route("/manifest.json", methods=["GET", "HEAD"])
async def serve_manifest(request: Request) -> Response:
    return await _serve_seo_file(request, "/manifest.json", "application/json")


@router.api_route("/robots.txt", methods=["GET", "HEAD"])
async def serve_robots(request: Request) -> Response:
    return await _serve_seo_file(request, "/robots.txt", "text/plain; charset=utf-8")


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"])
async def serve_sitemap(request: Request) -> Response:
    return await _serve_seo_file(request, "/sitemap.xml", "application/xml")


@router.api_route("/llms.txt", methods=["GET", "HEAD"])
async def serve_llms(request: Request) -> Response:
    return await _serve_seo_file(request, "/llms.txt", "text/plain; charset=utf-8")


async def _serve_derived(request: Request, path: str, content_type: str, derived) -> Response:
    """A file the phones (or the ad network) read off the app's address: the
    app's own file when it ships one; else the one derived from the app's
    mobile facts (core/mobile_identity.py) when there is one to derive; else
    the captured copy, as for every SEO file — an app that never turned the
    feature on keeps serving exactly what Base44 served."""
    static = try_serve_static(request.app.state.settings.FRONTEND_DIR, path)
    if static is not None:
        return static
    body = derived(request.app.state.settings)
    if inspect.isawaitable(body):
        body = await body
    if body is not None:
        text = body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))
        return Response(content=text.encode("utf-8"), media_type=content_type)
    return await _serve_seo_file(request, path, content_type)


@router.api_route("/.well-known/apple-app-site-association", methods=["GET", "HEAD"])
async def serve_apple_app_site_association(request: Request) -> Response:
    return await _serve_derived(request, "/.well-known/apple-app-site-association", "application/json", mobile_identity.apple_app_site_association)


@router.api_route("/.well-known/assetlinks.json", methods=["GET", "HEAD"])
async def serve_assetlinks(request: Request) -> Response:
    return await _serve_derived(request, "/.well-known/assetlinks.json", "application/json", mobile_identity.asset_links)


@router.api_route("/app-ads.txt", methods=["GET", "HEAD"])
async def serve_app_ads(request: Request) -> Response:
    return await _serve_derived(request, "/app-ads.txt", "text/plain; charset=utf-8", mobile_identity.app_ads_txt)


@router.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def serve_favicon(request: Request) -> Response:
    return await _icon_redirect(request, "/favicon.ico")


@router.api_route("/apple-touch-icon.png", methods=["GET", "HEAD"])
async def serve_apple_touch_icon(request: Request) -> Response:
    return await _icon_redirect(request, "/apple-touch-icon.png")


@router.api_route("/apple-touch-icon-precomposed.png", methods=["GET", "HEAD"])
async def serve_apple_touch_icon_precomposed(request: Request) -> Response:
    return await _icon_redirect(request, "/apple-touch-icon-precomposed.png")
