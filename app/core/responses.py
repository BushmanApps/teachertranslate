"""
Server-owned field stamping and entity serialization.

Datetime formatting is handled by orjson at the HTTP boundary (OPT_UTC_Z),
not here. serialize_entity only does key remapping and field stripping.
"""

from datetime import datetime, timezone

from bson import ObjectId


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stamp_on_create(record: dict, ctx) -> dict:
    """Add server-owned fields to a new entity record — its id among them:
    Base44 judges a create rule on the record with its id on it (measured
    2026-10-21: `{"id": null}` refuses a create, `{"id": {"$ne": null}}`
    allows it)."""
    created_by = "anonymous"
    created_by_id = "anonymous"

    if ctx.token_class == "service_role" and ctx.service_principal:
        created_by_id = f"service_{ctx.service_principal['sub']}"
        created_by = f"service+{ctx.service_principal['sub']}@no-reply.base44.com"
    elif ctx.user:
        created_by = ctx.user["email"]
        created_by_id = ctx.user["id"]

    record["created_by"] = created_by
    record["created_by_id"] = created_by_id
    record["created_date"] = utcnow()
    record["updated_date"] = utcnow()
    record["is_sample"] = False
    record["_id"] = ObjectId()
    return record


def app_settings_to_runtime(doc: dict) -> dict:
    """Map an `_app_settings` Mongo document to the dict shape `RuntimeApp`
    expects on construction.

    Translates Mongo's `_id` (ObjectId) to `id` (string). Everything else
    flows through verbatim — `RuntimeApp`'s `extra='ignore'` drops the
    22 UserApp-only fields naturally.
    """
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    return out


def doc_to_entity_input(doc: dict) -> dict:
    """Map a Mongo entity document to the dict shape a dynamic entity
    model expects on construction.

    Same `_id` -> `id` translation as `app_settings_to_runtime`. Kept
    distinct so call-sites read at the right semantic layer.
    """
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    return out


def serialize_entity(doc: dict, *, hide_created_by: bool = False) -> dict:
    """Convert a Mongo document to the API response shape.

    - _id (ObjectId) → id (string), preserving storage position when a
      stored `id` field exists (M-009 User docs); otherwise emits `id` at
      `_id`'s original position.
    - environment is always stripped
    - created_by is stripped when hide_created_by is True
    - datetime values pass through — orjson handles formatting at the HTTP boundary

    Position-preserving _id handling matters for User docs after M-009:
    the migrator + `build_new_user_doc` stamp `id` as a doc field at its
    canonical position. If `serialize_entity` were to write `id` at `_id`'s
    position (always slot 0 for Mongo docs), the stored `id` field would
    later collapse onto slot 0 too (Python dict `out["id"] = ...` updates
    value at the existing slot), corrupting the field order downstream
    consumers (`user_doc_to_userresource_input`) compute their boundary
    from. F-017 captures the original divergence.
    """
    has_stored_id = "id" in doc
    out: dict = {}
    for key, value in doc.items():
        if key == "_id":
            if has_stored_id:
                # The stored `id` doc field carries the canonical value;
                # let it land at its original storage position below.
                continue
            out["id"] = str(value)
        elif key == "environment":
            continue
        elif key == "created_by" and hide_created_by:
            continue
        else:
            out[key] = value
    return out


# serialize_entities + serialize_for_realtime removed in Phase 10.
# Entity-CRUD paths now use the dynamic entity models from
# `app.core.models.entities` (registry.response_model). The RLS-input
# `_id` -> `id` mapper lives in `entities/helpers.py:serialize_for_rls`.
# `serialize_entity` above is still used by pipeline.py / deps.py /
# agents/executor.py for generic Mongo-doc serialization.
