"""Management-module response models.

These are the wire shapes served by:
- `GET /api/apps/public/login-info/by-id/{appId}` → `LoginInfoResponse`
- `GET /api/apps/public/prod/public-settings/by-id/{appId}` → `PublicSettingsResponse`
- `GET /api/apps/public/prod/by-id/{appId}` → `RuntimeApp` (defined in app.py)

`LoginInfoResponse` field order is probe-verified (own-probes §1, findings L480-505).
`auth_config` is non-Optional — Base44 always emits a populated dict here on
every observed app. The migrator MUST seed `_app_settings.auth_config` as a
dict (empty dict is acceptable; `AuthConfiguration`'s fields all default).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.core.models.app import AuthConfiguration


# MIGRATOR_NOTE: _app_settings.auth_config must be a dict (never null, never
# missing). Empty dict is acceptable — AuthConfiguration's fields all default.
class LoginInfoResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    slug: str
    logo_url: Optional[str] = None
    user_description: Optional[str] = None
    updated_date: datetime
    created_date: datetime
    auth_config: AuthConfiguration
    platform_version: int
    last_deployed_at: Optional[datetime] = None
    is_unpublished: bool
    organization_id: str


class PublicSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    public_settings: Literal[
        "private_with_login",
        "public_with_login",
        "public_without_login",
        "workspace_with_login",
    ]
