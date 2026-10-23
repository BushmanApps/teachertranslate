"""The message never leaves this server — the HIPAA lineup's delivery.

The message is stored in `_email_messages` under a random token — its two
bodies and its attachments, byte for byte — and the recipient gets a
one-line notice with a button that opens it here over HTTPS (modules/mail
serves the page; an attachment is downloaded from it). Nothing of the
message — not the subject, not an attachment's name — is in the email, so a
mailbox provider holding the email holds no patient data and needs no BAA;
the page itself shows nothing until a button is pressed, because mail
scanners (Safe Links, Proofpoint, Gmail) fetch every link they see. The
link never expires: the person's inbox is their archive, and the message
stays on the app's server as long as the app does (Michal, 2026-09-25). No
login, no code.
"""

from __future__ import annotations

import secrets
from typing import Sequence

from app.core import db
from app.core.providers.email.base import Attachment, EmailProvider, attachments_to_docs
from app.core.providers.email.templates import message_notice_html
from app.core.responses import utcnow_naive

MESSAGES = "_email_messages"


def message_url(base_url: str, app_id: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/api/apps/{app_id}/mail/{token}"


class LinkMail:
    def __init__(self, provider: EmailProvider, app_id: str):
        self._provider = provider
        self._app_id = app_id

    async def deliver(
        self,
        *,
        to: str,
        subject: str,
        html: str | None = None,
        text: str | None = None,
        from_name: str | None = None,
        attachments: Sequence[Attachment] = (),
        base_url: str,
    ) -> None:
        token = secrets.token_urlsafe(32)
        await db.coll(MESSAGES).insert_one({
            "_id": token,
            "to": to,
            "subject": subject,
            "html": html,
            "text": text,
            "from_name": from_name,
            "attachments": attachments_to_docs(attachments),
            "created_date": utcnow_naive(),
            "opened_at": None,
        })

        app_name = from_name or (await db.app_settings()).get("name") or "the app"
        url = message_url(base_url, self._app_id, token)
        await self._provider.send(
            to=to,
            subject=f"New message from {app_name}",
            html=message_notice_html(app_name, url),
            text=f"{app_name} sent you a message.\n\nOpen it here: {url}",
            from_name=from_name,
        )
