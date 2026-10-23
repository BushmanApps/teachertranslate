"""User-resource model — Base44's `User` Pydantic class.

Base44's User wire shape (probed 2026-05-21 against data-core-lab Daniel
across `/User/me`, `/entities/User`, list, GET, PUT and successive PUTs
adding new orphan fields) emits fields in this exact order:

    role,                                            # always first
    <declared customs from additional_user_data_schema, in declaration order>,
    <orphan extras from user_doc, in storage order>,  # includes `_app_role`
    id, created_date, updated_date, email, full_name,
    disabled, disabled_reason, is_verified, force_password_reset,
    app_id, is_service, collaborator_role

The 12 canonical built-ins that close the response (`id`...`collaborator_role`)
are NOT declared on `UserResource`; they enter as `extra='allow'` keys
whose wire position is dictated by their position in the input dict
constructed by `auth/helpers.py:user_doc_to_userresource_input`. Same
for `_app_role` — Base44 treats it as an extra, not a canonical built-in
(empirically confirmed: `_app_role`'s wire position tracks user-doc
insertion order alongside orphans, not the 12-built-ins canonical block).

Used by (via `from app.core.models import users as users_models;
users_models.UserResource(**input).model_dump(mode="json", exclude_unset=True)`):
- `GET /entities/User/me` and `PUT /entities/User/me`
- `GET /entities/User/{id}` and `GET /entities/User` (list)
- `POST /entities/User` (phantom create) and `POST /entities/User/bulk`
- `POST /auth/login` `user` field
- `POST /auth/change-password` success
- `POST /auth/reset-password` success
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, create_model



# Static placeholder: only `role` declared. The live class used at runtime
# is built per-app by `build_user_resource` below and adds the per-app
# custom-schema fields as additional declared fields. Everything else
# (the 12 canonical wire-trailing built-ins plus `_app_role` plus any
# orphan extras) flows through `extra='allow'` so `model_dump(mode="json")`
# emits them in input-insertion order. See
# `auth/helpers.py:user_doc_to_userresource_input` which constructs the
# input dict in Base44's exact wire field order.
class UserResourceBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str = "user"


# Module-level rebindable handle to the live per-app User Pydantic class.
# Lifespan reassigns `users.UserResource = build_user_resource(...)`. Call
# sites import the MODULE, not the name (`from app.core.models import users;
# users.UserResource(...)`) so the rebinding propagates — `from
# app.core.models.users import UserResource` would capture the placeholder
# at import time and never see the live class.
#
# Pre-lifespan value: UserResourceBase (the static role-only placeholder).
# Tests that don't touch the DB get a workable class either way.
UserResource: type[BaseModel] = UserResourceBase


def build_user_resource(
    additional_user_data_schema: Optional[dict],
) -> type[BaseModel]:
    """Build the live per-app User Pydantic class.

    Declares ONLY `role` + the per-app custom-schema fields. The 12
    canonical built-ins (id, created_date, updated_date, email, full_name,
    disabled, disabled_reason, is_verified, force_password_reset, app_id,
    is_service, collaborator_role) and `_app_role` are NOT declared — they
    enter as `extra='allow'` keys whose wire position is dictated by the
    input dict insertion order built by
    `auth/helpers.py:user_doc_to_userresource_input`.

    Field declaration order on the model = wire emission order for declared
    fields: role first, then customs in `additional_user_data_schema`
    declaration order. Pydantic v2's `model_dump(mode="json",
    exclude_unset=True)` emits declared fields first (in declaration order),
    then extras (in input-insertion order). Combined with the input-dict
    builder, this produces Base44's exact wire field order — empirically
    verified against `/User/me`, `/entities/User`, list, GET, PUT, and
    successive-PUT-with-new-orphans probes on 2026-05-21.

    Custom fields are typed `Optional[X] = None`. With `exclude_unset=True`
    on the dump, customs not present on the user doc are dropped — matches
    Base44 (unpopulated `total_queries`-style customs don't appear on the
    wire).
    """
    fields: dict[str, tuple[Any, Any]] = {"role": (str, "user")}

    properties = (additional_user_data_schema or {}).get("properties") or {}
    for fname, fdef in properties.items():
        if not isinstance(fdef, dict):
            continue
        if fname == "role":
            # `role` is already declared as a built-in. Skip the custom
            # duplicate (chat AI sometimes adds `role` to the additional
            # schema; the built-in declaration wins).
            continue
        # User custom fields are NOT type-coerced by Base44 — they round-trip
        # raw. Probed 2026-05-24 on ParityGym (`clearance_level`, schema
        # `number`): PUT `"5"`→`"5"`, `3.7`→`3.7`, `true`→`true`, `9`→`9`,
        # `"hello"`→`"hello"` (all 200, stored + emitted verbatim). The
        # `additional_user_data_schema` is documentation-only for User customs,
        # unlike entity schemas which ARE enforced. Typing as `Optional[X]`
        # (e.g. `Optional[float]` for a number) wrongly coerced int→float on
        # read (`1`→`1.0`). `Any` preserves the stored value; `exclude_unset`
        # still drops unset customs (matches B44 omitting unpopulated customs).
        fields[fname] = (Optional[Any], None)

    return create_model(  # type: ignore[call-overload]
        "UserResource",
        __config__=ConfigDict(extra="allow"),
        **fields,
    )
