"""
Exception types and FastAPI exception handlers.

Six wire envelopes exist in Base44 production (per DISCOVERIES.md D-002, D-004,
beyond-pydantic-leaks C-005):

1. Bare FastAPI 422 — `{"detail": [{type, loc, msg, input}]}`. Produced by
   FastAPI's built-in handler for `RequestValidationError` (raised by
   `body: SomeModel` validation failures, or manually by us).
2. Wrapped ValidationError — `{error_type: "ValidationError", message,
   detail (string repr of errors list), traceback: "", request_id: null}`.
   Produced by `WrappedValidationError` (caught after manual
   `Model(**body)` + `try/except ValidationError`).
3. HTTPException with dict-detail (integrations) — `AppHTTPException` with
   `detail` as a dict. The existing handler preserves dict values as-is.
4. Normal HTTPException — `AppHTTPException(status, message)` with string
   detail (or detail = message when None).
5. Leaked Python exception — `{error_type: <ClassName>, message: str(exc),
   detail: same, traceback: "", request_id: null}`. Produced by the
   `Exception` catchall for uncaught exceptions
   (`ObjectNotFoundError`, `ValueError`, `InvalidId`, `AttributeError`,
   `TypeError`, etc.).
6. Bare backend (AppError) — `{message, detail, traceback: null,
   extra_data: null or {...}, request_id: null}`. Used by RLS / FLS /
   visibility denials.

`AppHTTPException` covers both envelopes #3 and #4 — wire shape is
identical, the difference is whether `detail` is a dict or a string.

The `Exception` catchall is dispatch-of-last-resort. FastAPI's MRO-based
exception routing means `AppHTTPException`, `AppError`,
`WrappedValidationError`, `RequestValidationError`, and built-in
`HTTPException` all win over it for those specific types.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppHTTPException(Exception):
    """Produces envelope #2 (string detail) / #3 (dict detail).

    Wire shape: `{error_type, message, detail, traceback, request_id}`.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        detail: str | dict | None = None,
        error_type: str = "HTTPException",
    ):
        self.status_code = status_code
        self.message = message
        self.detail = detail if detail is not None else message
        self.error_type = error_type

    def __str__(self) -> str:
        return f"status={self.status_code} message={self.message} details={self.detail}"


class AppError(Exception):
    """Produces envelope #6 (and visibility variant when extra_data is set)."""

    def __init__(
        self,
        status_code: int,
        message: str,
        detail: str | None = None,
        extra_data: dict | None = None,
    ):
        self.status_code = status_code
        self.message = message
        self.detail = detail
        self.extra_data = extra_data

    def __str__(self) -> str:
        return f"status={self.status_code} message={self.message} details={self.detail} extra_data={self.extra_data}"


class WrappedValidationError(Exception):
    """Produces envelope #2 with `error_type='ValidationError'`.

    Raised after manual `Model(**body)` + `try/except ValidationError`. The
    handler renders `message` as `\\n`-joined `"Error in field X: <msg>"` lines
    in Pydantic declaration order (D-002), and `detail` as the Python
    `repr()` of the errors list with tuple-syntax `loc`.
    """

    def __init__(self, errors: list[dict]):
        self.errors = errors


class ObjectNotFoundError(Exception):
    """Produces envelope #5 with `error_type='ObjectNotFoundError'`.

    Wire format of `str(exc)` (re-measured 2026-09-28 on the conversation
    routes, the only ones still raising it — the auth routes moved to
    HTTPExceptions): the filter's KEYS as a list, never its values —
    `"['_id'] -> Object not found"` — and, for an id that does not parse,
    `"Invalid id value -> Object not found"`. Until 2026-09 the values were
    echoed (`{'_id': ObjectId('…')}`, `Invalid id value: <id>`).
    """

    def __init__(self, query: dict | None = None):
        self.query = query

    def __str__(self) -> str:
        what = list(self.query) if self.query is not None else "Invalid id value"
        return f"{what} -> Object not found"


def entity_not_found(entity_name: str, entity_id: str) -> AppError:
    return AppError(404, f"Entity {entity_name} with ID {entity_id} not found")


def permission_denied(entity_name: str, op: str) -> AppError:
    return AppError(403, f"Permission denied for {op} operation on {entity_name} entity")


