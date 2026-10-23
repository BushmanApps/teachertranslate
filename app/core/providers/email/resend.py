import asyncio
import base64
from typing import Sequence

import resend as _resend

from .base import Attachment, sender


class ResendEmailProvider:
    def __init__(self, api_key: str, email_from: str):
        self._email_from = email_from
        _resend.api_key = api_key

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str | None = None,
        text: str | None = None,
        from_name: str | None = None,
        attachments: Sequence[Attachment] = (),
    ) -> None:
        params: dict = {
            "from": sender(self._email_from, from_name),
            "to": [to],
            "subject": subject,
        }
        if html is not None:
            params["html"] = html
            # Resend writes a plain-text copy of an html-only mail by itself;
            # an empty `text` opts out (its documented switch). Base44's
            # html-only mail is ONE part, html — measured on real mail, and
            # on the first real migration of this code the copy arrived as a
            # second part on every mail.
            params["text"] = text if text is not None else ""
        elif text is not None:
            params["text"] = text
        if attachments:
            params["attachments"] = [
                {
                    "filename": a.filename,
                    "content": base64.b64encode(a.content).decode("ascii"),
                    "content_type": a.content_type,
                }
                for a in attachments
            ]

        await asyncio.to_thread(_resend.Emails.send, params)
