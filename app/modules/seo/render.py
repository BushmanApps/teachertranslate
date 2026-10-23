"""The head of a page, served the way Base44 served it.

The migration captured what Base44 serves for `/`, every page the app's record
names, and two probe paths no app has (`_seo_pages`, one document per page —
src/migration/seo/pages.ts). A request is matched to a captured page and the
captured tags are merged into the built `index.html`, with the visitor's path
put in — the one thing a capture cannot hold:

  - the page's own address (`og:url`, `twitter:url`, `canonical`): the arrival
    scheme+host and the request path decoded, its trailing slash dropped, the
    query kept; the root and the main page are the bare host;
  - the breadcrumb (`BreadcrumbList`): one item per segment of the request
    path — a known page's captured name, otherwise the segment with `-`/`_` as
    spaces; items are the cumulative encoded path, the last carries the query;
  - where Base44 names a page it does not know after its path (an app with no
    route scan — the probe's captured title says so — and the dash-free form
    of a page's name in any app): the last segment humanized, in the title
    tags and the snapshot's heading.

Base44 looks a page up twice, by two keys: the title and description by the
dashed, lowercased first segment (`/limits-probe`, `/LimitsProbe`), the
breadcrumb's name by the dash-free one (`/limitsprobe`, `/LIMITSPROBE` too).
Both lookups are kept as they are.

Measured on Base44 on 2026-09-29 (the parity audit's session file). Gates:
scripts/check-seo-serving.py, the battery's 43-seo-head.ts.
"""

from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import quote, unquote

from app.config import Settings
from app.core import db

# What Base44 makes of the probe's last segment when it names a page after its
# path — the migration's probe path is `/eb44-unknown-path/eb44-probe-page`.
PROBE_NAME = "Eb44 Probe Page"

FindOne = Callable[[dict], Awaitable[dict | None]]


def read_index_html(settings: Settings) -> str:
    """The built frontend's `index.html`, read from disk on every call.

    Deliberately never cached: a frontend-only redeploy replaces the dist
    files under the running process, and a memorized copy would keep
    referencing chunk hashes that no longer exist. Disk reads of a small
    file land in the OS page cache — freshness here is free.
    """
    path = Path(settings.FRONTEND_DIR) / "index.html"
    if not path.is_file():
        raise RuntimeError(
            f"FRONTEND_DIR/index.html not found at {path}. "
            "Set FRONTEND_DIR to the directory containing the built Vite output."
        )
    return path.read_text(encoding="utf-8")


# ── the two keys ───────────────────────────────────────────────────────────


