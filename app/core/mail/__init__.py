"""How an email the app's own code produces reaches its recipient — two
implementations of one contract, one chosen per deployment at startup by
the EMAIL_DELIVERY fact (the way EMAIL_PROVIDER picks the transport and
LLM_PROVIDER the model vendor). Callers (the SendEmail integration, the
workflows send_email activity) hold an `AppMail` and call `deliver`; which
one they hold is decided once, here, never inside a send.

  inline.py — the message IS the email, as Base44 sends it (every app).
  link.py   — the message stays on this server; the email is a notice with
              a button that opens it here over HTTPS (the HIPAA lineup).

A message is what the transport takes (core/providers/email/base.py): its
two bodies, either or both, and its attachments byte for byte.

The account emails (sign-in codes, password resets, invitations, the owner's
"workflow paused" notice) do not come through here: they carry no app data
and go straight to the transport whatever the fact says.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from app.config import Settings
from app.core.providers.email.base import Attachment, EmailProvider


class AppMail(Protocol):
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
    ) -> None: ...


def build_app_mail(provider: EmailProvider | None, settings: Settings) -> AppMail | None:
    if provider is None:
        return None
    if settings.EMAIL_DELIVERY == "link":
        from app.core.mail.link import LinkMail

        return LinkMail(provider, settings.APP_ID)
    from app.core.mail.inline import InlineMail

    return InlineMail(provider)
