"""
The auth pipeline — to be implemented by the security agent.

This is a FastAPI dependency (used via Depends) that runs on every runtime request.

Steps:
1. Classify the token (via classify.py)
2. If app_user or preview with verified email: resolve the User row from Mongo
3. If service_role: build the synthetic service principal
4. Run the visibility gate (via visibility.py) — unless the route opts out
5. Return an AuthedContext

AuthedContext should contain:
    token_class: Literal["anonymous", "app_user", "service_role", "platform", "preview"]
    user: dict | None          # resolved User row for app_user / verified preview
    service_principal: dict | None  # synthetic principal for service_role
    app_settings: dict         # from _app_settings collection

Endpoint handlers receive AuthedContext and never re-parse Authorization.

Some routes need a lighter variant that skips the visibility gate:
- Backend function routes (they have their own gate)
- Management routes (if we add them later)
Expose a separate dependency for these cases (e.g., get_authed_context_no_visibility).

See security.md for the full auth/visibility specification.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.core import db
from app.core.errors import AppError, AppHTTPException
from app.core.responses import serialize_entity, utcnow
from app.core.security.classify import TokenClass, classify_headers
from app.core.security.visibility import assert_app_visible


@dataclass(slots=True)
class AuthedContext:
    token_class: TokenClass
    user: dict | None
    service_principal: dict | None
    app_settings: dict
    token_payload: dict | None = None
    principal: dict | None = None
    # `is_admin` — derived from token class + app-owner email check. Used as
    # the gate for honoring the `X-Bypass-RLS: true` header. Probed against
    # Base44 production 2026-05-22: service_role and app-owner app_user JWT
    # are admin; all other classes are not. See F-007.
    is_admin: bool = False
    # `bypass_rls` — True iff the request set `X-Bypass-RLS: true` AND
    # `is_admin`. Set by `_build_context`; if the header is "true" but
    # `is_admin` is False, _build_context raises 401 instead of setting this.
    # RLS engine short-circuits to allow-all when this is True.
    bypass_rls: bool = False
    # A signed-out visitor's id: the SDK's `X-Base44-Anonymous-Id` header (its
    # analytics session id), `anonymous_id` on a realtime handshake. Kept only
    # for a caller with no principal — it is what makes a visitor's agent
    # conversation THEIRS (modules/agents).
    visitor_id: str | None = None


async def get_authed_context(request: Request) -> AuthedContext:
    return await _build_context(request, check_visibility=True)


async def get_authed_context_no_visibility(request: Request) -> AuthedContext:
    return await _build_context(request, check_visibility=False)


async def get_authed_context_required_no_visibility(request: Request) -> AuthedContext:
    """Like `get_authed_context_no_visibility`, but raises 401 when the
    caller is unauthenticated.

    Behavior — probe-verified against Base44 (`POST /users/invite-user`):
    - No `Authorization` header at all -> 401 "No authentication header
      (Authorization: Bearer <token> or api_key)".
    - Invalid Bearer (junk JWT, wrong signature, expired) -> 401 "Could not
      validate credentials".
    - Anything else (app_user, service_role, platform, preview) -> proceed
      with the context attached.

    Crucially the 401 raise happens BEFORE FastAPI runs Pydantic body
    validation, so a request with no auth + a malformed body returns 401,
    not 422. This matches Base44's universal gate order:
        app_id-match -> auth-required (if endpoint requires it)
                     -> visibility (if endpoint visibility-gated)
                     -> body Pydantic
                     -> handler logic
    FastAPI resolves Depends() before body field validation, so a Depends
    that raises short-circuits everything that comes after.

    Use this on endpoints where Base44 returns 401 (not 403 visibility-deny)
    on no-auth — verified set so far: `POST /users/invite-user`. Most other
    endpoints are either visibility-gated (use `get_authed_context_no_visibility`
    + manual visibility check, or `get_authed_context`) or genuinely public
    (no dep at all). Probe an endpoint with no-auth + valid-body before
    swapping to this dep; the wire response tells you which gate Base44 runs.
    """
    ctx = await _build_context(request, check_visibility=False)
    if ctx.token_class == "anonymous":
        # Distinguish "no Authorization header at all" from "header present
        # but invalid" — Base44 uses different messages and the classifier
        # collapses both to "anonymous", so we re-inspect headers here.
        #
        # F-034 (probed 2026-05-23 paired): only `Authorization` counts as
        # an auth header for this distinction. `Base44-Service-Authorization`
        # alone returns "No authentication header" on B44 — consistent with
        # F-034's finding that B44 doesn't honor that header inbound at
        # all. We previously treated its presence as "header present but
        # invalid" → 'Could not validate credentials'; that was wrong.
        if not request.headers.get("Authorization"):
            raise AppHTTPException(
                401,
                "No authentication header (Authorization: Bearer <token> or api_key)",
            )
        raise AppHTTPException(401, "Could not validate credentials")
    return ctx


async def build_app_user_context(email: str) -> AuthedContext | None:
    """Build an app_user context for a known account, with no HTTP request.

    The agent channel relays (WhatsApp/Telegram) need one: their caller is a
    phone number bound to an account rather than a browser holding a token,
    but every downstream check — RLS, FLS, entity ownership, admin bypass —
    reads the same context an in-app caller produces, so it has to be built
    the same way rather than approximated here. Returns None when the account
    no longer exists, which the caller treats as "not connected".

    No visibility gate: the binding could only have been created from an
    authenticated in-app session, which already passed it.
    """
    app_settings = await db.app_settings()
    user = await _resolve_user({"sub": email}, require_verified=False)
    if user is None:
        return None

    return AuthedContext(
        token_class="app_user",
        user=user,
        service_principal=None,
        app_settings=app_settings,
        token_payload={"sub": email},
        principal=_build_user_principal(user, app_settings.get("additional_user_data_schema")),
        is_admin=_compute_is_admin("app_user", user, app_settings),
        bypass_rls=False,
    )


async def context_for_credentials(
    authorization: str | None, settings, *, visitor_id: str | None = None,
) -> AuthedContext:
    """Who a credential is, before any gate: the token classified, the account
    resolved, the principal the rule engines read. One owner for every door a
    caller comes through — an HTTP request's `Authorization` header here, a
    realtime socket's handshake token in core/realtime.py — so a rule can never
    see one person as two different principals."""
    app_settings = await db.app_settings()
    token_class, token_payload = classify_headers(authorization, settings)

    user = None
    service_principal = None
    principal = None

    if token_class == "app_user":
        user = await _resolve_user(token_payload, require_verified=False)
        principal = _build_user_principal(user, app_settings.get("additional_user_data_schema"))
    elif token_class == "preview":
        user = await _resolve_user(token_payload, require_verified=True)
        principal = _build_user_principal(user, app_settings.get("additional_user_data_schema"))
    elif token_class == "service_role":
        service_principal = _build_service_principal(token_payload)
        principal = _build_service_principal_for_security(service_principal)

    return AuthedContext(
        token_class=token_class,
        user=user,
        service_principal=service_principal,
        app_settings=app_settings,
        token_payload=token_payload,
        principal=principal,
        is_admin=_compute_is_admin(token_class, user, app_settings),
        bypass_rls=False,  # an HTTP request sets it after visibility passes
        # A visitor is a caller with no principal who carries the id — a
        # token that resolves to nobody (a stale or foreign JWT) counts as no
        # token here (measured 2026-09-28: a garbage token plus the header
        # creates the visitor's conversation).
        visitor_id=(visitor_id or None) if principal is None else None,
    )


async def _build_context(request: Request, check_visibility: bool) -> AuthedContext:
    settings = request.app.state.settings
    ctx = await context_for_credentials(
        request.headers.get("Authorization"), settings,
        visitor_id=request.headers.get("X-Base44-Anonymous-Id"),
    )

    # Gate order matches Base44 production:
    #   visibility → admin-required (if X-Bypass-RLS is set) → body validation → handler
    # Probed 2026-05-22 (F-007 extended):
    # - public_with_login + anon + X-Bypass-RLS → 403 visibility-deny "You must be
    #   logged in to access this app" (visibility fires first, never reaches bypass
    #   gate).
    # - public_without_login + anon + X-Bypass-RLS → 401 "Authentication required for
    #   admin operations" (visibility passes; bypass gate denies no-auth).
    # - any visibility + authed non-admin + X-Bypass-RLS → 403 "Admin permissions
    #   required for this operation" with detail "This operation requires admin
    #   privileges...".
    #
    # The bypass-admin gate ALSO only fires on routes that use the
    # visibility-gated dependency (`get_authed_context`). Probed: routes like
    # `/api/apps/public/prod/public-settings/by-id/<id>` and `/auth/register`
    # accept `X-Bypass-RLS: true` from anonymous callers and return 200 — Base44
    # doesn't fire the bypass gate on non-runtime/public endpoints. Tying the
    # check to `check_visibility` matches this behavior since those routes use
    # `get_authed_context_no_visibility` (or no auth context at all).
    if check_visibility:
        assert_app_visible(ctx.token_class, ctx.app_settings, settings.APP_ID, user=ctx.user)
        ctx.bypass_rls = _compute_bypass_rls(request, ctx)

    return ctx


def _compute_is_admin(token_class: TokenClass, user: dict | None, app_settings: dict) -> bool:
    """True iff the caller has admin rights on this app.

    Probed against Base44 production 2026-05-22 (F-007):
    - service_role JWT → admin (the `X-Bypass-RLS: true` header is honored).
    - app_user JWT where `user.email == _app_settings.created_by` → admin
      (the app owner). Verified on data-core-lab with Daniel as owner.
    - api_key → admin on Base44, but we don't currently classify api_key
      as a distinct token class. Not handled here; see F-007 §"Open
      follow-ups" for the api_key path.
    - All other classes → not admin.

    The `created_by` field is the app-owner email (a Base44 platform
    convention — `_app_settings.created_by` is set to the user who created
    the Base44 app, e.g. "daniel.frishtik@gmail.com"). Comparison is exact
    email string equality.
    """
    if token_class == "service_role":
        return True
    if token_class == "app_user" and user is not None:
        owner_email = app_settings.get("created_by")
        if isinstance(owner_email, str) and user.get("email") == owner_email:
            return True
    return False


def _compute_bypass_rls(request: Request, ctx: AuthedContext) -> bool:
    """Honor the `X-Bypass-RLS: true` admin header (F-001, F-007).

    Strict equality on the header value — `"true"` (case-sensitive value).
    Header name is case-insensitive per HTTP standard. Probed against
    Base44: `TRUE`, `1`, `yes` all behave like the header is absent.

    If the header is set but the caller is not admin, Base44 emits TWO
    distinct envelopes depending on auth state (both envelope #3,
    bare-backend shape — no `error_type` field, both fields nullable):

    - **anonymous** caller (no Authorization header — typically reaches
      this branch only on `public_without_login` apps where visibility
      passes): `401 "Authentication required for admin operations"` with
      `detail: null`.
    - **authenticated non-admin** caller: `403 "Admin permissions required
      for this operation"` with `detail: "This operation requires admin
      privileges. Please ensure you have admin role for this app."`.

    On `public_with_login` / `private_with_login` / `workspace_with_login`
    apps, the visibility gate fires FIRST for anonymous callers — they
    never reach this function. The bypass gate is reached only after
    visibility passes.
    """
    if request.headers.get("X-Bypass-RLS") != "true":
        return False
    if ctx.is_admin:
        return True
    # Anonymous AND platform tokens take the no-auth path — probed 2026-05-22
    # against data-core-lab: PLATFORM Bearer + X-Bypass-RLS returns 401
    # "Authentication required for admin operations" (same as anon), not the
    # 403 "Admin permissions required" emitted for authed app_user/service_role
    # non-admins. Matches the documented "platform is not a runtime user
    # identity" architecture.md decision — platform tokens behave like
    # anonymous on the entity surface.
    if ctx.token_class in ("anonymous", "platform"):
        raise AppError(401, "Authentication required for admin operations")
    raise AppError(
        403,
        "Admin permissions required for this operation",
        detail="This operation requires admin privileges. Please ensure you have admin role for this app.",
    )


async def _resolve_user(token_payload: dict | None, require_verified: bool) -> dict | None:
    email = token_payload.get("sub") if isinstance(token_payload, dict) else None
    if not isinstance(email, str):
        return None

    user = await db.coll("User").find_one({"email": email})
    if not user:
        return None

    serialized = serialize_entity(user)
    if require_verified and serialized.get("is_verified") is not True:
        return None

    return serialized


def _build_service_principal(token_payload: dict | None) -> dict | None:
    if not isinstance(token_payload, dict):
        return None

    subject = token_payload.get("sub") or token_payload.get("client_id")
    if not isinstance(subject, str):
        return None

    return {
        "sub": subject,
        "client_id": token_payload.get("client_id"),
        "app_id": token_payload.get("app_id"),
        "id": f"service_{subject}",
        "email": f"service+{subject}@no-reply.base44.com",
        "full_name": f"Service ({subject})",
        "role": "admin",
        "_app_role": "admin",
        "is_service": True,
        "is_verified": True,
        "force_password_reset": False,
        "collaborator_role": "editor",
        "disabled": None,
        "created_date": utcnow(),
        "updated_date": utcnow(),
    }


_BUILT_IN_USER_KEYS = frozenset({
    "id", "role", "email", "full_name", "_app_role",
    "created_date", "updated_date",
    "disabled", "disabled_reason",
    "is_verified", "force_password_reset",
    "app_id", "is_service", "collaborator_role",
})


def _build_user_principal(
    user: dict | None,
    additional_user_data_schema: dict | None,
) -> dict | None:
    """Reshape a flat User document into the principal that RLS/FLS evaluates against.

    Empirical contract probed against Base44 production (data-core-lab,
    2026-05-20 — full template + user_condition + orphan-field matrix in
    `research/testing-server/entities/findings.md`):

    Base44 routes each User-doc field according to its membership in two
    sets — `_BUILT_IN_USER_KEYS` (the 14 canonical User fields) and
    `additional_user_data_schema.properties` (the per-app custom fields):

    - In built-in only → top-level only.
      e.g. `email`, `id`, `full_name`, `_app_role` on a typical app.
      Probe: `{{user.email}}` resolves; `{{user.data.email}}` does not.
    - In additional schema only (a pure custom field) → `data.<key>` only.
      e.g. `nickname`, `lucky_number` on data-core-lab.
      Probe: `{{user.nickname}}` does not resolve; `{{user.data.nickname}}`
      does.
    - In BOTH (the chat AI sometimes adds built-in names like `role` to
      `additional_user_data_schema`) → top-level AND `data.<key>`.
      Probe: `{{user.role}}` AND `{{user.data.role}}` both resolve.
    - In NEITHER (server-stamped or undeclared extras like `environment`
      or `extra=allow`-persisted custom keys) → `data.<key>` only.
      Probe: `user_condition: {"data.environment": null}` matches when
      the User doc has `environment: null`; `user_condition:
      {"data.orphan_key": "fluffy"}` matches when orphan_key was set via
      PUT /me + extra=allow.

    The previous implementation used a single "in additional schema →
    data; else → top" branch and mis-routed (a) `role` to data-only when
    the schema included it (breaking `user_condition: {role: "admin"}`),
    and (b) every undeclared User-doc key to top-level instead of data.

    `_id` is stripped earlier in `_resolve_user` → `serialize_entity`,
    so no Mongo-internal-key filtering needed here. The leading-underscore
    `_app_role` is in the built-in set and stays at top-level.
    """
    if not user:
        return None

    custom_fields = set(
        ((additional_user_data_schema or {}).get("properties") or {}).keys()
    )
    principal: dict = {"data": {}}

    for key, value in user.items():
        in_builtin = key in _BUILT_IN_USER_KEYS
        in_custom = key in custom_fields

        if in_builtin:
            principal[key] = value
        if not in_builtin or in_custom:
            principal["data"][key] = value

    return principal


def _build_service_principal_for_security(service_principal: dict | None) -> dict | None:
    if not service_principal:
        return None

    return {
        "id": service_principal["id"],
        "email": service_principal["email"],
        "role": "admin",
        "is_service": True,
        "collaborator_role": "editor",
        "disabled": None,
        "data": {},
    }
