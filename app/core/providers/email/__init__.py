"""The app's email transport, chosen by its configuration — the one place
that reads `EMAIL_PROVIDER`: main.py's startup and the workflows engine
(which sends outside a request) both build theirs here, so a deployment's
fact governs every email — resend (every app), ses (the AWS HIPAA lineup,
in Amazon's starter mode until the account is approved), gmail (the Google
one). An app with no transport configured has none."""

from __future__ import annotations

from .base import Attachment, EmailProvider, attachments_from_docs, attachments_to_docs

__all__ = ["Attachment", "EmailProvider", "attachments_from_docs", "attachments_to_docs", "build_email_provider", "sends_from_own_domain"]


def build_email_provider(settings) -> EmailProvider | None:
    if not settings.EMAIL_FROM:
        return None
    if settings.EMAIL_PROVIDER == "resend" and settings.RESEND_API_KEY:
        from .resend import ResendEmailProvider

        return ResendEmailProvider(settings.RESEND_API_KEY, settings.EMAIL_FROM)
    if settings.EMAIL_PROVIDER == "ses" and settings.SES_ACCESS_KEY_ID and settings.SES_SECRET_ACCESS_KEY:
        from .ses import SesEmailProvider
        from .ses_starter import SesStarterModeProvider

        # An unverified recipient is registered with Amazon and the email kept
        # for retry, instead of the send failing (ses_starter.py).
        return SesStarterModeProvider(SesEmailProvider(
            settings.SES_REGION, settings.SES_ACCESS_KEY_ID, settings.SES_SECRET_ACCESS_KEY, settings.EMAIL_FROM,
            endpoint_url=settings.SES_ENDPOINT_URL,
        ))
    if settings.EMAIL_PROVIDER == "gmail" and settings.GMAIL_SERVICE_ACCOUNT_JSON_B64 and settings.GMAIL_SENDER_USER:
        from .gmail import GmailEmailProvider

        # The owner's Google Workspace (the Google HIPAA lineup): no starter
        # mode to handle, nothing to retry — a plain transport.
        return GmailEmailProvider(settings.GMAIL_SERVICE_ACCOUNT_JSON_B64, settings.GMAIL_SENDER_USER, settings.EMAIL_FROM)
    return None


def sends_from_own_domain(settings) -> bool:
    """Whether the app's mail leaves from a domain of its owner's — Base44's
    "verified custom domain". An app starts on the platform's zone
    (`…@eb44.app`, `…@{slug}.eb44.app`) and moves to the owner's domain when
    the domain card verifies it; only `EMAIL_FROM` says which it is."""
    address = settings.EMAIL_FROM.rsplit("<", 1)[-1].rstrip("> ").strip()
    domain = address.rpartition("@")[2].lower()
    base = settings.EB44_BASE_DOMAIN.lower()
    return bool(domain) and domain != base and not domain.endswith("." + base)