def fls_write_deny(fields: list[str], op: str) -> AppError:
    verb = "set" if op == "create" else "modify"
    joined = ", ".join(f"data.{f}" for f in fields)
    return AppError(403, f"You're not allowed to {verb} the following fields: {joined}")


def visibility_deny(message: str, app_id: str) -> AppError:
    return AppError(403, message, extra_data={"app_id": app_id, "reason": "auth_required"})


def _is_unparseable_body(errors: list[dict]) -> bool:
    """True when the validation error list indicates the request body could
    not be decoded at all — either no body at all (`type=missing,
    loc=(body,)`) or invalid JSON (`type=json_invalid`).

    Used by the integrations RequestValidationError handler to swap in
    Base44's verbatim "payload is not serializable to json..." message.
    """
    if len(errors) != 1:
        return False
    err = errors[0]
    if err.get("type") == "json_invalid":
        return True
    if err.get("type") == "missing" and tuple(err.get("loc", ())) == ("body",):
        return True
    return False


def _jsonable_errors(errors: list[dict]) -> list[dict]:
    """Render Pydantic errors with JSON-safe ctx values (Exception → str)."""
    out = []
    for err in errors:
        err = dict(err)
        ctx = err.get("ctx")
        if isinstance(ctx, dict):
            err["ctx"] = {
                k: (str(v) if isinstance(v, Exception) else v)
                for k, v in ctx.items()
            }
        out.append(err)
    return out


def _loc_to_field(loc: tuple | list) -> str:
    """Render a Pydantic error loc as a dotted field name.

    Strips a leading `body` (FastAPI injects it for body-validation errors)
    and joins the rest with `.`. Matches the `"Error in field X"` formatting
    Base44 emits in envelope #2 messages.
    """
    parts = list(loc)
    if parts and parts[0] == "body":
        parts = parts[1:]
    return ".".join(str(p) for p in parts) if parts else ""


