"""The message is the email — Base44's behaviour, every non-HIPAA app."""

from __future__ import annotations

from typing import Sequence

from app.core.providers.email.base import Attachment, EmailProvider


class InlineMail:
    def __init__(self, provider: EmailProvider):
        self._provider = provider

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
        await self._provider.send(to=to, subject=subject, html=html, text=text, from_name=from_name, attachments=attachments)