def dashed(segment: str) -> str:
    """Base44's dashed form of a segment, as its own title-sync script spells it."""
    return re.sub(r"([A-Z])([A-Z][a-z])", r"\1-\2", re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", segment))


def page_key(segment: str) -> str:
    return dashed(segment).lower()


def crumb_key(segment: str) -> str:
    return re.sub(r"[-_]", "", segment.lower())


def humanized(segment: str) -> str:
    """`BarBaz2` → `Bar Baz2`, `abc-DEF_ghi` → `Abc DEF Ghi`, `some page` → `Some Page`, `über` → `Über`."""
    return " ".join(w[:1].upper() + w[1:] for w in re.split(r"[-_\s]+", dashed(segment)) if w)


def crumb_name(segment: str) -> str:
    return re.sub(r"[-_]+", " ", segment)


# ── which captured page answers a request ──────────────────────────────────


@dataclass(frozen=True)
class Match:
    # the captured page whose title, description and tags are served
    page: dict
    # the captured page whose name the first breadcrumb item carries (Base44's second lookup)
    crumb_page: dict | None
    root: bool
    # the request path's segments, decoded
    segments: list[str]
    # the app names a page it does not know after its path
    app_derives: bool
    # the title tags carry the last segment humanized
    derive: bool


async def page_for(path: str, find_one: FindOne | None = None) -> Match | None:
    """The captured page for a request path; None when nothing was captured
    (the app is then served exactly as built)."""
    if find_one is None:
        find_one = lambda query: db.coll("_seo_pages").find_one(query)  # noqa: E731
    root = await find_one({"keys": ""})
    if root is None:
        return None
    segments = [s for s in unquote(path).split("/") if s]
    probe_one = await find_one({"probe": "one"})
    app_derives = bool(probe_one and probe_one.get("derived"))
    if not segments:
        return Match(root, None, True, [], app_derives, False)
    first = segments[0]
    if len(segments) == 1 and (page_key(first) in root["keys"] or crumb_key(first) in root["crumb_keys"]):
        return Match(root, None, True, segments, app_derives, False)
    title_page = await find_one({"keys": page_key(first), "probe": None})
    crumb_page = await find_one({"crumb_keys": crumb_key(first), "probe": None})
    if title_page is not None:
        return Match(title_page, crumb_page, False, segments, app_derives, False)
    probe = probe_one if len(segments) == 1 else await find_one({"probe": "deep"})
    return Match(probe or root, crumb_page, False, segments, app_derives, app_derives or crumb_page is not None)


# ── the page, rendered ─────────────────────────────────────────────────────


def render_html(template: str, match: Match | None, *, query: str, base_url: str) -> tuple[str, dict[str, str]]:
    """The built `index.html` with the captured head merged in and the request's
    path put in; and the response headers the captured page carried."""
    if match is None:
        return template, {}
    page = match.page
    base = base_url.rstrip("/")
    url = base if match.root else f"{base}/{'/'.join(match.segments)}"
    if query:
        url = f"{url}?{query}"

    title = page.get("title")
    if match.derive and title is not None:
        last = humanized(match.segments[-1])
        title = title.replace(PROBE_NAME, last) if PROBE_NAME in title else f"{last} | {title}"

    tags: list[str] = []
    crumbs = _crumbs(match, base, query)
    placed_crumbs = False
    for tag in page.get("tags") or []:
        if _is_meta(tag, "property", "og:url") or _is_meta(tag, "name", "twitter:url") or _is_link(tag, "canonical"):
            tags.append(_with_attr(tag, "href" if _is_link(tag, "canonical") else "content", url))
        elif _is_breadcrumb(tag):
            if crumbs:
                tags.append(_breadcrumb_script(crumbs))
            placed_crumbs = True
        elif match.derive and title is not None and (_is_meta(tag, "property", "og:title") or _is_meta(tag, "name", "twitter:title")):
            tags.append(_with_attr(tag, "content", title))
        else:
            tags.append(tag)
    if crumbs and not placed_crumbs:
        tags.append(_breadcrumb_script(crumbs))

    html = template
    if title is not None:
        html = re.sub(r"<title\b[^>]*>[\s\S]*?</title>", lambda m: f"<title>{_esc(title)}</title>", html, count=1, flags=re.IGNORECASE)
    head = _head_of(html)
    kept: list[str] = []
    for tag in tags:
        if _is_link(tag, "icon") and _DEFAULT_ICON_RE.search(html):
            html = _DEFAULT_ICON_RE.sub(lambda m: tag, html, count=1)
            continue
        if _already_in(head, tag):
            continue
        kept.append(tag)
    if kept:
        html = _HEAD_CLOSE_RE.sub(lambda m: "\n".join(kept) + "\n" + m.group(0), html, count=1)

    snapshot = page.get("snapshot")
    if snapshot:
        if match.derive and title is not None:
            snapshot = re.sub(r"(<h1\b[^>]*>)[\s\S]*?(</h1>)", lambda m: f"{m.group(1)}{_esc(title)}{m.group(2)}", snapshot, count=1)
        html = _ROOT_DIV_RE.sub(lambda m: m.group(0) + snapshot, html, count=1)

    headers = {"X-Robots-Tag": page["robots"]} if page.get("robots") else {}
    return html, headers


def _crumbs(match: Match, base: str, query: str) -> list[tuple[str, str]]:
    """Base44's breadcrumb for this request: (name, item) per segment, or none.
    A known page gets one when the path is exactly the page; deeper paths and
    unknown ones get one only where the app names pages after their path (or
    the first segment is the dash-free form of a page's name)."""
    if match.root or not match.segments:
        return []
    known = match.page.get("probe") is None
    if known and len(match.segments) > 1 and not match.app_derives:
        return []
    if not known and not match.derive:
        return []
    items = [("Home", f"{base}/")]
    for i, segment in enumerate(match.segments):
        path = "/" + "/".join(quote(s) for s in match.segments[: i + 1])
        name = match.crumb_page.get("crumb_name") if i == 0 and match.crumb_page and match.crumb_page.get("crumb_name") else crumb_name(segment)
        items.append((name, f"{base}{path}"))
    if query:
        name, item = items[-1]
        items[-1] = (name, f"{item}?{query}")
    return items


def _breadcrumb_script(crumbs: list[tuple[str, str]]) -> str:
    schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": item} for i, (name, item) in enumerate(crumbs)
        ],
    }
    return f'<script data-seo-source="builder" type="application/ld+json">{json.dumps(schema, separators=(", ", ": "), ensure_ascii=False)}</script>'


