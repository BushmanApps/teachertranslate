"""GET /api/apps/public/prod/public-settings/by-id/{app_id}

Visibility-gated. Returns the app's public_settings literal. The SDK uses
this on app boot to decide auth flow.
"""

from fastapi import Depends

from app.config import Settings
from app.core.errors import AppHTTPException
from app.core.models import PublicSettingsResponse
from app.core.security.pipeline import AuthedContext, get_authed_context_no_visibility
from app.core.security.visibility import assert_app_visible
from app.deps import get_settings


async def public_settings(
    app_id: str,
    ctx: AuthedContext = Depends(get_authed_context_no_visibility),
    settings: Settings = Depends(get_settings),
):
    if app_id != settings.APP_ID:
        raise AppHTTPException(404, "App not found")

    assert_app_visible(ctx.token_class, ctx.app_settings, app_id, user=ctx.user)

    return PublicSettingsResponse(
        id=app_id,
        public_settings=ctx.app_settings.get("public_settings", "public_without_login"),
    ).model_dump(mode="json")
