"""POST /api/apps/:appId/integration-endpoints/Core/SendEmail

Base44's SendEmail since its rebuild (measured 2026-09-28/29): one recipient;
a `body` or `html` (the mail's html part, sent as written), a `text` (its
plain part), or a template of the app's own (`base44/emails/<name>.html`);
`{{variables}}` filled in all of them and in the subject; up to five
attachments. The request's rules are the model's (core/models/
integrations.py); this handler answers, in Base44's order: the recipient →
the attachments → the template → the subject.

Who may be written to. Base44 sends to the app's registered users (a user
who registered and never verified included) and, once the app has a verified
custom domain, to anyone. Here "a verified custom domain" is the app's mail
leaving from its owner's domain (providers/email `sends_from_own_domain`):
until then the mail leaves from the platform's zone, as Base44's does from
theirs.

Extras are ignored, as Base44 ignores them: `reply_to`, `headers`, `cc`,
`htmlBody` change nothing in the mail.
"""

from __future__ import annotations

import re

from fastapi import Body, Depends, Request

from app.core import addresses, db, email_templates
from app.core.errors import AppHTTPException
from app.core.models import SendEmailRequest
from app.core.providers.email import sends_from_own_domain
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_settings, get_storage_provider
from app.modules.integrations import email_attachments
from app.modules.integrations.helpers import validate_body


async def send_email(
    app_id: str,
    request: Request,
    body: dict = Body(...),
    ctx: AuthedContext = Depends(get_authed_context),
    settings=Depends(get_settings),
    storage=Depends(get_storage_provider),
):
    req = validate_body(SendEmailRequest, body)

    to = req.to.strip()
    if not to or "," in to or ";" in to:
        raise AppHTTPException(
            422, "'to' must be a single email address. To reach several people, send one email per recipient."
        )
    if not sends_from_own_domain(settings):
        recipient = await db.coll("User").find_one(
            {"email": {"$regex": f"^{re.escape(to)}$", "$options": "i"}}, {"_id": 1}
        )
        if recipient is None:
            raise AppHTTPException(
                422,
                "Emails to people who aren't registered users of this app need a verified custom domain. "
                "Connect and verify a domain, then try again.",
            )

    attachments = await email_attachments.gather(req.attachments or [], app_id=app_id, storage=storage)

    subject = (req.subject or "").strip() and email_templates.render(req.subject, req.variables, escape=False)
    template_name = req.template_id or req.template_name
    if template_name:
        # A template's id is Base44's own record of the file; the repo carries
        # the file, so here a template is found by its name and an id finds none.
        template = await email_templates.find(template_name) if req.template_name else None
        if template is None:
            raise AppHTTPException(404, email_templates.NOT_FOUND.format(name=template_name))
        title, html = email_templates.split_title(email_templates.render(template, req.variables, escape=True))
        subject = subject or title
        if not subject:
            raise AppHTTPException(
                422,
                "This email has no subject. Pass 'subject', or give the template a <title> "
                "in base44/emails/<Name>.html.",
            )
        text = None
    else:
        html = req.html if req.html and req.html.strip() else req.body
        html = None if html is None else email_templates.render(html, req.variables, escape=True)
        text = email_templates.render(req.text, req.variables, escape=False) if req.text and req.text.strip() else None

    app_mail = request.app.state.app_mail
    if app_mail is None:
        raise AppHTTPException(500, "Email provider not configured")

    await app_mail.deliver(
        to=to,
        # A subject is one line: a title written over several lines arrives joined.
        subject=re.sub(r"[\r\n]+", "", subject),
        html=html,
        text=text,
        from_name=req.from_name or (await db.app_settings()).get("name"),
        attachments=attachments,
        # A link-delivered message (the HIPAA lineup) opens at the address the
        # sender's visit came in on (the addresses doctrine: links in emails
        # sent during a visit derive from the arrival host).
        base_url=await addresses.arrival_base_url(request),
    )

    return {"success": True}
