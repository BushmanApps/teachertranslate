"""Agents-module static models.

Probed against Base44 prod (2026-05-21/22 — `agent-parity-hub`):
- `AddMessageBody` is `extra="forbid"`, `content` is Optional (defaults to ""
  in storage), `additional_message_params` loosely typed, `reasoning` is
  Optional[ReasoningBlock] (not Union[str,...]).
- `AgentConversation.summary` is non-null on every observed conv — Base44
  stamps it at create with `{user_group_key: <created_by_id>, message_count: 0,
  credit_count: 0.0}` and updates on each message push.
- `UpdateConversationBody.metadata` is `dict` (not Optional) — null rejected
  with Pydantic envelope #1 `dict_type`.

`AgentConversation` is the agents-module conversation type — DIFFERENT from
`Conversation` (which is `UserApp.conversation` for the app-level chat
history). Same concept name in two places.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Max message content, in CODE POINTS (not bytes) — probe-locked and
# re-confirmed 2026-08-02: 100,000 accepted / 100,001 rejected on both sides,
# and 50,001 CJK characters (≈150 KB of UTF-8) accepted on both, which is what
# proves the unit. Lives here rather than in the router because Base44
# enforces it during body validation; see `AddMessageBody._content_rules`.
CONTENT_MAX_LENGTH = 100_000


class Usage(BaseModel):
    """Message-level usage shape. `prompt_tokens` and `completion_tokens`
    are REQUIRED (B44 returns 422 missing on those two when client sends
    `usage={}` — probed 2026-05-22). Other fields default to 0/null.

    The loop's `_coalesce_msg_usage` always provides both required fields,
    so the assistant-side serialization path is unaffected. The strictness
    matters only when a CLIENT sends `usage={...}` on AddMessageBody."""

    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int
    completion_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_5m_tokens: int = 0
    cache_creation_1h_tokens: int = 0
    reasoning_tokens: int = 0
    web_search_queries: int = 0
    credits_charged: Optional[float] = None
    tools_cost: Optional[float] = None


class ReasoningBlock(BaseModel):
    """Permissive parsing for user-supplied reasoning blocks — Base44 accepts
    `reasoning={}` and any partial shape, then stamps defaults. Probed
    2026-05-22:

    - `reasoning={}` → stored as `{start_date:<server-stamped now>, end_date:
      null, content:'', signature:null}`.
    - `reasoning={start_date:"2026-..."}` → stored with the supplied start_date
      plus `end_date:null, content:'', signature:null`.

    `start_date` is stamped server-side when missing — see the
    `_default_start_date` validator below. `end_date` is `Optional`
    because the loop emits reasoning-started events with `end_date=null`
    mid-stream; the HTTP response always has it populated.
    """

    model_config = ConfigDict(extra="ignore")

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    content: str = ""
    signature: Optional[str] = None

    @model_validator(mode="after")
    def _default_start_date(self) -> "ReasoningBlock":
        if self.start_date is None:
            # Match Base44's wire: when the client omits start_date (e.g.,
            # sends reasoning={}), the server stamps now() naively.
            self.start_date = datetime.utcnow()
        return self


class MessageMetadata(BaseModel):
    """Embedded message metadata.

    `created_date` is typed as `datetime` (NOT `str`) so that the
    just-created in-memory value retains microsecond precision while
    the Mongo round-trip truncates to millisecond — exactly matching
    Base44's POST-vs-GET asymmetry on the wire:

      POST /messages → `metadata.created_date: 2026-05-22T09:48:08.309912`
      GET  /conversations/{id} → `created_date: 2026-05-22T09:45:12.842000`

    Both naive (no `Z` suffix) because Mongo's BSON Date strips tz; the
    POST response keeps full precision because the just-stamped value
    hasn't gone through Mongo yet.

    Fields default to empty/anonymous so that AddMessageBody can declare
    `metadata: MessageMetadata = Field(default_factory=MessageMetadata)` —
    that typing rejects `metadata=null` natively with Pydantic's
    `model_attributes_type` 422 (matching Base44 wire — type, msg, and
    input are byte-identical) while still allowing metadata to be omitted.

    `from_attributes=True` is what triggers the `model_attributes_type`
    error code specifically (without it, you get `model_type`). Same
    decision as Base44 — they're using attribute-extraction-capable
    pydantic models, so the error code matches naturally.
    """

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    # Naive-UTC sentinel for the omitted-metadata case. The router stamps
    # `datetime.utcnow()` when the client omits metadata; this default just
    # has to be a valid datetime so `MessageMetadata()` constructs cleanly.
    # created_date + created_by_email are REQUIRED when the client supplies a
    # `metadata` object at all — measured 2026-08-02: `metadata: {}` returns
    # exactly two `missing` errors, at loc ["body","metadata","created_date"]
    # and ["body","metadata","created_by_email"]. `created_by_full_name` is
    # NOT among them, so it keeps its default. The omitted-metadata case is
    # unaffected: AddMessageBody's default_factory supplies both sentinels,
    # and the router still distinguishes the two cases via `model_fields_set`.
    created_date: datetime
    created_by_email: str
    created_by_full_name: str = "anonymous"


class ToolCall(BaseModel):
    """Per-tool-call shape on assistant messages (probed 2026-05-22 against
    Base44 prod).

    On INPUT (user-supplied tool_calls on AddMessageBody): only `id`,
    `name`, and `arguments_string` are required. Probed: B44 returns
    422 with `missing` for those three when absent, but `status` defaults
    to `"running"` server-side if the client omits it. `thought_signature`,
    `requires_user_input`, `results`, `user_input` all default to None/
    False.

    On OUTPUT (assistant tool_calls emitted by the loop): the loop fills
    all fields explicitly.

    Statuses include `waiting_for_user_input` per the SDK type, not just
    running/success/error/stopped. Field order matches the wire emission
    order.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    arguments_string: str
    thought_signature: Optional[str] = None
    requires_user_input: bool = False
    # `auto_approved`, `error_class`, `mutation_applied`: on every tool call
    # Base44 answers since 2026-09 (measured 2026-09-28).
    auto_approved: bool = False
    status: Literal["running", "success", "error", "stopped", "waiting_for_user_input"] = "running"
    error_class: Optional[str] = None
    results: Optional[str] = None
    user_input: Optional[dict] = None
    mutation_applied: Optional[bool] = None


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    role: Literal["user", "assistant", "system"]
    reasoning: Optional[Union[str, ReasoningBlock]] = None
    content: Union[str, dict]
    file_urls: Optional[list[str]] = None
    tool_calls: Optional[list[ToolCall]] = None
    usage: Optional[Usage] = None
    hidden: bool = False
    custom_context: list = Field(default_factory=list)
    checkpoint_id: Optional[str] = None
    metadata: MessageMetadata
    additional_message_params: dict = Field(default_factory=dict)
    agent_loop_id: Optional[str] = None
    # Last on every message Base44 answers or emits since 2026-09 (measured
    # 2026-09-28 on both message routes, every role); always null on the
    # wire so far.
    prompt_analysis: Optional[dict] = None


class ConversationSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_group_key: str
    message_count: int = 0
    credit_count: float = 0.0


class AgentConversation(BaseModel):
    """`summary` is non-null on every Base44 observed conv. We stamp it at
    create and update on every message push. Pre-stamp legacy docs (none in
    fresh migrations) are handled by `_serialize_conversation`'s defensive
    fallback in the router."""

    model_config = ConfigDict(extra="ignore")

    # Field order is the wire order (measured 2026-09-28 on create, read, PUT
    # and list). `region`, `conversation_type`, `expires_at`, `is_archived` and
    # `anonymous_visitor_key` arrived with Base44's visitor conversations; none
    # has been seen non-null / true on an app conversation yet. A visitor's
    # conversation is `created_by_id: "anonymous"` with the visitor's id in
    # `metadata.anonymous_visitor_id` (router.py).
    id: str
    created_date: datetime
    updated_date: datetime
    app_id: str
    created_by_id: str
    agent_name: str
    region: Optional[str] = None
    conversation_type: Optional[str] = None
    expires_at: Optional[datetime] = None
    title: Optional[str] = None
    is_archived: bool = False
    messages: list[Message] = Field(default_factory=list)
    summary: ConversationSummary
    metadata: dict = Field(default_factory=dict)
    anonymous_visitor_key: Optional[str] = None


class CreateConversationBody(BaseModel):
    """`custom_context` is accepted but **silently dropped** — Base44
    swallows it on create (verified empirically: not stored, not in
    response). Keep the field on the model so we don't 422 clients that
    send it; just don't persist."""

    model_config = ConfigDict(extra="ignore")

    agent_name: str
    metadata: dict = Field(default_factory=dict)
    custom_context: Optional[Any] = None


class UpdateConversationBody(BaseModel):
    """`metadata` is `dict` (not Optional) so `null` is rejected natively
    via Pydantic envelope #1 `dict_type`. Matches Base44 wire."""

    model_config = ConfigDict(extra="ignore")

    metadata: dict = Field(default_factory=dict)


