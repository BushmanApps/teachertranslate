"""
Socket.IO realtime — who may listen, and what each listener is sent.

When init() is called, Socket.IO is active. When it's not called,
emit_entity_event() and emit_agent_event() are no-ops. main.py decides
whether to call init() based on REALTIME_ENABLED, and uses the returned
ASGIApp as the outer entrypoint when realtime is on — so Socket.IO can
intercept its specific path and delegate everything else to FastAPI.

A socket is a READER like any other. Base44 treats it as one (measured
2026-09-28 with an anonymous socket, the app's owner and a second user
listening to the same rooms —
research/divergence-chasing/2026-09-28-parity-audit):

- The handshake is the login. Its query carries `app_id` and either `token`
  (the app user's token) or nothing (`anonymous_id` names a visitor). No
  `app_id`, another app's, a token that does not validate (`null` and
  `undefined` — what an SDK before 0.8.51 sent for a signed-out visitor —
  included) → "Connection rejected by server". An empty token is a visitor.
  A visitor is refused on an app that requires login: the visibility gate,
  the same one every HTTP route passes.
- An entity event goes to the listeners who may READ that row, each getting
  the row as THEY may see it: the entity's read rule evaluated per listener
  on the row as written (an update that takes a row out of someone's reach
  sends them nothing, not a delete; one that brings it into reach arrives as
  an `update`), field rules masked per listener, `created_by` hidden where
  REST hides it. The app's owner is a reader like any other — no exemption.
- An agent conversation's room is joined by the conversation's owner only.

May 2026 measured the opposite (any socket, every row —
research/testing-server/realtime/FINDINGS.md F4) and this module copied it;
Base44 closed that since.

Wire shape (probed against Base44 production 2026-05-21, re-read 2026-09-28):

- All `update_model` events carry the canonical Socket.IO room-broadcast
  envelope `{"room": <room>, "data": <JSON-string>}`. The SDK's
  `RoomsSocket` dispatcher needs `msg.room` to fan out to per-room
  listeners and `JSON.parse(msg.data)` to recover the inner event.
- Entity events: inner = `{"type": op, "id": row_id, "entityName": ent,
  "data": row}`. No `timestamp` (SDK synthesizes one if absent).
- Agent events: inner = `{"id": conversation_id, "_message": msg}` (id
  FIRST, _message SECOND — matches Base44 prod field order).
- Datetimes inside the inner payload use Python's `datetime.isoformat()`
  via `_DateTimeEncoder` — tz-aware UTC emits `+00:00` (Base44's offset
  form on realtime), naive UTC emits no suffix. This is intentionally
  distinct from REST's `Z` suffix (which comes from Pydantic v2
  `mode="json"`); the realtime serializer keeps `mode="python"` upstream
  so `datetime` instances reach this encoder.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable
from urllib.parse import parse_qs

import socketio

from app.core import db
from app.core.errors import AppError
from app.core.security.pipeline import AuthedContext, context_for_credentials
from app.core.security.visibility import assert_app_visible


class _DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


@dataclass
class Listener:
    """A socket's reader: the credentials its handshake carried and the
    context they resolve to. The context is re-resolved once it is older than
    the settings read (db.FRESHNESS_SECONDS), so a role change, a deleted
    account, an expired token or a visibility change reaches a socket that is
    already open — the way it reaches the next HTTP request."""

    authorization: str | None
    visitor_id: str | None
    ctx: AuthedContext
    resolved_at: float

    @property
    def reader(self) -> str:
        """Listeners with one reader are sent the same thing."""
        principal = self.ctx.principal or {}
        return f"{self.ctx.token_class}:{principal.get('id', '')}"


class _Refused(Exception):
    pass


# What a module says about joining ITS rooms: (listener, room) -> may join.
RoomGuard = Callable[[Listener, str], Awaitable[bool]]

_sio: socketio.AsyncServer | None = None
_settings = None
_room_guards: dict[str, RoomGuard] = {}


def guard_rooms(prefix: str, guard: RoomGuard) -> None:
    """A module that emits into rooms of its own names who may join them.
    A room no module guards is joined by nobody — nothing emits into it."""
    _room_guards[prefix] = guard


async def _admit(authorization: str | None, visitor_id: str | None) -> Listener:
    ctx = await context_for_credentials(authorization, _settings, visitor_id=visitor_id)
    if authorization and ctx.principal is None:
        raise _Refused
    try:
        assert_app_visible(ctx.token_class, ctx.app_settings, _settings.APP_ID, user=ctx.user)
    except AppError:
        raise _Refused
    return Listener(authorization, visitor_id, ctx, time.monotonic())


async def _listener(sid: str) -> Listener | None:
    """The socket's reader as of now; a socket whose credentials no longer
    admit it is disconnected."""
    listener: Listener | None = (await _sio.get_session(sid)).get("listener")
    if listener is None:
        return None
    if time.monotonic() - listener.resolved_at <= db.FRESHNESS_SECONDS:
        return listener
    try:
        listener = await _admit(listener.authorization, listener.visitor_id)
    except _Refused:
        await _sio.disconnect(sid)
        return None
    await _sio.save_session(sid, {"listener": listener})
    return listener


def init(settings, *, other_asgi_app=None) -> socketio.ASGIApp:
    """Create and return the Socket.IO ASGI app to use as the outer entrypoint.

    `other_asgi_app` is the FastAPI app to delegate to for non-Socket.IO
    paths (and for lifespan events). Without this, `socketio.ASGIApp`
    handles only its own path and 404s everything else — which would
    shadow `/health`, the SPA catch-all, and every module route if
    mounted at `/` after them. The library-default integration pattern
    is to wrap the FastAPI app via `other_asgi_app=`; Socket.IO
    intercepts its path and delegates the rest.
    """
    global _sio, _settings
    _settings = settings
    origins = settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS != "*" else "*"
    _sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=origins)

    @_sio.event
    async def connect(sid, environ, auth=None):
        query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        if query.get("app_id", [""])[0] != settings.APP_ID:
            return False
        token = query.get("token", [""])[0]
        try:
            listener = await _admit(
                f"Bearer {token}" if token else None,
                query.get("anonymous_id", [None])[0],
            )
        except _Refused:
            return False
        await _sio.save_session(sid, {"listener": listener})

    @_sio.on("join")
    async def join(sid, room):
        if not isinstance(room, str):
            return
        listener = await _listener(sid)
        if listener is None:
            return
        if room.startswith(f"entities:{settings.APP_ID}:"):
            # Anyone admitted may listen; what reaches them is decided per
            # event, per listener (emit_entity_event).
            await _sio.enter_room(sid, room)
            return
        for prefix, guard in _room_guards.items():
            if room.startswith(prefix) and await guard(listener, room):
                await _sio.enter_room(sid, room)
                return

    @_sio.on("leave")
    async def leave(sid, room):
        if isinstance(room, str):
            await _sio.leave_room(sid, room)

    return socketio.ASGIApp(
        _sio,
        other_asgi_app=other_asgi_app,
        socketio_path="/ws-user-apps/socket.io/",
    )


async def emit_entity_event(
    app_id: str,
    entity_name: str,
    op: str,
    row_id: str,
    view: Callable[[AuthedContext], dict | None],
) -> None:
    """Send an entity event to the listeners of the entity's room who may read
    the row. `view(ctx)` is the row as that reader may see it, or None when
    they may not see it at all — the entities service owns it, next to the
    REST read it mirrors."""
    if _sio is None:
        return
    room = f"entities:{app_id}:{entity_name}"
    readers: dict[str, tuple[AuthedContext, list[str]]] = {}
    for sid, _ in list(_sio.manager.get_participants("/", room)):
        listener = await _listener(sid)
        if listener is not None:
            readers.setdefault(listener.reader, (listener.ctx, []))[1].append(sid)

    for ctx, sids in readers.values():
        row = view(ctx)
        if row is None:
            continue
        event = {"type": op, "id": row_id, "entityName": entity_name, "data": row}
        message = {"room": room, "data": json.dumps(event, cls=_DateTimeEncoder)}
        for sid in sids:
            await _sio.emit("update_model", message, to=sid)


async def emit_agent_event(conversation_id: str, message: dict) -> None:
    if _sio is None:
        return
    room = f"/agent-conversations/{conversation_id}"
    truncated = _truncate_agent_message(message)
    # Base44 prod field order (probed): id FIRST, _message SECOND.
    inner = {"id": conversation_id, "_message": truncated}
    await _sio.emit(
        "update_model",
        {"room": room, "data": json.dumps(inner, cls=_DateTimeEncoder)},
        room=room,
    )


def _truncate_agent_message(message: dict) -> dict:
    out = dict(message)
    if out.get("tool_calls"):
        out["tool_calls"] = [_truncate_tool_call(tc) for tc in out["tool_calls"]]
    return out


def _truncate_tool_call(tc: dict) -> dict:
    out = dict(tc)
    if out.get("arguments_string") and len(out["arguments_string"]) > 500:
        out["arguments_string"] = out["arguments_string"][:500]
    if out.get("results") and len(out["results"]) > 50:
        out["results"] = out["results"][:50]
    return out
