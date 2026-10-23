"""Auth-module request and response models.

Field types and strictness per IMPLEMENTOR.md L596-741 and the strictness
reference table L122-156. Every model uses `extra='ignore'` — Base44's auth
endpoints silently drop unknown body fields (D-005 + C-006).

`RegisterRequest.email` is plain `str` (not `EmailStr`) — Base44 emits
envelope #2 (`WrappedValidationError`) on bad email format, not envelope
#1's auto-FastAPI error. To produce envelope #2 we must validate the email
format MANUALLY in the handler (wrapping any `ValidationError` into
`WrappedValidationError`); declaring `email: EmailStr` here would route
through FastAPI's auto-422 → envelope #1. Empty / missing-email still
emits envelope #1 (auto-Pydantic catches `missing` before the handler
runs) — that matches Base44's wire shape too. Probe-verified 2026-05-19
against `auth/register` with `{"email":"nobody@example.invalid","password":"abcd1234"}`.

The `change-password` and `reset-password` success responses are the bare
UserResource shape — handlers return `users.UserResource(...).model_dump(...)`
directly, no wrapper.

`LoginResponse` IS a Pydantic class here, with `user: dict` rather than
`user: UserResource` — because `UserResource` is a dynamic per-app class
(rebuilt at lifespan from `_app_settings.additional_user_data_schema`) and
can't sit as a typed Pydantic field. The login handler pre-dumps the user
to a dict, then wraps in LoginResponse for consistency with the other
response Pydantic models in this file.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # NB: plain `str` (not `EmailStr`). See module docstring — email format
    # validation is performed manually in the register handler so failure
    # produces envelope #2 instead of envelope #1.
    email: str
    password: str
    turnstile_token: Optional[str] = None
    referral_code: Optional[str] = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str
    password: str
    turnstile_token: Optional[str] = None


class AppleNativeLoginRequest(BaseModel):
    """The wrapped iPhone app's Sign in with Apple result: the identity token
    Apple handed it, the nonce the app asked this backend for, and the name
    Apple shows the app once (never inside the token)."""

    model_config = ConfigDict(extra="ignore")

    identity_token: str
    nonce: str
    given_name: Optional[str] = None
    family_name: Optional[str] = None


class VerifyOTPRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str
    otp_code: str


class ResendOTPRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str


class ResetPasswordRequestBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str


class ResetPasswordBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reset_token: str
    new_password: str


class ChangePasswordBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: str
    current_password: str
    new_password: str


class InviteUserBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_email: str
    role: Optional[str] = None


class RegisterResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    message: str
    otp_expires_in_minutes: int
    country_code: str


class VerifyOTPResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    success: bool
    access_token: str
    message: str
    country_code: str


class ResendOTPResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str
    otp_expires_in_minutes: int


class ResetPasswordRequestResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # `user` is typed `dict`, not `UserResource`, because UserResource is a
    # per-app dynamic Pydantic class — the handler pre-dumps the user via
    # `users.UserResource(**input).model_dump(by_alias=True, exclude_unset=True)`
    # and passes the resulting dict here.
    user: dict
    success: bool
    access_token: str
    country_code: str


class SSOAccessTokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
