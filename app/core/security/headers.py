"""The security headers a response carries — Base44's, as measured.

Measured on a published Base44 app in the four states of its two switches
(2026-09-29, the parity audit's probe 30):

- every response carries `Referrer-Policy` and `Strict-Transport-Security`;
- a response that is an HTML document — the page, any client route, the
  login page, the page answered for a file that does not exist — adds
  `X-Content-Type-Options: nosniff` and what the app's switches ask for:
  `prevent_iframe_embedding` → `X-Frame-Options: DENY`,
  `restrict_browser_features` → `Permissions-Policy` (the list below);
- an API answer, a built asset, a redirect carry none of those three.

On Base44 a switch takes effect when the app is PUBLISHED; its editor's
preview is not the published app. Here the app that is not published is the
dev stack (`addresses.arrived_at_dev_stack`: a laptop, the builder's preview —
which shows the app inside a frame), and it gets no switch header.

A header the response already carries is left as it is: a backend function
that sets its own policy keeps it.
"""

from __future__ import annotations

from starlette.datastructures import Headers, MutableHeaders

from app.core import addresses, db

REFERRER_POLICY = "strict-origin-when-cross-origin"
STRICT_TRANSPORT_SECURITY = "max-age=31536000"
PERMISSIONS_POLICY = (
    "camera=(self), microphone=(self), geolocation=(self), payment=(self), "
    "usb=(self), magnetometer=(), gyroscope=()"
)


async def for_response(content_type: str, request_headers) -> dict[str, str]:
    """The headers of a response of this content type, to the request these headers came with."""
    headers = {
        "Referrer-Policy": REFERRER_POLICY,
        "Strict-Transport-Security": STRICT_TRANSPORT_SECURITY,
    }
    if content_type.split(";")[0].strip().lower() != "text/html":
        return headers
    headers["X-Content-Type-Options"] = "nosniff"
    if await addresses.arrived_at_dev_stack(request_headers):
        return headers
    app_settings = await db.app_settings()
    if app_settings.get("prevent_iframe_embedding"):
        headers["X-Frame-Options"] = "DENY"
    if app_settings.get("restrict_browser_features"):
        headers["Permissions-Policy"] = PERMISSIONS_POLICY
    return headers


class SecurityHeaders:
    """ASGI middleware: adds `for_response` to every HTTP response as it starts
    (a streamed answer included — nothing is buffered)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                response = MutableHeaders(scope=message)
                for name, value in (await for_response(response.get("content-type", ""), Headers(scope=scope))).items():
                    response.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)
