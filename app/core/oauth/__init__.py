"""OAuth2 / OIDC helper — shared mechanics for login and connectors.

The helper covers the HTTP dance: authorize URL construction, code exchange,
refresh, and userinfo fetch. Everything else (state validation, nonce
validation, cookies, JWTs, DB writes) is the caller's responsibility.
"""

from app.core.oauth.config import ProviderConfig
from app.core.oauth.flow import (
    build_authorize_url,
    exchange_code_for_token,
    fetch_userinfo,
    mint_client_credentials_token,
    refresh_access_token,
)
from app.core.oauth.signed_instance import verify_signed_instance

__all__ = [
    "ProviderConfig",
    "build_authorize_url",
    "exchange_code_for_token",
    "fetch_userinfo",
    "mint_client_credentials_token",
    "verify_signed_instance",
    "refresh_access_token",
]
