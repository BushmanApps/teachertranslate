"""The page a link-delivered message opens on (core/mail/link.py).

GET  /api/apps/{app_id}/mail/{token} — a neutral page: the app's name and one
     "Open message" button. Nothing of the message: mail scanners fetch every
     link in an email, and a fetch must find nothing.
POST /api/apps/{app_id}/mail/{token} — the message itself (the button is a
     form submit). No login: the token is the key, the link is the one the
     recipient was sent, and it never expires (the inbox is their archive).
POST /api/apps/{app_id}/mail/{token}/attachments/{index} — one attachment of
     it, as a download (a button on the message page; a POST like the
     message, so no link on the page hands a scanner the file).

Public by design (no auth dependency) — the recipient may not be an app user
in any sense the app can authenticate (the SendEmail rule only requires a
User record, not a session). Ships iff the app sends app emails at all (the
prune manifest: a SendEmail call or workflows).
"""

from fastapi import APIRouter

from app.modules.mail.page import download_attachment, open_message, show_notice

router = APIRouter(prefix="/api/apps/{app_id}/mail", tags=["mail"])
router.add_api_route("/{token}", show_notice, methods=["GET"])
router.add_api_route("/{token}", open_message, methods=["POST"])
router.add_api_route("/{token}/attachments/{index}", download_attachment, methods=["POST"])
