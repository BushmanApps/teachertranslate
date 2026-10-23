"""The app's own email templates — `base44/emails/<name>.html` in its repo.

The repo is the source; `_email_templates` is the runtime copy, converged
onto the repo's files on every deploy (core/reconcile.py). Two senders read
it: Core SendEmail (`template_name`) and the workflows `send_email` activity.

Everything here is Base44's behaviour as measured on real mail (2026-08-31,
the workflows chase §5; 2026-09-28/29, the parity audit's SendEmail
batteries):

- a template's name is its path under `base44/emails/` without `.html` —
  exact, case-sensitive, a nested file included (`nested/inner`); a name
  carrying the extension misses, and so does any other file type;
- `{{ key }}` — whitespace of any kind around a key of word characters — is
  replaced when `variables` has the key and left as written when it has not;
  the value is Python's `str()` (`3`, `True`, `None`, a dict's repr); one
  pass, so a value holding `{{x}}` is not rendered again; a dotted path or a
  key with a dash is no placeholder;
- in html the value is HTML-escaped, quotes included; in plain text and in a
  subject it goes in raw;
- a template's `<title>` is its subject: the first `<title>` element,
  wherever it sits, leaves the html that is sent, and its text — entities
  decoded, trimmed — is the subject unless the sender passed one.
"""

from __future__ import annotations

import html as html_lib
import re

from app.core import db
from app.core.responses import utcnow_naive

COLLECTION = "_email_templates"
ROOT = "base44/emails/"
NOT_FOUND = "Email template '{name}' not found. Check the name matches a file in base44/emails/."

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title\s*>", re.IGNORECASE | re.DOTALL)


def render(source: str, variables: dict | None, *, escape: bool) -> str:
    if not variables:
        return source

    def fill(match: re.Match) -> str:
        key = match.group(1)
        if key not in variables:
            return match.group(0)
        value = str(variables[key])
        return html_lib.escape(value, quote=True) if escape else value

    return _PLACEHOLDER.sub(fill, source)


def split_title(html: str) -> tuple[str, str]:
    """(the title's text, the html without the title element) — an empty
    text when the html has no title or a blank one."""
    match = _TITLE.search(html)
    if match is None:
        return "", html
    return html_lib.unescape(match.group(1)).strip(), html[: match.start()] + html[match.end():]


async def find(name: str) -> str | None:
    doc = await db.coll(COLLECTION).find_one({"_id": name})
    return None if doc is None else doc["body"]


async def converge(files: dict[str, str]) -> dict:
    """Converge the runtime copy onto the repo's `base44/emails/**.html`.
    A template whose file is gone is deleted: the next send answers the
    not-found message, which is the file-deleted state on Base44 (their read
    is live from the file tree)."""
    wanted = {
        path[len(ROOT):-len(".html")]: text
        for path, text in files.items()
        if path.startswith(ROOT) and path.endswith(".html")
    }
    now = utcnow_naive()

    upserted, unchanged = [], 0
    for name, body in wanted.items():
        if await find(name) == body:
            unchanged += 1
            continue
        await db.coll(COLLECTION).update_one(
            {"_id": name}, {"$set": {"body": body, "updated_date": now}}, upsert=True,
        )
        upserted.append(name)

    removed = []
    async for doc in db.coll(COLLECTION).find({"_id": {"$nin": sorted(wanted)}}, {"_id": 1}):
        await db.coll(COLLECTION).delete_one({"_id": doc["_id"]})
        removed.append(doc["_id"])

    return {"upserted": upserted, "removed": removed, "unchanged_count": unchanged}
