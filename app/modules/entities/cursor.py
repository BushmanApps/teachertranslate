"""The cursor of a paged read: where the page ended, and what it was a page OF.

Base44's cursor is an opaque token a client hands back untouched (theirs is
encrypted). Ours is the same to a client: a signed token, readable by this
backend only. It carries the place (the last row's sort value and id, or the
last distinct value) and the read it belongs to — the entity, the filter, the
sort, the fields, the distinct field — because a cursor handed back with a
DIFFERENT read is refused, each difference by its own sentence (measured
2026-09-28; the answers are in a envelope of their own, `{"error": {"code":
"invalid_cursor", …}}`).

A parameter the request leaves out is taken from the cursor; one it names must
be the cursor's (measured 2026-09-29: a page asked for by its cursor alone is
the next page of the same read).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from bson import json_util
from fastapi.responses import JSONResponse

from app.deps import get_settings


class InvalidCursor(Exception):
    def __init__(self, message: str = "Invalid cursor"):
        self.message = message


def refusal(exc: InvalidCursor) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_cursor", "message": exc.message, "details": {}}},
    )


def _key() -> bytes:
    return hashlib.sha256(b"entity-cursor:" + get_settings().APP_JWT_SECRET.encode()).digest()


def filter_mark(query: dict) -> str:
    """The filter as a cursor remembers it: the same filter whatever the order
    its keys were written in."""
    return hashlib.sha256(json.dumps(query, sort_keys=True, default=str).encode()).hexdigest()[:24]


def issue(read: dict, place) -> str:
    body = json_util.dumps({"read": read, "place": place}, separators=(",", ":")).encode()
    signature = hmac.new(_key(), body, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(signature + body).decode().rstrip("=")


def open_(token: str) -> tuple[dict, object]:
    """The read and the place a token carries; `InvalidCursor` for anything
    this backend did not issue."""
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        signature, body = raw[:16], raw[16:]
        if len(signature) != 16 or not hmac.compare_digest(signature, hmac.new(_key(), body, hashlib.sha256).digest()[:16]):
            raise InvalidCursor()
        carried = json_util.loads(body.decode())
        return carried["read"], carried["place"]
    except InvalidCursor:
        raise
    except Exception:
        raise InvalidCursor() from None
