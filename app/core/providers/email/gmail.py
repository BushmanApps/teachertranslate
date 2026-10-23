"""Gmail through the app owner's Google Workspace — the email sender of the
Google HIPAA lineup (SES is the AWS lineup's). Gmail is on Google Workspace's
HIPAA Included Functionality list; the owner accepts the Workspace BAA in
their Admin console.

The credential is the service-account key the owner pasted for Compute
Engine (GMAIL_SERVICE_ACCOUNT_JSON_B64), which their Workspace admin
authorized under domain-wide delegation for exactly the Gmail scopes below.
Every send acts as the owner's own account (GMAIL_SENDER_USER — the `sub` of
the token) and goes out "From" the `noreply@<their domain>` alias the
migration added to it (EMAIL_FROM). Google minting the token IS the
authorization check; a revoked delegation is a 401 at the next send, which
every caller already treats as a failed send.

No starter mode, no review: a Workspace account sends up to 2,000 messages a
day from day one. Transport security is Google's: TLS to every receiver that
offers it, and the owner may require it for all outbound mail in the Admin
console (Gmail → Compliance → Secure transport) — the hub's card names it.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Sequence
from email.message import EmailMessage
from email.utils import formataddr

import httpx
import jwt

from .base import Attachment

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
_SCOPES = "https://www.googleapis.com/auth/gmail.send"


class GmailEmailProvider:
    def __init__(self, service_account_json_b64: str, sender_user: str, email_from: str):
        self._sa = json.loads(base64.b64decode(service_account_json_b64))
        self._sender_user = sender_user
        self._email_from = email_from
        self._token: tuple[str, float] | None = None

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
        msg = EmailMessage()
        msg["From"] = formataddr((from_name, self._email_from)) if from_name else self._email_from
        msg["To"] = to
        msg["Subject"] = subject
        # The two bodies as Base44 composes them: text and html as
        # alternatives, one of them alone as the single part.
        if text is not None:
            msg.set_content(text)
            if html is not None:
                msg.add_alternative(html, subtype="html")
        elif html is not None:
            msg.set_content(html, subtype="html")
        else:
            msg.set_content("")
        for a in attachments:
            maintype, _, subtype = a.content_type.partition("/")
            msg.add_attachment(a.content, maintype=maintype, subtype=subtype or "octet-stream", filename=a.filename)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

        token = await self._access_token()
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(_SEND_URL, headers={"Authorization": f"Bearer {token}"}, json={"raw": raw})
        if res.status_code >= 400:
            raise RuntimeError(f"Gmail refused the send ({res.status_code}): {res.text[:300]}")

    async def _access_token(self) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": self._sa["client_email"],
                "sub": self._sender_user,
                "scope": _SCOPES,
                "aud": _TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            },
            self._sa["private_key"],
            algorithm="RS256",
        )
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                _TOKEN_URL,
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            )
        if res.status_code != 200:
            raise RuntimeError(
                f"Google would not let the key act as {self._sender_user} ({res.status_code}) — "
                f"the Workspace admin's domain-wide delegation for this key: {res.text[:200]}"
            )
        data = res.json()
        self._token = (data["access_token"], now + int(data.get("expires_in", 3600)))
        return self._token[0]
