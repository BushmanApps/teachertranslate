"""
FastAPI application factory.

- Connects to MongoDB and loads config on startup
- Auto-discovers and mounts module routers from app/modules/*/router.py
- Conditionally mounts Socket.IO for realtime
- GET/HEAD catch-all serves static frontend files; unmatched paths render
  `index.html` per-request via the SEO templater.

The catch-all does NOT enforce visibility/auth. Base44's catch-all serves
the SPA HTML for every unmatched GET/HEAD, and the SPA handles auth
client-side (it's the same SPA we ship). A server-side redirect-to-/login
here would fight the SPA's own auth flow. Visibility lives on the API
routes only.
"""

import asyncio
import importlib
from contextlib import asynccontextmanager
from pathlib import Path

import orjson
from bson import ObjectId
from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response

from app.config import Settings
from app.deps import get_settings
from app.core import addresses, db, errors, realtime, reconcile
from app.core.internal_auth import check_cron_secret
from app.core.security.headers import SecurityHeaders
from app.core.schema import registry
from app.core.static_files import try_serve_static
from app.core.redirects import CACHE_CONTROL, redirect_location
from app.modules.seo.render import page_for, read_index_html, render_html


def _orjson_default(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError


class ORJSONResponse(Response):
    media_type = "application/json"

    def render(self, content) -> bytes:
        return orjson.dumps(content, default=_orjson_default, option=orjson.OPT_UTC_Z)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    db.init(settings.MONGO_URL, settings.MONGO_DB)
    await registry.load()

    # Fail fast on a missing frontend build — the catch-all reads it per
    # request from then on (never cached: a frontend-only redeploy swaps the
    # dist files under a running process, and serving a memorized index.html
    # against new chunk hashes breaks every page load).
    read_index_html(settings)

    await _run_module_startup_hooks()

    _init_providers(app, settings)

    # SES starter mode (ses_starter.py): the kept emails are retried by a
    # minutely loop wherever a long-lived server owns the process; on
    # serverless the container is frozen after each response
    # (EB44_BACKGROUND_TASKS), and SES is never selected there (the HIPAA
    # lineup is a box).
    retrier = app.state.email_provider if hasattr(app.state.email_provider, "run_forever") else None
    retry_loop = asyncio.create_task(retrier.run_forever()) if retrier and settings.EB44_BACKGROUND_TASKS else None

    yield

    if retry_loop:
        retry_loop.cancel()
    db.close()


def create_app():
    """Build the ASGI app uvicorn serves.

    Returns the FastAPI app when realtime is disabled. With realtime
    enabled, returns `socketio.ASGIApp` wrapping the FastAPI app — that's
    the library-default integration where Socket.IO intercepts its own
    path and delegates everything else (lifespan included) to FastAPI.
    Same shape Base44 dev-server uses (`new SocketIOServer(httpServer,
    { path })` — Socket.IO sits on the HTTP server, app handles the
    rest). Without this wrapping, mounting Socket.IO at `/` shadows
    every route registered after it (e.g. `/health` and the SPA
    catch-all).
    """
    # ONE Settings per process, through the same cached accessor every request
    # uses (deps.get_settings is @lru_cache'd). Constructing it here warms that
    # cache at import time, which is what makes the workflows module's env
    # scrub safe: after it runs, nothing ever re-reads os.environ for a
    # scrubbed key. Calling Settings() directly here would leave the cache
    # cold and the first request would rebuild from a scrubbed environment.
    settings = get_settings()

    app = FastAPI(lifespan=lifespan, default_response_class=ORJSONResponse)
    app.state.settings = settings

    origins = settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS != "*" else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeaders)

    errors.register_handlers(app)
    _discover_and_mount_modules(app)
    _mount_health(app)
    _mount_internal_reconcile(app)
    _mount_fallback(app)

    if settings.REALTIME_ENABLED:
        return realtime.init(settings, other_asgi_app=app)
    return app


def _discover_and_mount_modules(app: FastAPI) -> None:
    modules_dir = Path(__file__).parent / "modules"
    for module_path in sorted(modules_dir.iterdir()):
        router_file = module_path / "router.py"
        if module_path.is_dir() and router_file.exists():
            mod = importlib.import_module(f"app.modules.{module_path.name}.router")
            router = getattr(mod, "router", None)
            if router:
                app.include_router(router)
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if attr is not router and isinstance(attr, APIRouter):
                    app.include_router(attr)


