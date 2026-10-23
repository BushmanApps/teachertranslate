"""Entity-schema registry.

Holds the in-memory cache of `_entity_schemas` documents and the Pydantic
models built from them. `load()` also rebinds the per-app
`app.core.models.users.UserResource` module attribute (built from
`_app_settings.additional_user_data_schema`) so all importers that do
`from app.core.models import users; users.UserResource(...)` get the live
class.

- `_schemas[name]`             — raw schema doc.
- `_response_models[name]`     — full response model (schema fields
                                  followed by server-stamp fields per
                                  Base44's probed wire order). Used to
                                  serialize Mongo docs for REST/realtime
                                  wire output.
- `_body_models[name]`         — schema-only model (no stamps). Used to
                                  validate request bodies on CREATE/UPDATE;
                                  server-stamp fields are managed by the
                                  service layer and must not be required on
                                  the body.
- `_body_models_allow_extra['User']` — same as above with
                                  `extra='allow'` for `PUT /entities/User/me`.

`load()` runs once at lifespan startup. Schemas and
additional_user_data_schema are immutable per-deployment, so there's no
reload path.
"""

from pydantic import BaseModel

from app.core import db
from app.core.models import users as _users
from app.core.models.entities import (
    build_entity_body_model,
    build_entity_body_model_partial,
    build_entity_model,
)
from app.core.models.users import build_user_resource


_schemas: dict[str, dict] = {}
_response_models: dict[str, type[BaseModel]] = {}
_body_models: dict[str, type[BaseModel]] = {}
_body_models_allow_extra: dict[str, type[BaseModel]] = {}
_body_models_partial: dict[str, type[BaseModel]] = {}
_body_models_partial_allow_extra: dict[str, type[BaseModel]] = {}


async def load() -> None:
    _schemas.clear()
    _response_models.clear()
    _body_models.clear()
    _body_models_allow_extra.clear()
    _body_models_partial.clear()
    _body_models_partial_allow_extra.clear()
    async for doc in db.coll("_entity_schemas").find():
        name = doc["name"]
        _schemas[name] = doc
        # Response model is `extra="allow"`: surfaces Mongo-resident fields
        # outside the schema (set via `/User/me` PUT extras, `update-many` raw
        # `$set`, or anything else that bypasses Pydantic). Body model stays
        # `extra="ignore"` so writes through normal CRUD reject unknown fields
        # — User/me's `extra="allow"` body lives in `_body_models_allow_extra`.
        _response_models[name] = build_entity_model(name, doc, extra_mode="allow")
        _body_models[name] = build_entity_body_model(name, doc, extra_mode="ignore")
        # Partial-body model: every field Optional. Used by PUT paths; Base44
        # accepts partial updates that omit required fields (F-008). Per-field
        # type checks still apply for fields the client DOES send.
        _body_models_partial[name] = build_entity_body_model_partial(
            name, doc, extra_mode="ignore",
        )
        if name == "User":
            _body_models_allow_extra[name] = build_entity_body_model(
                name, doc, extra_mode="allow",
            )
            _body_models_partial_allow_extra[name] = build_entity_body_model_partial(
                name, doc, extra_mode="allow",
            )

    app_settings = await db.app_settings()
    # Rebind the module attribute so importers that did
    # `from app.core.models import users` see the live class via
    # `users.UserResource(...)`.
    _users.UserResource = build_user_resource(
        app_settings.get("additional_user_data_schema"),
    )


def get(entity_name: str) -> dict | None:
    return _schemas.get(entity_name)


def response_model(entity_name: str) -> type[BaseModel] | None:
    return _response_models.get(entity_name)


def body_model(entity_name: str, *, allow_extra: bool = False) -> type[BaseModel] | None:
    if allow_extra:
        return _body_models_allow_extra.get(entity_name) or _body_models.get(entity_name)
    return _body_models.get(entity_name)


def body_model_partial(entity_name: str, *, allow_extra: bool = False) -> type[BaseModel] | None:
    """Per-entity body model where every field is Optional. For PUT paths.

    Base44 accepts partial PUT bodies that omit required fields (F-008,
    probed 2026-05-22 against `positive-flow-state-labs.base44.app`). The
    full `body_model` is wrong for PUT because it enforces Pydantic's
    required-marker on schema-required fields. Per-field type checks
    still apply via the Optional[X] annotation.
    """
    if allow_extra:
        return (
            _body_models_partial_allow_extra.get(entity_name)
            or _body_models_partial.get(entity_name)
        )
    return _body_models_partial.get(entity_name)


def exists(entity_name: str) -> bool:
    return entity_name in _schemas


def all_names() -> list[str]:
    return list(_schemas.keys())
