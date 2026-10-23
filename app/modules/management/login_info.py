"""GET /api/apps/public/login-info/by-id/{app_id}

The login page (login.html) fetches this to render OAuth buttons, app name,
logo, etc. Wire shape: LoginInfoResponse — 12 fields including the full
AuthConfiguration nested dict. Field order matches Base44's production GET
response (own-probes §1, findings L480-505).
"""

from fastapi import Depends

from app.config import Settings
from app.core import db
from app.core.errors import AppHTTPException
from app.core.models import LoginInfoResponse
from app.core.responses import app_settings_to_runtime
from app.deps import get_settings


async def login_info(app_id: str, settings: Settings = Depends(get_settings)):
    if app_id != settings.APP_ID:
        raise AppHTTPException(404, "App not found")

    app_settings = await db.app_settings()
    if not app_settings:
        raise AppHTTPException(404, "App not found")

    # Same `_id` -> `id` translation `runtime_app.py` uses. Without it,
    # `LoginInfoResponse(...)` rejects on `id: str` missing because Mongo
    # docs carry `_id` (ObjectId), not `id`.
    return LoginInfoResponse(**app_settings_to_runtime(app_settings)).model_dump(mode="json")
