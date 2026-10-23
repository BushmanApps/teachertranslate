"""POST /api/apps/:appId/integration-endpoints/Core/SendPushNotification

Base44's built-in push integration, as measured on 2026-09-17 (divergence
chase `2026-09-17-speech-transcribe-upload-push`): service-role callers only
(an app-user token → 403 with the sentence below), `user_id` + `title` +
`content` required and non-empty, extra fields ignored, a user id outside
the app → "Cannot send a push to a user outside the app". The limits — 100
characters of title, 500 of content, 50 of action label — are Base44's
documented ones (Integrations → built-in integrations); their 422 wording
for a too-long value is pydantic's, as every other Core 422 measured is.

The push itself goes through the owner's own APNs key and Firebase project
(modules/push) to every device the person registered from the app.
"""

from __future__ import annotations

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Body, Depends

from app.config import Settings
from app.core import db
from app.core.errors import AppHTTPException
from app.core.models import SendPushNotificationRequest
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings
from app.modules.integrations.helpers import validate_body
from app.modules.push.send import send_to_user


async def send_push_notification(
    app_id: str,
    body: dict = Body(...),
    ctx: AuthedContext = Depends(get_authed_context),
    settings: Settings = Depends(get_settings),
):
    if ctx.token_class != "service_role":
        raise AppHTTPException(403, "SendPushNotification is only available to service-role (server-side) callers")
    req = validate_body(SendPushNotificationRequest, body)

    try:
        oid = ObjectId(req.user_id)
    except (InvalidId, TypeError):
        oid = None
    user = await db.coll("User").find_one({"_id": oid, "app_id": settings.APP_ID}, {"_id": 1}) if oid else None
    if not user:
        raise AppHTTPException(404, "Cannot send a push to a user outside the app")

    await send_to_user(settings, str(user["_id"]), req.title, req.content, req.action_label, req.action_url)
    return {"success": True}
