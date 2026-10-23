"""The owner's URL redirect rules — the 301s Base44 answers on the app's published site.

The rules ride the app's settings (`eb44_url_redirects`: `source_path`,
`target_path`, `match_type` each), written by the migration from Base44's own
list. What answers them is Base44's contract, measured 2026-09-29 (probe 40
of research/divergence-chasing/2026-09-28-parity-audit):

- a GET or a HEAD of a path a rule names answers 301 with the rule's target
  in `Location`, `Cache-Control: max-age=300, must-revalidate` and no body;
- the path is matched as Base44 stores a rule's: percent-escapes decoded, a
  trailing slash dropped, the case as written;
- a `single` rule answers its own path; a `prefix` rule its own path and
  every path under it (a whole segment: `/old-blogger` is not under
  `/old-blog`), the rest of the path kept;
- the visitor's query is carried over as it came;
- a target is a path of the app or an `https://` address elsewhere;
- a path with a `;` in it is redirected by no rule, and what follows a `#`
  (an escaped one: a browser sends none) is dropped with the query after it.

Rules never overlap and never chain — Base44 refuses to store one that would
— so the first rule that matches is the only one.
"""

from __future__ import annotations

from urllib.parse import quote

CACHE_CONTROL = "max-age=300, must-revalidate"
# What a Location carries as it is; a space and anything beyond ASCII are escaped.
_AS_IT_IS = ":/%#?=@[]!$&'()*+,;"


def redirect_location(rules: list[dict], path: str, query: str) -> str | None:
    """Where a request for `path` (decoded, as the server hands it) is sent —
    or None when no rule names it."""
    if ";" in path or any(ord(char) < 32 for char in path):
        return None
    asked = path.rstrip("/") if len(path) > 1 else path
    for rule in rules:
        source = rule["source_path"]
        if asked == source:
            rest = ""
        elif rule.get("match_type") == "prefix" and asked.startswith(f"{source}/"):
            rest = asked[len(source):]
        else:
            continue
        target = f"{rule['target_path']}{rest}{f'?{query}' if query else ''}"
        return quote(target.split("#", 1)[0], safe=_AS_IT_IS)
    return None
