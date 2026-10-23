"""Pydantic models mirroring Base44's wire shapes.

Each submodule defines models for one logical area. The convention:
- Model class names verbatim from Base44 (`RuntimeApp`, `UserResource`, ...).
- Field declaration order verbatim — `D-003` in DISCOVERIES.md says Base44
  emits GET responses in Pydantic declaration order.
- `model_config` per-model matching Base44's observed strictness mode.

See `research/pydantic-divergence/IMPLEMENTOR.md` for the source of truth
on every model's fields, types, and strictness.
"""

from app.core.models.app import (
    AuthConfiguration,
    BackendFunctionMetadata,
    BackendFunctionsRuntime,
    Conversation,
    DiscoveredRoutes,
    MigrationInfo,
    RuntimeApp,
    StatusObject,
    ToolsPermissionConfig,
)
from app.core.models.agents import (
    AddMessageBody,
    AgentConversation,
    ConversationSummary,
    CreateConversationBody,
    Message,
    MessageMetadata,
    ReasoningBlock,
    UpdateConversationBody,
    Usage,
)
from app.core.models.connectors import (
    InitiateAppBody,
    InitiateResponse,
    StatusResponse,
    TokenVendResponse,
)
from app.core.models.custom_integrations import RuntimeIntegrationBody
from app.core.models.integrations import (
    CreateFileSignedUrlRequest,
    ExtractDataFromUploadedFileRequest,
    GenerateImageRequest,
    GenerateSpeechRequest,
    GenerateVideoRequest,
    InvokeLLMRequest,
    SendEmailRequest,
    SendPushNotificationRequest,
    TranscribeAudioRequest,
)
from app.core.models.management import LoginInfoResponse, PublicSettingsResponse
from app.core.models.users import UserResource
# auth.py depends on users.UserResource — import last to avoid cycles.
from app.core.models.auth import (
    ChangePasswordBody,
    InviteUserBody,
    AppleNativeLoginRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    ResendOTPRequest,
    ResendOTPResponse,
    ResetPasswordBody,
    ResetPasswordRequestBody,
    ResetPasswordRequestResponse,
    SSOAccessTokenResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
)

__all__ = [
    "AddMessageBody",
    "AgentConversation",
    "AuthConfiguration",
    "BackendFunctionMetadata",
    "BackendFunctionsRuntime",
    "ChangePasswordBody",
    "Conversation",
    "ConversationSummary",
    "CreateConversationBody",
    "CreateFileSignedUrlRequest",
    "DiscoveredRoutes",
    "ExtractDataFromUploadedFileRequest",
    "GenerateImageRequest",
    "GenerateSpeechRequest",
    "GenerateVideoRequest",
    "InitiateAppBody",
    "InitiateResponse",
    "InviteUserBody",
    "InvokeLLMRequest",
    "LoginInfoResponse",
    "AppleNativeLoginRequest",
    "LoginRequest",
    "LoginResponse",
    "Message",
    "MessageMetadata",
    "MigrationInfo",
    "PublicSettingsResponse",
    "ReasoningBlock",
    "RegisterRequest",
    "RegisterResponse",
    "ResendOTPRequest",
    "ResendOTPResponse",
    "ResetPasswordBody",
    "ResetPasswordRequestBody",
    "ResetPasswordRequestResponse",
    "RuntimeApp",
    "RuntimeIntegrationBody",
    "SSOAccessTokenResponse",
    "SendEmailRequest",
    "SendPushNotificationRequest",
    "TranscribeAudioRequest",
    "StatusObject",
    "StatusResponse",
    "TokenVendResponse",
    "ToolsPermissionConfig",
    "UpdateConversationBody",
    "Usage",
    "UserResource",
    "VerifyOTPRequest",
    "VerifyOTPResponse",
]
