"""
Shared proxy logic for function runtime routes.

All three route families (invoke, fetch, alias) use the same core flow:
1. Look up function by name in _function_configs
2. Inject runtime headers
3. Forward request to deployed function URL
4. Forward response back transparently (with SSE streaming support)
"""

import os

import httpx
from fastapi import Request
from fastapi.responses import Response, StreamingResponse

from app.config import Settings
from app.core import addresses
from app.core import db
from app.core.errors import AppHTTPException
from app.core.functions.service_token import mint, mint_state_token, validate_state_token

_HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})

# What Base44 puts on a function call itself, overwriting whatever the caller
# sent under the same name — measured 2026-11-03 on an echo function on Base44
# (research/divergence-chasing/2026-11-03-function-call-headers/): a forged
# X-Base44-App-Url, Base44-App-Id, Base44-Api-Url, Base44-Service-Authorization,
# Base44-Function-Name, Base44-Functions-Version or X-Base44-Caller-User-Agent
# reached the function as the platform's value only; a forged Base44-State and
# an X-Data-Env did not reach it at all. A caller's copy dropped here would
# otherwise arrive NEXT to ours, and the function would read both values
# joined ("https://evil.example, https://<app>"). The workflow and automation
# markers (x-workflow-run, base44-*-automation, base44-scheduled-task) are NOT
# in the set: Base44 passes a caller's through, and so does this proxy.
# `base44-state` is handled on its own (a valid one is re-minted, below).
_PLATFORM_SET = frozenset({
    "base44-app-id", "base44-api-url", "base44-service-authorization",
    "base44-function-name", "base44-functions-version", "x-base44-app-url",
    "x-base44-caller-user-agent", "base44-state", "x-data-env",
})


async def lookup_function(name: str) -> dict | None:
    # Dev override. Inside any dev environment (local `npm run dev` or the
    # EscapeBase44 vibecoder sandbox) this env var points at a local
    # supervisor that lazy-spawns one Deno process per function, so calls
    # route there instead of the deployed function URL. The var is never set
    # in production — this is a no-op for every real deploy.
    # `VIBECODER_DEV_FUNCTIONS_BASE_URL` is the legacy name; existing
    # sandboxes still set it. New ones set `ESCAPEBASE44_DEV_FUNCTIONS_BASE_URL`.
    dev_base = (
        os.environ.get("ESCAPEBASE44_DEV_FUNCTIONS_BASE_URL")
        or os.environ.get("VIBECODER_DEV_FUNCTIONS_BASE_URL")
    )
    if dev_base:
        return {"name": name, "deployed_url": f"{dev_base.rstrip('/')}/{name}"}

    return await db.coll("_function_configs").find_one({"name": name})


async def _build_runtime_headers_from_dict(
    caller_headers: dict, settings: Settings, function_name: str, *, http_invoke: bool
) -> dict:
    """Build runtime headers from an explicit headers dict (no Request needed).

    `function_name` is the function being invoked — embedded into the service
    JWT as `backend_function_name` (production parity, see service_token.mint)
    and handed over as `base44-function-name`, as Base44 does on every call
    kind. `http_invoke` is a call that came in over HTTP (the SDK, a webhook,
    a fetch); False is the agent loop calling a function as a tool.

    Every name is written lowercase, so a header the platform sets can never
    sit next to a caller's copy that differs only in case.
    """
    # Base44 hands functions the ARRIVAL address (measured: the same function
    # sees a different Base44-Api-Url per host it was invoked through). The
    # caller's own Host/X-Forwarded-* headers carry it; a synthetic offline
    # caller (the channel relay) has none and resolves to the canonical.
    api_url = await addresses.arrival_base_url_from_headers(caller_headers)

    headers = {}
    for key, value in caller_headers.items():
        lower = key.lower()
        if lower in ("host", "content-length", "accept-encoding") or lower in _HOP_BY_HOP or lower in _PLATFORM_SET:
            continue
        headers[lower] = value
    # Accept-Encoding is the proxy's own to negotiate, never the caller's: the
    # upstream body is relayed DECODED (httpx transparently decodes what it
    # asked for; _filter_response_headers drops content-encoding), so an
    # encoding forwarded from the caller that httpx cannot decode reaches the
    # caller as raw bytes with no header. Measured 2026-09-03 on functions on
    # the box: the edge-runtime honours a browser's `br` and the client got
    # Brotli garbage — Supabase's gateway had simply never chosen `br`.

    headers["base44-app-id"] = settings.APP_ID
    headers["base44-api-url"] = api_url
    headers["base44-service-authorization"] = f"Bearer {mint(settings, function_name=function_name)}"
    headers["base44-function-name"] = function_name
    if http_invoke:
        # The app's address as the platform knows it, never the caller's Origin:
        # the arrival origin, validated (an attached custom domain, the eb44
        # address, the canonical for a host the app doesn't know). Measured on
        # Base44, equal to Base44-Api-Url on every call (the app's own host, its
        # preview host) whatever Origin or X-Origin-URL the caller sent; and on a
        # live app's checkout: "https://teachertranslate.com.au" on its custom
        # domain. Base44's captured workflow, automation and agent-tool calls
        # carry none.
        headers["x-base44-app-url"] = api_url
        # "prod" on every measured HTTP invoke, a caller's "draft" overwritten.
        # (Absent when the caller is the app's signed-in owner — the one call
        # Base44 runs on the editor's functions; this backend has one version,
        # and nothing here reads the header, so it is not told apart.)
        headers["base44-functions-version"] = "prod"
        # Base44 calls the function as itself and hands it the caller's agent.
        caller_agent = addresses.header_value(caller_headers, "user-agent")
        headers["user-agent"] = "Base44-Backend"
        if caller_agent:
            headers["x-base44-caller-user-agent"] = caller_agent

    incoming_state = addresses.header_value(caller_headers, "base44-state")
    if incoming_state and validate_state_token(incoming_state, settings):
        headers["base44-state"] = mint_state_token(settings)

    return headers