# ── tag helpers ────────────────────────────────────────────────────────────

_DEFAULT_ICON_RE = re.compile(
    r'<link\s+rel="icon"\s+type="image/svg\+xml"\s+href="https://base44\.com/logo_v2\.svg"\s*/?\s*>'
)
_ROOT_DIV_RE = re.compile(r'<div\s+id="root"\s*>', re.IGNORECASE)
_HEAD_CLOSE_RE = re.compile(r"</head\s*>", re.IGNORECASE)


def _esc(value: object) -> str:
    return _html.escape(str(value), quote=True)


def _head_of(html: str) -> str:
    m = re.search(r"<head\b[^>]*>([\s\S]*?)</head>", html, re.IGNORECASE)
    return m.group(1) if m else ""


def _attr(tag: str, name: str) -> str | None:
    m = re.search(r"\b" + re.escape(name) + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", tag, re.IGNORECASE)
    return (m.group(1) if m.group(1) is not None else m.group(2)) if m else None


def _with_attr(tag: str, name: str, value: str) -> str:
    return re.sub(r"(\b" + re.escape(name) + r"\s*=\s*)(?:\"[^\"]*\"|'[^']*')", lambda m: f'{m.group(1)}"{_esc(value)}"', tag, count=1, flags=re.IGNORECASE)


def _is_meta(tag: str, attr: str, key: str) -> bool:
    return tag[:5].lower() == "<meta" and (_attr(tag, attr) or "").lower() == key


def _is_link(tag: str, rel: str) -> bool:
    return tag[:5].lower() == "<link" and (_attr(tag, "rel") or "").lower() == rel


def _is_breadcrumb(tag: str) -> bool:
    return tag[:7].lower() == "<script" and (_attr(tag, "type") or "").lower() == "application/ld+json" and '"BreadcrumbList"' in tag


def _already_in(head: str, tag: str) -> bool:
    """A tag the built head already carries by its own name — a meta by its
    charset, name or property, a link by its rel. (Base44's served head opens
    with `<meta charset="utf-8"/>` and the build's own head has one too; a
    document carries ONE.)"""
    if tag[:5].lower() == "<meta":
        if _attr(tag, "charset") is not None:
            return re.search(r"<meta\b[^>]*\bcharset\s*=", head, re.IGNORECASE) is not None
        for attr in ("name", "property"):
            key = _attr(tag, attr)
            if key and re.search(r"<meta\b[^>]*\b" + attr + r"\s*=\s*[\"']" + re.escape(key) + r"[\"']", head, re.IGNORECASE):
                return True
        return False
    if tag[:5].lower() == "<link":
        rel = _attr(tag, "rel")
        return bool(rel) and re.search(r"<link\b[^>]*\brel\s*=\s*[\"']" + re.escape(rel) + r"[\"']", head, re.IGNORECASE) is not None
    return False
