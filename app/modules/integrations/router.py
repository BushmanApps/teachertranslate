"""Core integrations module — all integration endpoints."""

from fastapi import APIRouter, Depends

from app.modules.integrations.credit_protection import guard_core
from app.modules.integrations.invoke_llm import invoke_llm
from app.modules.integrations.send_email import send_email
from app.modules.integrations.send_push_notification import send_push_notification
from app.modules.integrations.upload_file import upload_file

# Credit protection guards every Core route (credit_protection.py decides
# which ones it applies to); a router dependency runs before the route's body
# is validated, the order Base44 answers in.
router = APIRouter(
    prefix="/api/apps/{app_id}/integration-endpoints",
    tags=["integrations"],
    dependencies=[Depends(guard_core)],
)

router.add_api_route("/Core/InvokeLLM", invoke_llm, methods=["POST"])
router.add_api_route("/Core/SendEmail", send_email, methods=["POST"])
router.add_api_route("/Core/SendPushNotification", send_push_notification, methods=["POST"])
router.add_api_route("/Core/UploadFile", upload_file, methods=["POST"])


installable_router = APIRouter(
    prefix="/api/apps/{app_id}/integration-endpoints/installable",
    tags=["integrations-installable"],
)


@installable_router.post("/{package_name}/integration-endpoints/{endpoint_name}")
async def installable_stub(app_id: str, package_name: str, endpoint_name: str):
    from app.core.errors import AppHTTPException
    raise AppHTTPException(405, "Method Not Allowed")
