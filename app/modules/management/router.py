"""Management module — public endpoints not tied to a specific SDK module.

Routers, all auto-mounted by `app.main._discover_and_mount_modules`:
- `router`            — /api/apps/public/prod/public-settings/by-id/{app_id}
- `login_info_router` — /api/apps/public/login-info/by-id/{app_id}
- `runtime_app_router`— /api/apps/public/prod/by-id/{app_id}
- `internal_router`   — /_internal/tls-allowed (Caddy on-demand-TLS ask hook)
"""

from fastapi import APIRouter

from app.modules.management.login_info import login_info
from app.modules.management.public_settings import public_settings
from app.modules.management.runtime_app import get_runtime_app
from app.modules.management.tls_check import tls_allowed

router = APIRouter(prefix="/api/apps/public/prod/public-settings", tags=["management"])
router.add_api_route("/by-id/{app_id}", public_settings, methods=["GET"])

login_info_router = APIRouter(prefix="/api/apps/public/login-info", tags=["management"])
login_info_router.add_api_route("/by-id/{app_id}", login_info, methods=["GET"])

runtime_app_router = APIRouter(prefix="/api/apps/public/prod", tags=["management"])
runtime_app_router.add_api_route("/by-id/{app_id}", get_runtime_app, methods=["GET"])

# Internal hook for Caddy's on-demand TLS (see tls_check.py). Not an SDK
# surface — Caddy reaches it over the docker network at backend:8000.
internal_router = APIRouter(tags=["internal"])
internal_router.add_api_route("/_internal/tls-allowed", tls_allowed, methods=["GET"])
