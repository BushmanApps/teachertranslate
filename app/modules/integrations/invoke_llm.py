"""POST /api/apps/:appId/integration-endpoints/Core/InvokeLLM"""

from __future__ import annotations

import base64
import json

import httpx
from fastapi import Body, Depends

from app.core.errors import AppHTTPException
from app.core.llm import WEB_SEARCH_COMPATIBLE, WEB_SEARCH_DEFAULT_ALIAS, get_llm_client, resolve_model, supports_web_grounding
from app.core.models import InvokeLLMRequest
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.core.storage_uri import resolve_storage_uri
from app.deps import get_app_settings, get_storage_provider
from app.modules.integrations.helpers import validate_body


def _normalize_file_urls(raw) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return raw
    return raw


async def invoke_llm(
    app_id: str,
    body: dict = Body(...),
    ctx: AuthedContext = Depends(get_authed_context),
    app_settings: dict = Depends(get_app_settings),
    storage=Depends(get_storage_provider),
):
    if "file_urls" in body:
        body["file_urls"] = _normalize_file_urls(body.get("file_urls"))

    req = validate_body(InvokeLLMRequest, body)

    if req.add_context_from_internet:
        model_for_check = req.model or "automatic"
        if model_for_check not in WEB_SEARCH_COMPATIBLE:
            # Verbatim Base44 2026-09-17 (one reported model now, so the old
            # set-iteration order wobble is gone).
            raise AppHTTPException(
                400,
                f"Model '{model_for_check}' does not support web search. "
                f"Compatible models: '{WEB_SEARCH_DEFAULT_ALIAS}'",
            )

    # Grounding exists only on the OpenRouter path (Gemini's googleSearch).
    # The OpenAI provider answers the same prompt ungrounded — the request is
    # still valid (the validation above ran), it just carries no search.
    grounded = req.add_context_from_internet and supports_web_grounding()

    if grounded and (req.model is None or req.model == "automatic"):
        model_name, resolved_alias = resolve_model(WEB_SEARCH_DEFAULT_ALIAS, app_settings)
    else:
        model_name, resolved_alias = resolve_model(req.model, app_settings)

    # No file-extension whitelist (probe-locked own-probes 2026-05-20):
    # Base44 accepts ANY extension in file_urls — csv/json/html/xlsx/docx/
    # mp3/mp4 and no-extension URLs all return 200. The LLM provider
    # downloads and handles content-type sniffing.

    messages = await _build_messages(req, storage)
    kwargs = _build_kwargs(req, model_name, grounded)

    # openai is the `llm` optional dependency; imported lazily so this module
    # loads on deploys without it. By the time we reach a live LLM call it's
    # installed (the migrator selects the `llm` extra whenever InvokeLLM is used).
    import openai

    client = get_llm_client()
    try:
        response = await client.chat.completions.create(messages=messages, **kwargs)
    except openai.BadRequestError as e:
        raise AppHTTPException(400, f"Invalid request to LLM: {e}")
    except Exception as e:
        status = getattr(e, "status_code", 500)
        inputs_summary = {"prompt": req.prompt[:100], "model": req.model}
        raise AppHTTPException(
            status,
            f"Error running integration. Error: {e}. integration: InvokeLLM. inputs: {inputs_summary}",
        )

    content = response.choices[0].message.content

    if req.response_json_schema:
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content
    return content


async def _file_content_part(url: str) -> dict:
    """Build the appropriate OpenAI-compat content part for a file URL.

    OpenRouter accepts file inputs differently depending on type:
      - Images (png/jpg/jpeg/gif/webp/etc) → `image_url` part with URL
        passes through (LLM provider fetches).
      - PDFs → `file` part requires `file_data` as a `data:` URL — passing
        a remote URL via `file_id` returns 400 "file_id is only supported
        for BYOK requests" (OpenAI) or "File data is missing" (Gemini).
        So we download the PDF and inline-encode it as base64.
      - Anything else → fall back to `image_url` (Base44's permissive
        behavior — D-INT-12 / probe-locked own-probes 2026-05-20).

    Base44 prod accepts mixed image+PDF in file_urls (probe-locked own-probes
    2026-05-21 / D-INT-32). Their handler inspects extension and constructs
    the right part per file; we mirror.
    """
    lower = url.split("?")[0].lower()
    if lower.endswith(".pdf"):
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            b64 = base64.b64encode(resp.content).decode("ascii")
        filename = lower.rsplit("/", 1)[-1] or "file.pdf"
        return {
            "type": "file",
            "file": {
                "filename": filename,
                "file_data": f"data:application/pdf;base64,{b64}",
            },
        }
    return {"type": "image_url", "image_url": {"url": url}}


async def _build_messages(req: InvokeLLMRequest, storage) -> list[dict]:
    if req.file_urls:
        content_parts: list[dict] = [{"type": "text", "text": req.prompt}]
        # Base44 resolves storage URIs (mp/private/..., private/..., mp/public/..., public/...)
        # to fetchable URLs before constructing the LLM message. We do the same so
        # user code that passes `entity.file_uri` directly into file_urls works
        # (own-probes 2026-05-21 / D-INT-26).
        for url in req.file_urls:
            resolved = await resolve_storage_uri(url, storage)
            content_parts.append(await _file_content_part(resolved))
        return [{"role": "user", "content": content_parts}]

    return [{"role": "user", "content": req.prompt}]


def _normalize_schema_for_openai_strict(schema: dict) -> dict:
    """OpenAI structured-outputs strict mode requires:
    - every key in `properties` listed in `required`
    - `additionalProperties: false` on every object
    Base44 accepts the same user schemas we do, so they must auto-augment
    server-side. We do the same — recursively walk and fix.
    """
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    if out.get("type") == "object" and "properties" in out:
        props = out["properties"]
        if isinstance(props, dict):
            out["properties"] = {k: _normalize_schema_for_openai_strict(v) for k, v in props.items()}
            out["required"] = list(props.keys())
            out["additionalProperties"] = False
    elif out.get("type") == "array" and "items" in out:
        out["items"] = _normalize_schema_for_openai_strict(out["items"])
    return out


def _build_kwargs(req: InvokeLLMRequest, model_name: str, grounded: bool) -> dict:
    kwargs: dict = {"model": model_name}

    if grounded:
        kwargs["tools"] = [{"googleSearch": {}}]

    if req.response_json_schema:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": _normalize_schema_for_openai_strict(req.response_json_schema),
            },
        }

    return kwargs
