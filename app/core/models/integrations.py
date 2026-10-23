"""Integrations Core/* request models.

All integration endpoints use **envelope #3** for body validation failures
(D-005 + findings L2222-2240): manual `Model(**body)` + `try/except
ValidationError` + `AppHTTPException(422, message=str(detail_dict),
detail=detail_dict)` where `detail` is a dict. The wrapper lives in
`app/modules/integrations/helpers.py:validate_body`.

The model names are core/llm_models.py's (one table, derived from Base44).
`InvokeLLMRequest.model` uses `@field_validator` raising `ValueError`,
NOT `Literal[...]` — the wire error type must be `value_error`, not
`literal_error` (probe-locked, own-probes §7). The exact error message
format is also probe-locked; see `validate_model` below.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core import llm_models


class InvokeLLMRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str
    model: Optional[str] = None
    add_context_from_internet: bool = False
    response_json_schema: Optional[dict] = None
    file_urls: Optional[list[str]] = None

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v == "default":
            # Same-decisions: Base44 normalizes "default" -> "automatic"
            # before validation, so the user never sees it rejected.
            return "automatic"
        if v not in llm_models.ACCEPTED:
            # The message lists the REPORTED names only — Base44 accepts more
            # than it lists (core/llm_models.py).
            valid_str = ", ".join(f"'{m}'" for m in llm_models.REPORTED)
            # `raise ValueError(...)` is correct: Pydantic 2 auto-prefixes
            # the wire `msg` with "Value error, " — Base44's probe-locked
            # output INCLUDES that prefix (own-probes §7). Don't use
            # PydanticCustomError here — that path strips the prefix and
            # wire-diverges.
            raise ValueError(f"Invalid model '{v}'. Valid options are: {valid_str}")
        return v


class GenerateImageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str
    # Reference images: "edit one of them, match the style of a reference, or
    # give the AI visual context" (Base44's docs). Wire-leaked 2026-09-17 on a
    # deployed app: `list_type` on a non-list, `string_type` at index N on a
    # non-string item, `null` and `[]` accepted. What the handler does with
    # the entries is measured in generate_image.py.
    existing_image_urls: Optional[list[str]] = None


# Base44's GenerateVideo, wire-leaked 2026-09-17 (research/divergence-chasing/
# 2026-09-17-generate-video/). The three optional fields are exactly Google
# Veo 3.1's own parameter set, and the defaults are what a bare `{prompt}`
# call produced: a 6-second, 1280x720 (16:9), 24 fps h264 clip with a real
# AAC track. `null` is REJECTED on all three (they are not Optional at
# Base44), `"6"` is rejected while `6.0` passes (pydantic's own literal
# rules — the fork runs the same pydantic, so the same answers fall out),
# and `generate_audio` takes pydantic's lax booleans ("yes", "true", 1).
class GenerateVideoRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str
    duration: Literal[4, 6, 8] = 6
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    generate_audio: bool = True


# Base44's TranscribeAudio, wire-leaked 2026-09-17 (research/divergence-chasing/
# 2026-09-17-speech-transcribe-upload-push/): one required string. Everything
# else it checks lives in the handler (URL shape, the extension list).
class TranscribeAudioRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    audio_url: str


# Base44's GenerateSpeech, wire-leaked 2026-09-17 (same chase). The three
# refusals are field validators at Base44 (the `Value error, ` prefix and the
# ValueError in `ctx`), with these exact words; whitespace-only text is empty,
# the cap is 5,000 characters, the voice set is closed and case-sensitive
# (`River` is unknown) and listed alphabetically; `river` is the default
# (their docs — a bare `{text}` call succeeds).
SPEECH_VOICES = ("honey", "river", "spark", "storm", "sunny")
SPEECH_MAX_CHARS = 5000


class GenerateSpeechRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    voice: str = "river"

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Text cannot be empty.")
        if len(v) > SPEECH_MAX_CHARS:
            raise ValueError(f"Text is too long. Maximum {SPEECH_MAX_CHARS} characters allowed.")
        return v

    @field_validator("voice")
    @classmethod
    def validate_voice(cls, v: str) -> str:
        if v not in SPEECH_VOICES:
            raise ValueError(f"Unknown voice '{v}'. Available voices: {', '.join(SPEECH_VOICES)}.")
        return v


# SendEmail as Base44 serves it since its rebuild (measured 2026-09-28/29,
# ~250 requests and the mail they produced — the parity audit's session file
# has every case). Every rule below answers in the order Base44's answers,
# each neighbouring pair measured.
EMAIL_ATTACHMENT_TYPES = ("csv", "docx", "gif", "ics", "jpeg", "jpg", "md", "pdf", "png", "txt", "webp", "xlsx")
EMAIL_ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024
EMAIL_ATTACHMENTS_MAX_BYTES = 10 * 1024 * 1024
# The model judges a base64 attachment's size by the string's length, before
# anything is decoded: 6,990,510 characters pass and 6,990,511 do not (the
# handler then measures the decoded bytes exactly).
_EMAIL_ATTACHMENT_MAX_BASE64 = EMAIL_ATTACHMENT_MAX_BYTES * 4 // 3 + 4


class EmailAttachment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    filename: str
    file_url: Optional[str] = None
    content: Optional[str] = None

    @model_validator(mode="after")
    def _one_source_a_name_a_type_a_size(self):
        if (self.file_url is None) == (self.content is None):
            raise ValueError("each attachment needs exactly one of 'file_url' or 'content'")
        # The name is its last path segment, trimmed — what the mail carries
        # and what every later message calls it.
        self.filename = re.split(r"[/\\]", self.filename.strip())[-1]
        if not self.filename:
            raise ValueError("attachment 'filename' must not be empty")
        if self.extension not in EMAIL_ATTACHMENT_TYPES:
            raise ValueError(
                f"attachment '{self.filename}' has an unsupported type. "
                f"Supported: {', '.join(EMAIL_ATTACHMENT_TYPES)}"
            )
        if self.content is not None and len(self.content) > _EMAIL_ATTACHMENT_MAX_BASE64:
            raise ValueError(f"attachment '{self.filename}' exceeds the 5 MB limit")
        return self

    @property
    def extension(self) -> str:
        return self.filename.rpartition(".")[2].lower() if "." in self.filename else ""


class SendEmailRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    to: str
    subject: Optional[str] = None
    body: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    variables: Optional[dict] = None
    from_name: Optional[str] = None
    attachments: Optional[list[EmailAttachment]] = Field(default=None, max_length=5)

    @model_validator(mode="after")
    def _one_content(self):
        # What counts as given differs per field, as measured: a `body` is
        # given when it is there at all (an empty one too); `html` and
        # `text` when they hold more than whitespace; a template when its
        # name or id is not the empty string.
        body = self.body is not None
        html = bool(self.html and self.html.strip())
        text = bool(self.text and self.text.strip())
        template = bool(self.template_id or self.template_name)
        if body and html:
            raise ValueError("SendEmail accepts only one of 'body' or 'html', not both")
        if self.template_id and self.template_name:
            raise ValueError("SendEmail accepts only one of 'template_id' or 'template_name', not both")
        if template and (body or html):
            raise ValueError("SendEmail accepts a 'body' only when neither 'template_id' nor 'template_name' is set")
        if template and text:
            raise ValueError(
                "SendEmail does not support 'text' with a template yet \u2014 send 'html' and 'text' together instead"
            )
        if not (body or html or text or template):
            raise ValueError("SendEmail requires a 'body' / 'html', a 'text', or a 'template_id' / 'template_name'")
        if not template and not (self.subject and self.subject.strip()):
            raise ValueError("SendEmail requires a 'subject' unless it sends a template")
        return self


class SendPushNotificationRequest(BaseModel):
    """Base44's SendPushNotification body (measured 2026-09-17: the three
    required fields, min 1; extras ignored). The maxima are Base44's
    documented limits — the 422 they produce is pydantic's `string_too_long`,
    the shape every measured Core 422 has."""

    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=500)
    action_label: Optional[str] = Field(default=None, max_length=50)
    action_url: Optional[str] = None


class CreateFileSignedUrlRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file_uri: str
    expires_in: Optional[int] = None


class ExtractDataFromUploadedFileRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file_url: str
    json_schema: dict