async def build_runtime_headers(request: Request, settings: Settings, function_name: str) -> dict:
    caller_headers = dict(request.headers)
    return await _build_runtime_headers_from_dict(caller_headers, settings, function_name, http_invoke=True)


async def proxy_to_function(
    request: Request,
    function_name: str,
    settings: Settings,
) -> Response:
    config = await lookup_function(function_name)
    if not config or not config.get("deployed_url"):
        raise AppHTTPException(
            404,
            f"Backend function '{function_name}' not found or not deployed",
        )

    deployed_url = config["deployed_url"].rstrip("/") + "/"
    headers = await build_runtime_headers(request, settings, function_name)
    body = await request.body()

    query_string = str(request.url.query) if request.url.query else ""
    target_url = deployed_url
    if query_string:
        target_url = f"{deployed_url}?{query_string}"

    try:
        client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0))
        try:
            upstream = await client.send(
                client.build_request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                ),
                stream=True,
            )

            content_type = upstream.headers.get("content-type", "")

            if "text/event-stream" in content_type:
                return StreamingResponse(
                    _stream_sse(upstream, client),
                    status_code=upstream.status_code,
                    headers=_filter_response_headers(upstream.headers),
                    media_type=None,
                )

            response_body = await upstream.aread()
            await upstream.aclose()
            await client.aclose()

            return Response(
                content=response_body,
                status_code=upstream.status_code,
                headers=_filter_response_headers(upstream.headers),
            )
        except Exception:
            await client.aclose()
            raise

    except httpx.TimeoutException:
        return Response(content="Timeout", status_code=504, media_type="text/plain")
    except httpx.HTTPError:
        return Response(
            content="Internal Server Error",
            status_code=500,
            media_type="text/plain; charset=utf-8",
        )


async def _stream_sse(upstream: httpx.Response, client: httpx.AsyncClient):
    try:
        async for chunk in upstream.aiter_bytes():
            yield chunk
    finally:
        await upstream.aclose()
        await client.aclose()


def _filter_response_headers(headers: httpx.Headers) -> dict:
    result = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in _HOP_BY_HOP or lower == "content-encoding" or lower == "content-length":
            continue
        result[key] = value
    return result


async def invoke_function(
    function_name: str,
    method: str,
    body: bytes,
    caller_headers: dict,
    settings: Settings,
    query_string: str = "",
) -> tuple[int, bytes, dict]:
    """Invoke a deployed function and return (status_code, response_body, response_headers).

    Does NOT handle streaming. For SSE streaming, use proxy_to_function.
    """
    config = await lookup_function(function_name)
    if not config or not config.get("deployed_url"):
        raise AppHTTPException(404, f"Backend function '{function_name}' not found or not deployed")

    deployed_url = config["deployed_url"].rstrip("/") + "/"
    headers = await _build_runtime_headers_from_dict(caller_headers, settings, function_name, http_invoke=False)

    target_url = deployed_url
    if query_string:
        target_url = f"{deployed_url}?{query_string}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
            resp = await client.request(method=method, url=target_url, headers=headers, content=body)
            return resp.status_code, resp.content, dict(resp.headers)
    except httpx.TimeoutException:
        return 504, b"Timeout", {"content-type": "text/plain"}
    except httpx.HTTPError:
        return 500, b"Internal Server Error", {"content-type": "text/plain; charset=utf-8"}
