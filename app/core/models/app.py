"""App-document models — `RuntimeApp` and every nested model it composes.

`RuntimeApp` is the read-model served by `GET /api/apps/public/prod/by-id/{appId}`
and the `runtime/users/invite-user` success response. It is NOT `UserApp`
(the full management-side model with 88 fields, `extra='forbid'`) — Base44's
runtime surface ignores 22 dashboard-only fields and adds 3 deployment-runtime
ones. We never expose `UserApp` directly because `PUT /api/apps/{id}` is a
platform endpoint.

Field declaration order is verbatim from probe-locked findings (see
`own-probes/2026-05-18-locking-probes.md` §6 and findings.md L536-588).

`BackendFunctionsRuntime` and `BackendFunctionMetadata` are defined here for
typed-access by internal automation code that reads `_app_settings.backend_project`
and `_app_settings.backend_function_metadata`. They are NOT directly referenced
by `RuntimeApp` (which uses `dict` for `backend_function_metadata` since the
wire shape is just a passthrough map).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuthConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enable_username_password: bool = False
    enable_google_login: bool = False
    enable_microsoft_login: bool = False
    enable_facebook_login: bool = False
    enable_apple_login: bool = False
    sso_provider_name: Optional[str] = None
    enable_sso_login: bool = False
    sso_pkce_enabled: bool = True
    sso_include_offline_access: bool = True
    sso_use_custom_domain_callback: bool = False
    google_oauth_mode: Literal["default", "custom"] = "default"
    google_oauth_client_id: Optional[str] = None
    use_workspace_sso: bool = False


class ToolsPermissionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    auto_approved_operations: list = Field(default_factory=list)
    connector_guards: dict = Field(default_factory=dict)


class MigrationInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    migrated_to_sandbox: bool = False
    pre_migration_checkpoint_id: Optional[str] = None
    bonus_credits_granted: bool = False
    migration_in_progress: bool = False
    migration_started_at: Optional[datetime] = None
    migrated_date: Optional[datetime] = None
    reverted_date: Optional[datetime] = None


class BackendFunctionMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    entry: Optional[str] = None
    files: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    version: Optional[str] = None
    deno_app_id: Optional[str] = None
    deno_app_slug: Optional[str] = None


class BackendFunctionsRuntime(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app_id: str
    deployment_name_to_info: dict[str, BackendFunctionMetadata] = Field(default_factory=dict)
    layer_id: Optional[str] = None
    project_id: str
    project_name: str


class Conversation(BaseModel):
    """The `UserApp.conversation` sub-model. NOT `AgentConversation` from the
    agents module — same concept name in two places. This one lives in
    `_app_settings.conversation`.
    """

    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    messages: list = Field(default_factory=list)
    model: Optional[str] = None
    window_start_message_id: Optional[str] = None


class StatusObject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state: Literal["ready", "processing", "error"]
    details: Optional[str] = None
    request_id: Optional[str] = None
    last_updated_date: Optional[datetime] = None


class DiscoveredRoutes(BaseModel):
    model_config = ConfigDict(extra="ignore")

    routes: list = Field(default_factory=list)


# The app's record as its public routes answer it: a PROJECTION of the stored
# `_app_settings` document (Base44's own record, as the migration captured
# it), never a judgment of it. So a field takes every kind of value the fleet's
# records hold for it — `scripts/check-app-record.py` holds this model against
# the kinds counted over every readable app record (2026-09-29: 387), because a
# field typed stricter than the records answers 500 on the apps that hold the
# other kind (an app with no logo, no description, no layout: 36 of the 387).
# A null in the record is a null in the answer, as on Base44.
#
# Required (never absent, never null in any record): id, created_date,
# updated_date, organization_id, app_type, name, public_settings,
# git_remote_source, platform_version, slug, owner_id, app_stage,
# is_managed_source_code.
class RuntimeApp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    created_date: datetime
    updated_date: datetime
    organization_id: str
    app_type: str
    name: str
    user_description: Optional[str] = None
    logo_url: Optional[str] = None
    social_image_url: Optional[str] = None
    avatar_index: Optional[int] = None
    pages: dict = Field(default_factory=dict)
    page_names: list = Field(default_factory=list)
    discovered_routes: Optional[DiscoveredRoutes] = None
    components: dict = Field(default_factory=dict)
    layout: Optional[str] = ""
    globals_css: Optional[str] = ""
    entities: dict = Field(default_factory=dict)
    additional_user_data_schema: Optional[dict] = None
    agents: dict = Field(default_factory=dict)
    agents_enabled: bool = False
    backend_function_metadata: dict = Field(default_factory=dict)
    public_settings: Literal[
        "private_with_login",
        "public_with_login",
        "public_without_login",
        "workspace_with_login",
    ]
    custom_auth_enrolled: bool = False
    main_page: Optional[str] = ""
    auth_config: Optional[AuthConfiguration] = None
    enable_username_password: bool = False
    hide_entity_created_by: bool = False
    installable_integrations: dict = Field(default_factory=dict)
    installed_integration_context_items: list = Field(default_factory=list)
    payment_integrations: Optional[dict] = None
    seo_settings: Optional[dict] = None
    using_sandbox: bool = False
    captured_from: Optional[str] = None
    figma_source_url: Optional[str] = None
    last_git_commit_hash: Optional[str] = None
    git_remote_source: str
    has_unchained_ai: bool = False
    tools_permission_config: Optional[ToolsPermissionConfig] = None
    prevent_iframe_embedding: bool = False
    restrict_browser_features: bool = False
    platform_version: int
    github_repo_url: Optional[str] = None
    is_remixable: bool = False
    remixed_from_app_id: Optional[str] = None
    purchase_from_id: Optional[str] = None
    purchased_at: Optional[datetime] = None
    slug: str
    is_blocked: bool = False
    is_unpublished: bool = False
    last_deployed_at: Optional[datetime] = None
    last_deployed_checkpoint_id: Optional[str] = None
    screenshot_url: Optional[str] = None
    screenshot_updated_at: Optional[datetime] = None
    entities_agents_jsonc_synced_at: Optional[datetime] = None
    created_by_id: Optional[str] = None
    owner_id: str
    wix_metasite_id: Optional[str] = None
    app_stage: Literal["pending", "ready"]
    is_managed_source_code: bool
    has_non_prod_entities: bool = False
    is_deleted: bool = False
    deleted_date: Optional[datetime] = None
    migration_context: Optional[Any] = None   # null on every record but one, which holds an object
    data_region: Optional[str] = None
    function_names: list[str] = Field(default_factory=list)
    user_entity: Optional[dict] = None
    has_backend_functions_enabled: bool = False
    is_private: bool = False
    has_active_migration: bool = False
    backend_deployment_ids: dict = Field(default_factory=dict)
    backend_deno_app_slugs: dict = Field(default_factory=dict)
    snapshot_id: Optional[str] = None
