"""OAuth2 / OIDC flow primitives.

Thin wrapper over authlib's AsyncOAuth2Client. The helper handles the
HTTP mechanics (authorize URL construction, code-for-token exchange,
refresh, userinfo). Everything else — state validation, nonce
validation, cookie/JWT issuance, user upsert — is the caller's job.
"""

from __future__ import annotations

import time

from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client

from app.core.oauth.config import ProviderConfig


async def _resolve_endpoints(config: ProviderConfig) -> None:
    """Populate endpoint fields from OIDC discovery, in place.

    Only fetches metadata when at least one needed endpoint is missing
    AND server_metadata_url is set. Explicit endpoints win.
    """
    if config.authorization_endpoint and config.token_endpoint and config.userinfo_endpoint:
        return
    if not config.server_metadata_url:
        return

    async with httpx.AsyncClient() as http:
        resp = await http.get(config.server_metadata_url)
        resp.raise_for_status()
        metadata = resp.json()

    if not config.authorization_endpoint:
        config.authorization_endpoint = metadata.get("authorization_endpoint")
    if not config.token_endpoint:
        config.token_endpoint = metadata.get("token_endpoint")
    if not config.userinfo_endpoint:
        config.userinfo_endpoint = metadata.get("userinfo_endpoint")


def build_authorize_url(
    config: ProviderConfig,
    state: str,
    nonce: str | None = None,
    **extra_params: str,
) -> str:
    """Construct the authorization URL the browser is redirected to.

    Requires `config.authorization_endpoint` to be populated. Callers
    using OIDC discovery must resolve the endpoint before calling this.

    The parameter SET is the provider's, read off the config (see
    ProviderConfig): the client-id and redirect parameter names, the scope
    parameter name + separator, the provider's static extras, and whether
    the standard OAuth2 trio is sent at all. An empty scope list sends no
    scope parameter (notion, github, box, … — Base44 sends none there), and
    neither does a dance with no scope parameter at all (`scope_param` None:
    Wix's installer — the app's permissions live on the app; Base44 keeps the
    connection's scopes and sends none).
    `extra_params` are per-dance additions the caller decides on (the PKCE
    challenge; the login flows' own prompt/access_type).

    A dance without the standard trio (wix's app-installer) has nowhere to
    carry `state`, so it rides the redirect parameter's query string — the
    callback reads it off the URL the provider sends the browser back to.

    Some providers' authorization_endpoint already carries a query string;
    detect that and use `&`.
    """
    params: dict[str, str] = {}
    if config.authorize_standard_params:
        params["response_type"] = "code"
        params[config.client_id_param] = config.client_id
        params[config.redirect_uri_param] = config.redirect_uri
        params["state"] = state
    else:
        params[config.client_id_param] = config.client_id
        params[config.redirect_uri_param] = f"{config.redirect_uri}?{urlencode({'state': state})}"
    scope = config.scope_str()
    if scope and config.scope_param:
        params[config.scope_param] = scope
    if nonce is not None:
        params["nonce"] = nonce
    params.update(config.authorize_params)
    params.update(extra_params)

    sep = "&" if "?" in config.authorization_endpoint else "?"
    return f"{config.authorization_endpoint}{sep}{urlencode(params)}"