async def _run_module_startup_hooks() -> None:
    """Call the optional ``on_startup`` coroutine each module may expose in its
    ``lifespan.py``. The lifespan analog of ``_discover_and_mount_modules``: a
    module opts in by shipping ``lifespan.py`` with an ``on_startup`` hook, and
    pruned modules contribute nothing. Keeps ``main`` agnostic to which modules
    are present so the migrator can drop any of them.
    """
    modules_dir = Path(__file__).parent / "modules"
    for module_path in sorted(modules_dir.iterdir()):
        lifespan_file = module_path / "lifespan.py"
        if not (module_path.is_dir() and lifespan_file.exists()):
            continue
        mod = importlib.import_module(f"app.modules.{module_path.name}.lifespan")
        hook = getattr(mod, "on_startup", None)
        if hook is not None:
            await hook()


def _init_providers(app: FastAPI, settings: Settings) -> None:
    """
    Initialize provider adapters based on env config.
    Each adapter is implemented by the relevant module agent.
    If the adapter class doesn't exist yet, the provider stays None.
    """
    app.state.email_provider = None
    app.state.app_mail = None
    app.state.storage_provider = None

    try:
        from app.core.mail import build_app_mail
        from app.core.providers.email import build_email_provider
        app.state.email_provider = build_email_provider(settings)
        # How the app's own emails (SendEmail, workflow send_email) reach
        # their recipient — inline or by link, decided here once.
        app.state.app_mail = build_app_mail(app.state.email_provider, settings)
    except (ImportError, AttributeError):
        pass

    try:
        if settings.STORAGE_PROVIDER == "s3":
            from app.core.providers.storage.s3 import S3StorageProvider
            app.state.storage_provider = S3StorageProvider(
                settings.S3_BUCKET, settings.S3_REGION,
                settings.S3_ACCESS_KEY_ID, settings.S3_SECRET_ACCESS_KEY,
                settings.S3_ENDPOINT_URL, settings.S3_PUBLIC_URL,
                settings.S3_SESSION_TOKEN,
            )
        elif settings.STORAGE_PROVIDER == "vercel-blob":
            from app.core.providers.storage.vercel_blob import VercelBlobStorageProvider
            app.state.storage_provider = VercelBlobStorageProvider(
                settings.BLOB_READ_WRITE_TOKEN, settings.BLOB_PUBLIC_URL,
            )
    except (ImportError, AttributeError):
        pass


def _mount_internal_reconcile(app: FastAPI) -> None:
    """The one door the deploy runner converges the registries through — in
    core, so it exists whatever modules this backend ships (core/reconcile.py)."""
    @app.post("/api/internal/reconcile")
    async def internal_reconcile(
        payload: dict,
        settings: Settings = Depends(get_settings),
        x_eb44_cron_secret: str | None = Header(default=None, alias="X-Eb44-Cron-Secret"),
    ) -> dict:
        check_cron_secret(x_eb44_cron_secret, settings.EB44_CRON_SECRET)
        return await reconcile.converge(payload)


def _mount_health(app: FastAPI) -> None:
    @app.get("/health")
    async def health():
        return {"status": "ok"}


def _mount_fallback(app: FastAPI) -> None:
    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    async def html_catchall(request: Request, path: str):
        """
        The owner's redirect rules, then static files, then the SPA HTML
        catch-all. Any GET/HEAD that didn't match a module route falls here.

        0. A path one of the owner's URL redirect rules names answers its 301
           (core/redirects.py).
        1. If the path maps to a real file in FRONTEND_DIR (assets, the
           static login page, etc.), serve it as-is. This is the role
           Vercel's CDN / Caddy plays in those deploys; bringing it into the
           backend means the same routing works regardless of where we're
           deployed (Hetzner, Vercel, local) — single source of truth.
        2. Otherwise, `index.html` with the head Base44 served for this page
           merged in (the migration's capture, `_seo_pages`) and the
           visitor's path put in. The template is read from disk per
           request — a frontend-only redeploy replaces the dist files
           without restarting this process, so a startup-cached copy would
           reference deleted chunk hashes and break every page. No
           visibility/auth gate here — Base44's catch-all is dumb-200 and
           the SPA handles auth client-side.
        """
        settings: Settings = request.app.state.settings
        request_path = request.url.path

        # The owner's redirect rules answer before anything the app has at the path.
        rules = (await db.app_settings()).get("eb44_url_redirects") or []
        # the path and the query as the server took them off the request line
        # (`request.url` is put together again from both and read a second time)
        location = redirect_location(rules, request.scope["path"], request.scope["query_string"].decode("latin-1"))
        if location is not None:
            return Response(status_code=301, headers={"Location": location, "Cache-Control": CACHE_CONTROL})

        static_response = try_serve_static(settings.FRONTEND_DIR, request_path)
        if static_response is not None:
            return static_response

        body, headers = render_html(
            read_index_html(settings),
            await page_for(request_path),
            query=request.url.query,
            # Arrival host, like Base44: the page's address is the one the
            # visitor is on.
            base_url=await addresses.arrival_base_url(request),
        )
        return HTMLResponse(content=body, status_code=200, headers=headers)


app = create_app()
