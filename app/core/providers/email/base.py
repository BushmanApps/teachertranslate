"""What every email transport takes: one message, already composed.

`html` and `text` are the message's two bodies — either or both. With both
the mail is a multipart/alternative (text first, html second), with one it is
that single part: what Base44's own sender produces for the same fields
(measured 2026-09-28 on real mail, `research/divergence-chasing/
2026-09-28-parity-audit/`). Attachments arrive byte for byte, each named and
typed as the app gave it.

A message that is KEPT rather than sent — Amazon's starter mode holds one
until the person confirms their address (ses_starter.py), a link-delivered
one stays on the app's server (core/mail/link.py) — is stored with its
attachments as documents; `attachments_to_docs` / `attachments_from_docs`
are the one round trip."""

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    content_type: str


class EmailProvider(Protocol):
    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str | None = None,
        text: str | None = None,
        from_name: str | None = None,
        attachments: Sequence[Attachment] = (),
    ) -> None: ...


def sender(email_from: str, from_name: str | None) -> str:
    return f"{from_name} <{email_from}>" if from_name else email_from


def attachments_to_docs(attachments: Sequence[Attachment]) -> list[dict]:
    return [{"filename": a.filename, "content_type": a.content_type, "content": a.content} for a in attachments]


def attachments_from_docs(docs: Sequence[dict] | None) -> list[Attachment]:
    return [Attachment(filename=d["filename"], content=bytes(d["content"]), content_type=d["content_type"]) for d in docs or []]
