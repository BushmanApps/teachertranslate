"""
Field-Level Security engine — to be implemented by the security agent.

Public interface:

    mask_read_fields(ctx, entity_name, rows: list[dict]) -> list[dict]
        Strips denied fields from read results. Denied fields are omitted
        entirely (not set to null).

    validate_write_fields(ctx, entity_name, payload: dict, op: "create"|"update", held=) -> None
        Raises fls_write_deny() if the payload changes fields the caller
        cannot write. Validation is atomic: if ANY field is denied, the
        entire request fails before any DB write.

    validate_update_many(ctx, entity_name, data: dict) -> None
        The same for an update by operators (`$set`, `$unset`, …).

Field-level permission keys: read, write, create, update.
- "write" applies to both create and update.
- "create" and "update" are distinct (create-only protection, update-only protection).
- Field-level "delete" has no observable effect in production — do not implement.

Condition grammar is the same as RLS (user_condition, {{user.*}} templates, etc.)
but evaluated per-field using the field's rls property from the schema.

The service role is exempt from READ rules (it sees every field); for write
rules it is evaluated as an admin.
See security.md for full specification.
"""

from __future__ import annotations

from app.core.errors import fls_write_deny
from app.core.schema import registry
from app.core.security.rls import _rls_exempt, _rule_allows


def has_read_rules(entity_name: str) -> bool:
    """Whether any field of the entity carries a read rule. Base44 serves no
    aggregation — `distinct`, `aggregate` — on such an entity, to anyone."""
    properties = (registry.get(entity_name) or {}).get("properties") or {}
    return any(((field or {}).get("rls") or {}).get("read") is not None for field in properties.values())


def mask_read_fields(ctx, entity_name: str, rows: list[dict]) -> list[dict]:
    # The callers no rule is evaluated for see every field: `X-Bypass-RLS:
    # true` (F-007, probed against Base44 production 2026-05-22 — despite its
    # name the header lifts field rules too) and the SERVICE ROLE (measured
    # 2026-09-29 on the list, the filter, the get and the pages: a field
    # NOBODY may read is in the service role's rows. Until then the service
    # role passed only the rules an admin passes).
    if _rls_exempt(ctx):
        return list(rows)

    schema = registry.get(entity_name) or {}
    properties = schema.get("properties") or {}
    masked_rows = []

    for row in rows:
        masked_row = {}
        for key, value in row.items():
            field_schema = properties.get(key) or {}
            rule = ((field_schema.get("rls") or {}).get("read"))
            if _rule_allows(rule, row, ctx.principal, entity_name=entity_name):
                masked_row[key] = value
        masked_rows.append(masked_row)

    return masked_rows


def validate_write_fields(ctx, entity_name: str, payload: dict, op: str, *, held: dict | None = None) -> None:
    """Refuse a write that CHANGES a field its caller may not write.

    A field's write rule (`write`, or `create` / `update` for the one
    operation) guards the field's VALUE, not its mention — an app sends back
    the whole row it read, and that is no write of the fields it left alone.
    Measured on Base44's apps' host, 2026-09-29 (probe 05 of the entity
    chase, the "guard" and "field" cases), the same on the single routes, the
    bulk ones and upsert:

    - on a create, a field named as null is not written (a new row holds
      nothing; a field's DEFAULT named outright is a write like any value);
    - on an update, a field named with the value the row holds — `held`, the
      row as its reader is served it — is not written; null where the row
      holds a value is.

    A field with rules and none for the operation is written freely (probed
    2026-05-22). `X-Bypass-RLS: true` lifts every field rule (F-007).
    """
    if getattr(ctx, "bypass_rls", False):
        return

    properties = (registry.get(entity_name) or {}).get("properties") or {}
    denied = [
        key
        for key, value in payload.items()
        if key in properties
        and (value is not None if op == "create" else held is None or value != held.get(key))
        and not _rule_allows(_field_rule(properties[key], op), payload, ctx.principal,
                             entity_name=entity_name, write=True, creating=op == "create")
    ]
    if denied:
        raise fls_write_deny(denied, op)


def validate_update_many(ctx, entity_name: str, data: dict) -> None:
    """The same rule for an update that names its fields by operator
    (`{"$set": {…}, "$unset": {…}}`) and is applied to many rows at once: no
    row's value is looked at — a field the caller may not write is refused
    by its mention, whatever the rows hold (measured 2026-09-29: `$set` to
    the very value the row holds is refused, `$unset` too)."""
    if getattr(ctx, "bypass_rls", False):
        return

    properties = (registry.get(entity_name) or {}).get("properties") or {}
    named = {path.split(".", 1)[0] for fields in data.values() if isinstance(fields, dict) for path in fields}
    record = data.get("$set") if isinstance(data.get("$set"), dict) else {}
    denied = sorted(
        key for key in named
        if key in properties and not _rule_allows(_field_rule(properties[key], "update"), record, ctx.principal,
                                                  entity_name=entity_name, write=True)
    )
    if denied:
        raise fls_write_deny(denied, "update")


def _field_rule(field_schema: dict, op: str):
    rules = field_schema.get("rls") or {}
    if op in {"create", "update"} and op in rules:
        return rules[op]
    if op in {"create", "update"} and "write" in rules:
        return rules["write"]
    return None
