"""Amazon SES in starter mode ("the sandbox"): a fresh AWS account's SES
sends only to addresses the account has verified, until Amazon grants
production access — a review that takes days and is refused as often as not
(research/hipaa/EMAIL-PROVIDERS-2026-09-24.md).

The rule (Michal, 2026-09-25: "if we try sending an email that isn't
verified yet then add it to the verified emails"), plus a plain retry so the
email itself is not lost: when Amazon refuses a send, Amazon is asked the
facts that define the case — is this account still in starter mode, is this
address unverified, and does the person already hold a live link — and the
address is registered on the owner's key only when no live link exists
(Amazon mails THAT PERSON its confirmation link, the owner sees nothing;
Amazon's own `VerificationStatus`: absent or FAILED → a link is issued,
PENDING → the one they have stands — a second registration would mail them
again AND kill the first link, measured 2026-09-25). The email is kept. Any
other refusal is raised as it was. Every ten seconds the kept emails are
looked at: Amazon is asked whether each address is verified now, and a
verified one gets its emails, in order (a week-old email is dropped,
logged); the retry issues no links. Nothing is read before a send and
nothing about Amazon's state is kept here: with production access granted
Amazon never refuses, and none of this runs.

The retry runs where a long-lived server owns the process
(EB44_BACKGROUND_TASKS — the HIPAA lineup is always a box).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Sequence

from app.core import db
from app.core.providers.email.base import Attachment, attachments_from_docs, attachments_to_docs
from app.core.providers.email.ses import SesEmailProvider
from app.core.responses import utcnow_naive

logger = logging.getLogger("escapebase44.mail")

OUTBOX = "_email_outbox"
KEPT_FOR = timedelta(days=7)
RETRY_INTERVAL_SECONDS = 10
FIELDS = ("to", "subject", "html", "text", "from_name")


class SesStarterModeProvider:
    """The SES transport with an unverified recipient registered and the email
    kept for retry, instead of the send failing — the same `send` contract as
    every EmailProvider."""

    def __init__(self, provider: SesEmailProvider):
        self._provider = provider
        self._retrying = asyncio.Lock()

    async def send(self, *, to: str, subject: str, html: str | None = None, text: str | None = None,
                   from_name: str | None = None, attachments: Sequence[Attachment] = ()) -> None:
        # The message as the outbox keeps it (an attachment's bytes as a document).
        message = {"to": to, "subject": subject, "html": html, "text": text,
                   "from_name": from_name, "attachments": attachments_to_docs(attachments)}
        if await self._try(message):
            return
        await db.coll(OUTBOX).insert_one({**message, "created_date": utcnow_naive()})
        logger.info("email to %s kept: the address is registered with Amazon, its confirmation link is on its way", to)

    async def _try(self, message: dict) -> bool:
        """Send; if Amazon refused because the account is in starter mode and
        the recipient is unverified, make sure the person holds a live link
        and answer False. Any other refusal raises."""
        try:
            await self._provider.send(**_as_sent(message))
            return True
        except Exception as refusal:
            async with self._provider.client() as ses:
                identity = await _identity(ses, message["to"])
                if not await _starter_mode_unverified(ses, identity):
                    raise refusal
                if identity is not None and identity.get("VerificationStatus") == "PENDING":
                    return False  # their link is out there; a new one would replace it
                if identity is not None:
                    await ses.delete_email_identity(EmailIdentity=message["to"])  # the old link died: a fresh one
                await ses.create_email_identity(EmailIdentity=message["to"])
        return False

    async def retry(self) -> dict:
        """The kept emails whose address is verified now go out, in order; the
        rest wait. Asks Amazon one question per waiting address and sends
        nothing to an address it says is unverified — so no new link is ever
        issued from here."""
        async with self._retrying:
            sent = dropped = 0
            now = utcnow_naive()
            verified: dict[str, bool] = {}
            for kept in await db.coll(OUTBOX).find({}).sort("created_date", 1).to_list(None):
                to = kept["to"]
                if now - kept["created_date"] > KEPT_FOR:
                    await db.coll(OUTBOX).delete_one({"_id": kept["_id"]})
                    dropped += 1
                    logger.warning("dropped an email to %s: unverified with Amazon for a week", to)
                    continue
                if to not in verified:
                    async with self._provider.client() as ses:
                        verified[to] = not await _starter_mode_unverified(ses, await _identity(ses, to))
                if not verified[to]:
                    continue
                await self._provider.send(**_as_sent(kept))
                await db.coll(OUTBOX).delete_one({"_id": kept["_id"]})
                sent += 1
            return {"sent": sent, "dropped": dropped}

    async def run_forever(self) -> None:
        while True:
            await asyncio.sleep(RETRY_INTERVAL_SECONDS)
            try:
                await self.retry()
            except Exception:
                logger.warning("email retry failed; next minute", exc_info=True)


def _as_sent(message: dict) -> dict:
    """A kept message back into the transport's arguments."""
    return {**{k: message.get(k) for k in FIELDS}, "attachments": attachments_from_docs(message.get("attachments"))}


async def _identity(ses, address: str) -> dict | None:
    try:
        return await ses.get_email_identity(EmailIdentity=address)
    except ses.exceptions.NotFoundException:
        return None


async def _starter_mode_unverified(ses, identity: dict | None) -> bool:
    """The two facts, read off Amazon: no production access on the account,
    and the address not verified for sending."""
    account = await ses.get_account()
    if account.get("ProductionAccessEnabled"):
        return False
    return identity is None or not identity.get("VerifiedForSendingStatus")