async def _token_request_with_auth_fallback(config: ProviderConfig, do_request) -> dict:
    """Run a token-endpoint request, falling back across client-auth methods.

    Providers genuinely disagree on how a confidential client must
    authenticate at the token endpoint: RFC 6749 §2.3.1 makes HTTP Basic
    mandatory-to-support (notion-class providers accept ONLY that), while
    HubSpot-class providers accept ONLY client_id/client_secret as form-body
    parameters (their docs show no Basic variant at all). No metadata source
    declares which a provider wants — Composio's toolkit payload carries
    nothing — so this is external heterogeneity, not something we control.

    Order: `client_secret_basic` first (authlib's default and the RFC-first
    method — every surface that worked before this fallback existed keeps
    its exact previous behavior), retry once with `client_secret_post`.
    Safe for code exchange: a provider cannot attribute — let alone redeem —
    an authorization code before it has authenticated the client, so a
    client-auth rejection happens before code redemption and does not burn
    the single-use code.

    A PUBLIC client (no client secret — Base44 declares these per type:
    linear, posthog; PKCE is their proof of possession) authenticates with
    `none`: the client_id in the body and no Authorization header. An empty
    secret sent as Basic auth is what the provider rejects; there is nothing
    to fall back to.
    """
    if not config.client_secret:
        return await do_request("none")
    # A provider that insists on one method (catalog data — docusign: basic)
    # gets it first; the other is still the fallback, as ever.
    first, second = "client_secret_basic", "client_secret_post"
    if config.token_request_auth_method == "body":
        first, second = second, first
    try:
        return await do_request(first)
    except Exception:
        return await do_request(second)


def _client_auth(config: ProviderConfig, auth_method: str, body: dict) -> tuple[dict, tuple[str, str] | None]:
    """The body and the HTTP auth a token request carries for a client-auth
    method, for the requests authlib does not build (a JSON body)."""
    if auth_method == "client_secret_basic":
        return body, (config.client_id, config.client_secret)
    if auth_method == "client_secret_post":
        return {**body, "client_id": config.client_id, "client_secret": config.client_secret}, None
    return {**body, "client_id": config.client_id}, None


async def _post_token_json(config: ProviderConfig, auth_method: str, url: str, body: dict) -> dict:
    """A token request the endpoint wants as JSON (Notion) — authlib builds
    only form bodies. Same client-auth methods, same answer shape: the
    provider's dict with `expires_at` derived from `expires_in` the way
    authlib does; a non-2xx raises so the auth fallback can retry."""
    payload, auth = _client_auth(config, auth_method, body)
    async with httpx.AsyncClient(timeout=20.0) as http:
        resp = await http.post(url, json=payload, auth=auth, headers={"Accept": "application/json"})
    if resp.status_code >= 300:
        raise ValueError(f"token endpoint answered {resp.status_code}: {resp.text[:300]}")
    token = dict(resp.json())
    if "expires_in" in token and "expires_at" not in token:
        token["expires_at"] = time.time() + float(token["expires_in"])
    return token


def _token_at_path(token: dict, path: str | None) -> dict:
    """The token as the provider answered it — unless the top-level
    access_token is absent and the provider's contract names where it sits
    instead (`token_path`, a dotted path: Slack's `authed_user`). Then the
    object at that path is the token, laid over the provider's envelope so
    its access_token, refresh_token, expires_in and scope are the ones read
    (the catalog's own semantics for the field)."""
    if "access_token" in token or not path:
        return token
    inner: object = token
    for segment in path.split("."):
        inner = inner.get(segment) if isinstance(inner, dict) else None
    if isinstance(inner, dict) and "access_token" in inner:
        return {**token, **inner}
    if isinstance(inner, str):
        return {**token, "access_token": inner}
    return token


async def exchange_code_for_token(
    config: ProviderConfig, code: str, code_verifier: str | None = None
) -> dict:
    """Exchange an authorization code for tokens.

    Returns the full token dict from the provider — including access_token,
    refresh_token (if issued), expires_in, expires_at, token_type, scope,
    and id_token (for OIDC). Caller persists what it cares about.

    `code_verifier` (optional) rides the request as the PKCE verifier for
    dances whose authorize URL carried a code_challenge — the connectors
    module threads it from the pending row. Callers that never sent a
    challenge (the login flows) omit it and are byte-identical to before.
    """
    await _resolve_endpoints(config)
    _require_token_endpoint(config)

    async def do_request(auth_method: str) -> dict:
        # The provider's own extras first (catalog data — basecamp's
        # type=web_server), then the dance's PKCE verifier.
        extra = {**config.token_params, **({"code_verifier": code_verifier} if code_verifier else {})}
        if config.token_request_format == "json":
            token = await _post_token_json(
                config, auth_method, config.token_endpoint,
                {"grant_type": "authorization_code", "code": code, "redirect_uri": config.redirect_uri, **extra},
            )
        else:
            async with AsyncOAuth2Client(
                client_id=config.client_id,
                client_secret=config.client_secret,
                token_endpoint_auth_method=auth_method,
            ) as client:
                token = await client.fetch_token(
                    config.token_endpoint,
                    code=code,
                    redirect_uri=config.redirect_uri,
                    **extra,
                )
        return _token_at_path(dict(token), config.token_path)

    return await _token_request_with_auth_fallback(config, do_request)