class AddMessageBody(BaseModel):
    """Probed against Base44 prod 2026-05-21. `extra="forbid"`; `content`
    optional (stored as "" when omitted); `reasoning` Optional[ReasoningBlock]
    (NOT Union[str,...] — input only takes the structured form);
    `additional_message_params` loose-typed (int 42 passes Pydantic, crashes
    downstream as envelope #5 AttributeError); `metadata` optional and
    server-stamped to `anonymous`/`anonymous` when omitted regardless of
    auth context."""

    model_config = ConfigDict(extra="forbid")

    # ⚠️ `role` is `Literal["user"]` and DEFAULTED — re-measured 2026-08-02
    # (twice). Base44 answers `role: "assistant"` with
    # `literal_error … ctx.expected "'user'"`, and accepts a body that omits
    # `role` entirely. We previously did the opposite on both counts: we
    # REQUIRED it (so a client that omitted it, which Base44 allows, got a
    # 422 from us) and we ACCEPTED "assistant"/"system" (letting a caller
    # inject fabricated turns that the model then reads back as its own).
    # D-039's May reading of a 3-value enum is stale — same probe, different
    # answer today; that is drift, not a birth defect.
    # NOTE the STORED `Message.role` above keeps all three: the loop really
    # does write assistant/system rows. Only the request body narrowed.
    role: Literal["user"] = "user"
    content: Optional[str] = None
    # NOT Optional — Base44 rejects `metadata=null` with the Pydantic
    # `model_attributes_type` 422. Use `model_fields_set` in the handler to
    # distinguish "client omitted metadata" (→ server-stamp anonymous) from
    # "client sent metadata={...}" (→ store as-is).
    metadata: MessageMetadata = Field(
        default_factory=lambda: MessageMetadata(
            created_date=datetime(1970, 1, 1), created_by_email="anonymous"
        )
    )
    additional_message_params: Optional[Any] = None
    reasoning: Optional[ReasoningBlock] = None
    file_urls: Optional[list[str]] = None
    # `usage` is a real AddMessageBody field on B44 (probed: usage={} →
    # 422 missing prompt_tokens + completion_tokens). Client may send a
    # complete usage object; if so we accept and store it as-is. If
    # omitted (None), the loop stamps its own usage for assistant turns.
    usage: Optional[Usage] = None
    # Typed as `list[ToolCall]` so user-supplied tool_calls go through the
    # same validator B44 uses: requires id+name+arguments_string, status
    # defaults to "running" if omitted. Probed 2026-05-22.
    tool_calls: Optional[list[ToolCall]] = None
    hidden: bool = False
    custom_context: list = Field(default_factory=list)
    checkpoint_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _content_rules(cls, data):
        """Base44's three content rules, all raised at MODEL level.

        `mode="before"` is load-bearing: Base44 emits these at `loc: ["body"]`
        (measured 2026-08-02 on the raw wire), which is what a model-level
        ValueError produces once the router prepends "body". A field
        validator would emit `["body","content"]` instead, and a plain
        `Optional[str]` type error would fire before any validator could run.

        The rules, each measured against prod:

        * a dict content → "Message content must be a string" (value_error).
          Fires regardless of `file_urls`.
        * empty content → "Message content cannot be empty", where "empty"
          means `null`, `""`, or omitted — but ⚠️ ONLY when `file_urls` is
          absent or an EMPTY list. A non-empty `file_urls` EXEMPTS it, because
          an image-only turn legitimately carries no text. This exemption is
          not optional for us: our own agent-channel relay builds an
          image-only WhatsApp/Telegram turn as exactly `content="" +
          file_urls=[url]`, so enforcing emptiness unconditionally would 422
          every image sent to a migrated app's agent.
        * over-length content → "Message content is too long", counted in
          CODE POINTS not bytes (50,001 CJK chars = 150 KB is accepted on both
          sides; 100,001 ASCII is not). This used to live in the handler as a
          400 AFTER the conversation lookup; Base44 checks it here, before,
          and answers 422 — so a bad length on a nonexistent conversation
          returns the length error, not a 404.

        Anything else (`42`, `[]`) falls through to the `Optional[str]`
        annotation and gets Base44's plain "Input should be a valid string".
        """
        if not isinstance(data, dict):
            return data
        content = data.get("content")
        if isinstance(content, dict):
            raise ValueError("Message content must be a string")
        if content in (None, "") and not data.get("file_urls"):
            raise ValueError("Message content cannot be empty")
        if isinstance(content, str) and len(content) > CONTENT_MAX_LENGTH:
            raise ValueError("Message content is too long")
        return data
