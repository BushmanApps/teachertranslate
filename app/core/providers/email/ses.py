"""Amazon SES (v2) behind the EmailProvider Protocol — the app owner's own AWS
account, HIPAA-eligible under the AWS BAA they sign in AWS Artifact.

The sending identity (EMAIL_FROM's domain) is verified by the migration:
the app's own `{slug}.eb44.app` with Easy DKIM records in EscapeBase44's
zone, or the owner's custom domain with the records the domain card hands
them. A fresh AWS account starts in the SES sandbox (verified recipients
only) until AWS approves the production-access request the migration files
at the credentials step — until then sends to strangers are rejected by
SES, which every caller already treats as a failed send.

aioboto3 is the `storage` optional extra (the same client S3 uses); the
migrator selects it whenever EMAIL_PROVIDER is ses.
"""

from __future__ import annotations

from typing import Sequence

import aioboto3

from .base import Attachment, sender


class SesEmailProvider:
    def __init__(
        self, region: str, access_key_id: str, secret_access_key: str, email_from: str,
        endpoint_url: str | None = None,
    ):
        self._email_from = email_from
        self._session = aioboto3.Session()
        self._client_kwargs = {
            "service_name": "sesv2",
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "endpoint_url": endpoint_url,
        }

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
        body: dict = {}
        if text is not None:
            body["Text"] = {"Data": text, "Charset": "UTF-8"}
        if html is not None:
            body["Html"] = {"Data": html, "Charset": "UTF-8"}
        simple: dict = {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": body,
        }
        if attachments:
            # The encoding is NAMED: left to SES, an attachment travels as
            # `7bit` and arrives with other bytes — a line feed becomes two
            # bytes, a 70-byte picture arrived as 194 (measured on a real
            # migration and straight against SES, 2026-09-29). As base64 it
            # arrives byte for byte.
            simple["Attachments"] = [
                {
                    "FileName": a.filename,
                    "RawContent": a.content,
                    "ContentType": a.content_type,
                    "ContentDisposition": "ATTACHMENT",
                    "ContentTransferEncoding": "BASE64",
                }
                for a in attachments
            ]

        async with self.client() as ses:
            await ses.send_email(
                FromEmailAddress=sender(self._email_from, from_name),
                Destination={"ToAddresses": [to]},
                Content={"Simple": simple},
            )

    def client(self):
        """An SESv2 client context on the owner's key — the send above and
        the starter-mode handling (ses_starter.py) share it."""
        return self._session.client(**self._client_kwargs)
