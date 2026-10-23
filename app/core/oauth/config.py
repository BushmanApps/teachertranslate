"""ProviderConfig — the single piece of state passed around the OAuth helper.

Either explicit endpoints (authorization_endpoint + token_endpoint, plus
optionally userinfo_endpoint) OR server_metadata_url (OIDC discovery)
must be set. If both are set, explicit endpoints win — the helper does
not fetch metadata when it doesn't need to.

The authorize-request SHAPE is data too. Providers disagree on the name of
the client-id parameter (tiktok: client_key; wix: appId), the scope
parameter (slack user tokens: user_scope), how scopes are joined (meta /
slack: commas), which static extras ride along (google: access_type +
prompt; microsoft: response_mode + prompt; atlassian: audience + prompt;
notion: owner) and — for wix's app-installer — whether the standard OAuth2
trio (response_type + state + a redirect param) is sent at all. Base44's own
connector engine carries all of that per type in its config table (measured
on its dance for 80 of 82 types, 2026-09-02); the migrator seeds the same
fields onto `_connector_configs`, and the connectors module hands them here.
The login flows (google/microsoft sign-in) keep the OAuth2 defaults below.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    scope: str | list[str]

    # Explicit endpoints — use these if you have them.
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    # HTTP method to call userinfo_endpoint with. Most providers use GET;
    # a few (dropbox, wix) use POST.
    userinfo_method: str = "GET"

    # Or OIDC discovery — used when explicit endpoints aren't set.
    server_metadata_url: str | None = None

    # Authorize-request shape (see the module docstring).
    client_id_param: str = "client_id"
    redirect_uri_param: str = "redirect_uri"
    scope_param: str | None = "scope"  # None: the dance carries no scope parameter (Wix)
    scope_separator: str = " "
    authorize_standard_params: bool = True
    authorize_params: dict[str, str] = field(default_factory=dict)
    # Extra form fields the provider wants on the CODE-EXCHANGE request
    # (basecamp: type=web_server). Data from the provider catalog, seeded
    # per connector; the login flows send none.
    token_params: dict[str, str] = field(default_factory=dict)
    # Where the token sits in the provider's answer when it is not at the
    # top level — a dotted path (Slack's `authed_user`: a user-scope install
    # answers `{ok, authed_user: {access_token, scope, …}}` with no top-level
    # access_token). The catalog's own semantics (Nango's
    # alternate_access_token_response_path): the object at the path is read
    # as the token only when the top-level access_token is absent. None for
    # every provider whose token is where RFC 6749 puts it; the login flows
    # never set it.
    token_path: str | None = None
    # How a confidential client authenticates at the token endpoint when the
    # provider insists on one method (`basic` — docusign; `body`); None =
    # either, tried in the RFC's order. Catalog data.
    token_request_auth_method: str | None = None
    # A refresh endpoint other than the token endpoint (Instagram), resolved
    # from the same template shape as the token endpoint; None = the token
    # endpoint refreshes. And the extra fields the refresh request carries
    # beyond the protocol's own (`grant_type` stays the protocol's).
    refresh_endpoint: str | None = None
    refresh_params: dict[str, str] = field(default_factory=dict)
    # How the token is obtained. `authorization_code`: the callback carries
    # a code, exchanged (and later refreshed) per RFC 6749. `client_credentials`:
    # an installed-instance grant (Wix) — the callback carries the instance's
    # id under `callback_instance_param` plus its signature under
    # `callback_signature_param` (HMAC-SHA256 with the client secret); the
    # token is minted from client id + secret + instance id, has no refresh
    # token, and is minted again on expiry. `token_request_format` is the
    # body encoding that endpoint wants (Wix: JSON).
    token_grant: str = "authorization_code"
    token_request_format: str = "form"
    callback_instance_param: str | None = None
    callback_signature_param: str | None = None

    def scope_str(self) -> str:
        if isinstance(self.scope, str):
            return self.scope
        return self.scope_separator.join(self.scope)
