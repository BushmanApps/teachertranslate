"""App-logs module — no-op stub.

The SDK's `appLogs` module records page visits and reads back aggregated
logs/stats for the in-dashboard analytics view. We don't surface that view
in a migrated app, so all three endpoints are no-ops that return empty
shapes the SDK is happy to consume.

Two prefixes are mounted because two callers hit different paths:

1. `/api/app-logs/{app_id}/...` — what the SDK's `appLogs` module emits.
   `@base44/sdk` declares `baseURL: <serverUrl>/api` on its axios client,
   and the appLogs module appends `/app-logs/{appId}/...`, so the final
   wire URL gets the `/api` prefix automatically. This also matches
   Base44 production wire on every probed app.

2. `/app-logs/{app_id}/...` — what `@base44/vite-plugin`'s inline analytics
   script emits (raw `fetch()`, not axios — no `/api/` prefix prepended).
   The plugin source hardcodes the path without `/api/`. Base44 production
   evidently runs an older / patched plugin where the inline script includes
   `/api/`; the currently-published plugin (1.0.17) omits it. We alias both
   prefixes to the same handlers so neither caller misroutes.
"""

from fastapi import APIRouter


def _register(router: APIRouter) -> None:
    @router.post("/log-user-in-app/{page_name}")
    async def log_user_in_app(app_id: str, page_name: str) -> dict:
        return {}

    @router.get("")
    async def fetch_logs(app_id: str) -> list:
        return []

    @router.get("/stats")
    async def get_stats(app_id: str) -> dict:
        return {}


router = APIRouter(prefix="/api/app-logs/{app_id}", tags=["app-logs"])
_register(router)

# Alias for the plugin-injected analytics inline script (raw `fetch()` without
# the SDK's axios baseURL — see module docstring). Auto-discovered by main.py
# the same way `router` is.
alias_router = APIRouter(prefix="/app-logs/{app_id}", tags=["app-logs"])
_register(alias_router)
