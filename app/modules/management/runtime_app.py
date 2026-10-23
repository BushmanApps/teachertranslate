"""GET /api/apps/public/prod/by-id/{app_id}

Serves the full RuntimeApp shape — 72 fields covering app metadata, auth
config, layout, components, agents config, etc. The SDK and the deployed
frontend both consume this on boot. Same envelope as public-settings
(visibility-gated, AppHTTPException 404 if app_id mismatch). Findings
L527-534.
"""

from fastapi import Depends

from app.config import Settings
from app.core import db
from app.core.errors import AppHTTPException
from app.core.models import RuntimeApp
from app.core.responses import app_settings_to_runtime
from app.core.security.pipeline import AuthedContext, get_authed_context_no_visibility
from app.core.security.visibility import assert_app_visible
from app.deps import get_settings


async def get_runtime_app(
    app_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
    settings: Settings = Depends(get_settings),
):
    if app_id != settings.APP_ID:
        raise AppHTTPException(404, "App not found")

    assert_app_visible(ctx.token_class, ctx.app_settings, app_id, user=ctx.user)

    # The full document, not `ctx.app_settings`: this response carries the
    # whole RuntimeApp shape (`agents`, `seo_settings` included), and those are
    # projected out of the hot per-request read (see core/db.py).
    return RuntimeApp(**app_settings_to_runtime(await db.app_settings_full())).model_dump(mode="json")
