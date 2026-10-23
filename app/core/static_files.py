"""Static-files-first resolution against FRONTEND_DIR.

Shared by the HTML catch-all (main.py) and the SEO file routes (modules/seo):
a file the app ships in its build output — hashed assets, the standalone
login page, an app's OWN `public/manifest.json` / `robots.txt` — is served as
that file, before anything the backend would generate or has captured. That
is Base44's precedence (an app that ships its own manifest gets it served
directly; only apps without one get the generated manifest), and Vercel's
CDN and Caddy both behave the same way in front of this backend.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse


def try_serve_static(frontend_dir: str, request_path: str) -> FileResponse | None:
    """Resolve `request_path` against FRONTEND_DIR and return a FileResponse
    if a real file (or a `<dir>/index.html`) lives there. Returns None for
    `/` and `/index.html` — those route through the templating path so SEO
    head tags get injected per-request. The path-traversal guard rejects
    anything that resolves outside FRONTEND_DIR.
    """
    if request_path in ("/", "/index.html"):
        return None

    try:
        root = Path(frontend_dir).resolve()
        candidate = (root / request_path.lstrip("/")).resolve()
        # is_relative_to was added in 3.9 and is the standard guard against
        # `..`-style escapes.
        if not candidate.is_relative_to(root):
            return None
    except (OSError, ValueError):
        return None

    if candidate.is_file():
        return FileResponse(candidate)

    if candidate.is_dir():
        index = candidate / "index.html"
        if index.is_file():
            return FileResponse(index)

    return None
