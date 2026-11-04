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

A template written in MJML is compiled, the way Base44's own template
registry holds it (measured 2026-11-03 on the probe account: its template API
answers "inbox-ready HTML" and its test sender mails the same;
research/divergence-chasing/2026-11-02-mjml-email-templates):

- a file is MJML when, past leading whitespace and html comments, it opens
  with `<mjml` in any case; anything else (an xml declaration first, an html
  document holding an `<mjml>` element) is html and is kept as written;
- MJML is compiled with mrml's defaults — byte for byte what Base44 holds, on
  every case measured — and Base44 then puts one Google Fonts stylesheet link
  per font the email names right before `</head>` (`_google_fonts_block`);
- `{{ placeholders }}` survive the compile (in text, a `<mj-title>` that
  becomes the `<title>`, and attributes alike), so the senders fill the
  compiled html the same way they fill an html template;
- a file mrml cannot compile is no template at all: Base44 does not list it,
  so a send that names it answers the not-found message.
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
_LEADING_COMMENT = re.compile(r"\s*<!--.*?-->", re.DOTALL)

# What Base44 reads a font from: the first family of every `font-family`
# declaration in the compiled html, head and body, in order; a family is
# linked once (case counts: `roboto slab` and `Roboto Slab` are two links).
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;\"}]+)", re.IGNORECASE)
_FONT_NAME = re.compile(r"^[A-Za-z0-9 _.\-]+$")
# The families Base44 links no stylesheet for — every name here was measured
# unlinked, in any case (probes 03 and 04). Measured LINKED, so not here:
# Garamond, Comic Sans MS, Arial Black, Geneva, Lucida, Lucida Console,
# Lucida Sans Unicode, Trebuchet, Gill Sans, Optima, Candara, cursive, fantasy,
# emoji, initial, unset, a made-up name — and every Google font tried.
_SYSTEM_FONTS = frozenset(
    name.lower()
    for name in (
        "Arial", "Helvetica", "Helvetica Neue", "Georgia", "Verdana", "Tahoma",
        "Times", "Times New Roman", "Courier", "Courier New", "Trebuchet MS",
        "Segoe UI", "Impact", "Palatino", "Palatino Linotype", "Book Antiqua",
        "Lucida Grande", "Calibri", "Cambria", "Consolas", "Monaco", "Menlo",
        "system-ui", "-apple-system", "BlinkMacSystemFont", "ui-sans-serif",
        "ui-serif", "ui-monospace", "sans-serif", "serif", "monospace", "inherit",
    )
)


def is_mjml(source: str) -> bool:
    rest = source
    while (comment := _LEADING_COMMENT.match(rest)) is not None:
        rest = rest[comment.end():]
    return rest.lstrip()[:5].lower() == "<mjml"


def _google_fonts_block(html: str) -> str:
    families: list[str] = []
    for value in _FONT_FAMILY.findall(html):
        family = value.split(",")[0].strip().strip("'\"").strip()
        if (
            family
            and _FONT_NAME.match(family)
            and family.lower() not in _SYSTEM_FONTS
            and family not in families
        ):
            families.append(family)
    if not families:
        return ""
    links = "".join(
        f'<link href="https://fonts.googleapis.com/css2?family={family.replace(" ", "+")}'
        ':wght@400;500;600;700&amp;display=swap" rel="stylesheet" type="text/css">'
        for family in families
    )
    return f"<!--[if !mso]><!-->{links}<!--<![endif]-->"


def inbox_html(source: str) -> str | None:
    """What Base44's registry holds for a template file: an MJML file
    compiled, any other file as written — None for an MJML file that does not
    compile, which is no template."""
    if not is_mjml(source):
        return source
    import mrml  # only an app with an MJML template ever loads it

    try:
        html = mrml.to_html(source).content
    except Exception:
        # mrml raises for a file it cannot parse (an OSError naming the
        # position); whatever the reason, Base44 keeps no template for it.
        return None
    block = _google_fonts_block(html)
    if not block:
        return html
    head_end = html.find("</head>")
    return html[:head_end] + block + html[head_end:]


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
    """Converge the runtime copy onto the repo's `base44/emails/**.html`,
    each held as `inbox_html` makes it. A template whose file is gone, or no
    longer compiles, is deleted: the next send answers the not-found message,
    which is the file-deleted state on Base44 (their read is live from the
    file tree)."""
    wanted: dict[str, str] = {}
    not_templates: list[str] = []
    for path, text in files.items():
        if not (path.startswith(ROOT) and path.endswith(".html")):
            continue
        name = path[len(ROOT):-len(".html")]
        body = inbox_html(text)
        if body is None:
            not_templates.append(name)
        else:
            wanted[name] = body
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

    return {
        "upserted": upserted,
        "removed": removed,
        "unchanged_count": unchanged,
        "not_templates": sorted(not_templates),
    }