def core_validation(errors: list) -> tuple[str, dict]:
    """The Core integrations' validation answer — (`message`, `detail`) —
    from pydantic's errors, whoever raised them (a handler's own model
    through `validate_body`, or FastAPI reading the route's parameters).

    Base44's wire carries `type`, `loc`, `msg` (+ `ctx`) per error and
    nothing else — measured 2026-09-17 across 385 recorded 422s on
    GenerateVideo / GenerateImage / InvokeLLM, and 2026-09-28 on the upload
    routes: never pydantic's `input` echo, never its docs `url`.

    `message` is Python's str() of the errors — a location prints as a tuple
    (`('file',)`), and the ValueError a validator raised is still an OBJECT
    inside `ctx`, so it prints as `ValueError("…")` (measured: InvokeLLM's
    bad-model 422). `detail` is the same as JSON: the location a list, the
    error its text.
    """
    cleaned = []
    for err in errors:
        err = {k: v for k, v in dict(err).items() if k not in ("input", "url")}
        err["loc"] = tuple(err.get("loc", ()))
        cleaned.append(err)
    message = str({"message": "Validation Error", "error": cleaned})
    detail = {
        "message": "Validation Error",
        "error": [
            {
                **err,
                "loc": list(err["loc"]),
                **({"ctx": {k: (str(v) if isinstance(v, Exception) else v) for k, v in err["ctx"].items()}}
                   if isinstance(err.get("ctx"), dict) else {}),
            }
            for err in cleaned
        ],
    }
    return message, detail


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppHTTPException)
    async def handle_http_exception(_req: Request, exc: AppHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_type": exc.error_type,
                "message": exc.message,
                "detail": exc.detail,
                "traceback": "",
                "request_id": None,
            },
        )

    @app.exception_handler(AppError)
    async def handle_app_error(_req: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "message": exc.message,
                "detail": exc.detail,
                "traceback": None,
                "extra_data": exc.extra_data,
                "request_id": None,
            },
        )

    @app.exception_handler(WrappedValidationError)
    async def handle_wrapped_validation(_req: Request, exc: WrappedValidationError):
        message = "\n".join(
            f"Error in field {_loc_to_field(e['loc'])}: {e['msg']}"
            for e in exc.errors
        )
        # `detail` is the Python `repr()` of the errors list. Pydantic emits
        # `loc` as a tuple; we keep it as a tuple here so the repr matches
        # Base44's wire output (e.g. `('public_settings',)` not `['public_settings']`).
        detail = repr([
            {
                "type": e["type"],
                "loc": tuple(e["loc"]),
                "msg": e["msg"],
                "input": e.get("input"),
                # Base44 conditionally includes both `ctx` and `url` — emit
                # only when the source error dict actually has them. Pydantic
                # 2 returns `url` for some error types and not others; we
                # mirror that on the wire instead of adding `'url': None`.
                **({"ctx": e["ctx"]} if "ctx" in e else {}),
                **({"url": e["url"]} if "url" in e else {}),
            }
            for e in exc.errors
        ])
        return JSONResponse(
            status_code=422,
            content={
                "error_type": "ValidationError",
                "message": message,
                "detail": detail,
                "traceback": "",
                "request_id": None,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(req: Request, exc: RequestValidationError):
        # Two-path behavior matching Base44 production (own-probes 2026-05-20):
        #   - Under `/integration-endpoints/Core/*`, Base44 wraps every
        #     FastAPI-level validation error in envelope #3. Empty body /
        #     malformed JSON gets a specific custom message; field-level
        #     errors keep the Pydantic shape with `body` stripped from loc.
        #   - Everywhere else (entities, auth, etc.), Base44 emits the bare
        #     FastAPI envelope `{"detail":[...]}` — so we delegate to the
        #     default behavior outside the integrations namespace.
        if "/integration-endpoints/Core/" not in req.url.path:
            return JSONResponse(
                status_code=422,
                content={"detail": _jsonable_errors(exc.errors())},
            )

        errors = exc.errors()
        if _is_unparseable_body(errors):
            # Custom Base44 message — covers truly-empty bodies, malformed
            # JSON, and `application/json` Content-Type on a multipart
            # endpoint (UploadFile etc.). The advice about multipart is
            # part of the verbatim Base44 string.
            msg = (
                "payload is not serializable to json. if you're using files, "
                "use Content-Type: multipart/form-data in headers"
            )
            return JSONResponse(
                status_code=422,
                content={
                    "error_type": "HTTPException",
                    "message": msg,
                    "detail": msg,
                    "traceback": "",
                    "request_id": None,
                },
            )

        # Field-level validation error inside an integration endpoint: the
        # Core validation envelope, the one `validate_body` answers with —
        # without the request part FastAPI names in front of the location
        # (`body`), which Base44 does not surface.
        message, detail = core_validation(
            [{**err, "loc": tuple(err["loc"])[1:]} if tuple(err.get("loc", ()))[:1] == ("body",) else err for err in errors]
        )
        return JSONResponse(
            status_code=422,
            content={
                "error_type": "HTTPException",
                "message": message,
                "detail": detail,
                "traceback": "",
                "request_id": None,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_starlette_http_exception(_req: Request, exc: StarletteHTTPException):
        # Envelope #4 wrap for HTTPExceptions raised by Starlette / FastAPI
        # internals — e.g., the auto-405 emitted when a registered route
        # doesn't accept the request method, or any plain `HTTPException(...)`
        # raised without our `AppHTTPException` subclass. Without this,
        # Starlette's default handler emits the bare `{"detail": ...}` shape
        # (envelope #1-ish) which doesn't match Base44's wire contract.
        # `AppHTTPException` has its own handler registered above and wins
        # by MRO since it's not a Starlette subclass.
        detail = exc.detail if exc.detail is not None else ""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_type": "HTTPException",
                "message": detail,
                "detail": detail,
                "traceback": "",
                "request_id": None,
            },
        )

    @app.exception_handler(Exception)
    async def handle_uncaught(_req: Request, exc: Exception):
        # Envelope #5 — catchall for ObjectNotFoundError, InvalidId,
        # JSONDecodeError, ValueError, AttributeError, TypeError,
        # AssertionError, and anything else not caught by a more specific
        # handler. MRO routing ensures AppHTTPException / AppError /
        # WrappedValidationError / RequestValidationError / HTTPException
        # land in their own handlers before reaching this one.
        message = str(exc)
        return JSONResponse(
            status_code=500,
            content={
                "error_type": type(exc).__name__,
                "message": message,
                "detail": message,
                "traceback": "",
                "request_id": None,
            },
        )