async def mint_client_credentials_token(config: ProviderConfig, **extra: str) -> dict:
    """A token for an installed instance (Wix): no authorization code and no
    refresh token — client id + client secret + whatever names the instance
    (`instance_id`) mint a fresh one, and the caller mints again on expiry.
    The body goes as the endpoint wants it (`token_request_format`), with the
    provider's own extras first. Returns the token dict with `expires_at`
    derived from `expires_in` the way authlib does for the code grant."""
    _require_token_endpoint(config)
    body = {
        "grant_type": "client_credentials",
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        **config.token_params,
        **extra,
    }
    async with httpx.AsyncClient(timeout=20.0) as http:
        if config.token_request_format == "json":
            resp = await http.post(config.token_endpoint, json=body)
        else:
            resp = await http.post(config.token_endpoint, data=body)
    if resp.status_code >= 300:
        raise ValueError(f"token endpoint answered {resp.status_code}: {resp.text[:300]}")
    token = dict(resp.json())
    if "access_token" not in token:
        raise ValueError("token endpoint answered without an access_token")
    if "expires_in" in token and "expires_at" not in token:
        token["expires_at"] = time.time() + float(token["expires_in"])
    return token


def _require_token_endpoint(config: ProviderConfig) -> None:
    """A connector config's token endpoint is resolved per dance from
    templates the migrator seeded (a placeholder may only be fillable from
    the provider's callback — Zoho's `{accounts-server}`); when nothing
    resolved, say so instead of letting authlib fail on a None URL."""
    if not config.token_endpoint:
        raise ValueError("no token endpoint resolved for this connector dance")


async def refresh_access_token(config: ProviderConfig, refresh_token: str) -> dict:
    """Refresh an expired access token.

    Returns the full token dict — including a possibly-rotated refresh_token,
    which the caller must persist if present.
    """
    await _resolve_endpoints(config)
    _require_token_endpoint(config)
    # A provider that refreshes elsewhere (catalog data — Instagram) names
    # the endpoint; the rest refresh where they exchanged. The refresh
    # extras ride the body beside the protocol's own fields.
    endpoint = config.refresh_endpoint or config.token_endpoint

    async def do_request(auth_method: str) -> dict:
        if config.token_request_format == "json":
            token = await _post_token_json(
                config, auth_method, endpoint,
                {"grant_type": "refresh_token", "refresh_token": refresh_token, **config.refresh_params},
            )
        else:
            async with AsyncOAuth2Client(
                client_id=config.client_id,
                client_secret=config.client_secret,
                token_endpoint_auth_method=auth_method,
            ) as client:
                token = await client.refresh_token(
                    endpoint,
                    refresh_token=refresh_token,
                    **config.refresh_params,
                )
        return _token_at_path(dict(token), config.token_path)

    return await _token_request_with_auth_fallback(config, do_request)


async def fetch_userinfo(config: ProviderConfig, access_token: str) -> dict:
    """Fetch user info from the provider's userinfo endpoint.

    Method honored from `config.userinfo_method` — most providers use GET,
    but a few (dropbox, wix) require POST. Composio's toolkit metadata
    carries `get_current_user_endpoint_method` which the migrator seeds.
    """
    await _resolve_endpoints(config)

    method = (config.userinfo_method or "GET").upper()
    async with httpx.AsyncClient() as http:
        resp = await http.request(
            method,
            config.userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
