"""
Shared FastAPI dependencies.

Endpoint code declares these as function parameters with Depends().

For db, schema, security: import from app.core directly.
For providers and settings: use these Depends.
"""

from functools import lru_cache
from fastapi import Request

from app.config import Settings
from app.core import db


@lru_cache
def get_settings() -> Settings:
    return Settings()


async def get_app_settings() -> dict:
    return await db.app_settings()



def get_email_provider(request: Request):
    return request.app.state.email_provider


def get_storage_provider(request: Request):
    return request.app.state.storage_provider


async def resolve_on_behalf_of(request: Request) -> dict | None:
    """Resolve the user from the on-behalf-of header.

    Service role requests from the SDK include on-behalf-of: Bearer <user-token>
    to identify which user the service is acting for. Only specific endpoints
    (connectors, SSO) opt into this — the pipeline never touches it.

    Returns a serialized User dict, or None if the header is absent/invalid
    or the user doesn't exist.
    """
    header = request.headers.get("on-behalf-of")
    if not header:
        return None

    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    from app.core.security.tokens import try_decode_app_token
    from app.core import db
    from app.core.responses import serialize_entity

    settings = request.app.state.settings
    payload = try_decode_app_token(token, settings)
    if payload is None:
        return None

    email = payload.get("sub")
    if not isinstance(email, str):
        return None

    user = await db.coll("User").find_one({"email": email})
    if not user:
        return None

    return serialize_entity(user)
