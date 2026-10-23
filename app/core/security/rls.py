"""
Row-Level Security engine.

Public interface:

    filter_for_read(ctx, entity_name) -> dict
        Returns a logical query filter to AND into list queries.
        Uses `id` as the logical primary-key key; the entities/query layer
        is responsible for translating `id` → `_id` (ObjectId) for Mongo.

    filter_for_update(ctx, entity_name) -> dict
        The same for the update rule (an upsert looks for its row among them).

    can_read(ctx, entity_name, record) -> bool
        The read rule, asked about one row already in hand.

    assert_can_create(ctx, entity_name, record) -> None
        Raises permission_denied() if RLS denies the create. `record` is the
        row as it will be stored, server stamps and its new id included, in
        its RLS shape (`serialize_for_rls`) — not the raw body.

    assert_can_update(ctx, entity_name, existing_row) -> None
        Raises permission_denied() if RLS denies the update.

    assert_can_delete(ctx, entity_name, existing_row) -> None
        Raises permission_denied() or entity_not_found() per the masking rules.

THE MODEL — measured on Base44 2026-10-21 (research/divergence-chasing/
2026-10-21-rls-empty-values/: four fixture apps, every shape read, counted,
created, updated and deleted as a signed-in user and as a visitor). It
replaces the 2026-08-01 table ("an unresolvable template drops the
condition"), which Base44's 2026-09-02 change ("Row-level security denies an
empty value") made wrong — the fork kept serving those rows to everyone.

A rule is a condition on the row, built from field conditions combined by
$and / $or / $nor (a dict's keys are AND-ed), and a condition has THREE
answers: true, false, or UNKNOWN. A row is served — a write allowed — only
where the rule is TRUE. Unknown is what a condition about the user is when
there is no user to compare: it is never true, and neither is its negation.

1. The key — what the condition reads off the row:
   - `data.<field>`, `created_by`, `created_by_id`, `id`, `app_id`,
     `environment`, `is_sample`: stored on the row;
   - `entity_name`, `is_deleted`, `deleted_date` (documented, not stored by
     the fork): the entity's name, false, null on every live row;
   - any other key (a custom field written without `data.`, `base44.<X>`,
     `user.<x>`, `is_service_role`): a field no row has — the condition is
     decided against a MISSING value, the way Base44's engine reads it:
     `{"org": null}` holds for every row, `{"org": "acme"}` for none.
   A CREATE is judged on the record with its new id on it and before the
   platform's own fields are: `is_sample`, `entity_name`, `is_deleted`,
   `deleted_date` are missing then (`{"is_sample": false}` serves every row,
   allows its update and delete, and refuses every create; `{"id": null}`
   refuses a create, `{"id": {"$ne": null}}` allows one).
   A field of the entity's schema is on every row for Base44's reads, null
   where it was never set (`{"data.x": {"$exists": true}}` serves every row).

2. The value — a `{{user.*}}` template (`email`, `id`, `role` and the other
   built-in fields at the top level; the app's custom fields only as
   `data.<field>` — `{{user.<custom>}}` never resolves):
   - nobody signed in: the condition is UNKNOWN. `$or` with another branch
     still serves through it (a public branch serves a visitor); `$nor`,
     `$not`, `$ne`, `$nin` over it serve nothing;
   - signed in, the value missing or null: the condition is never true;
     under a negation ($nor, $not) it keeps its old meaning, "the field is
     null" — so `$nor[{"data.org": <missing>}]` serves the rows whose org is
     set (Base44's 2026-09-02 fix reached only the positive side);
   - `""`, `0`, `false`, `[]` are values;
   - an item of an `$in` list that does not resolve is dropped and the
     other items still decide (on a negation a signed-in user's null item
     keeps its old meaning there too);
   - a whole user value as an `$in` (`{"$in": "{{user.data.teams}}"}`):
     its items are what the value holds — a list, one value as a one-item
     list, none when it is null or missing or nobody is signed in — and the
     `$in` is two-valued over them (under `$nor`, a null list serves every
     row); under `$nin` one value is a one-item list too;
   - a template embedded in a longer string that does not resolve leaves a
     string no row holds.

3. `user_condition`: compared literally against the signed-in user (an
   allowlist of keys — `role`, `email`, `id`, `data.<field>`; templates are
   not substituted in it); nobody signed in → UNKNOWN.

4. Operators: $eq $ne $in $nin $all $exists $regex $not $gt $gte $lt $lte
   $elemMatch. Anything else, or an operand of the wrong shape, is UNKNOWN:
   read filters reach Mongo, and an unvetted operator would hand a rule
   author our query engine (and a negation of it must not open the rows).

5. Base44 judges a WRITE with another evaluator than a read: it knows plain
   equality, `$ne`, `$in`, `$nin` and the logical keys; every other operator
   ($eq, $all, $exists, $regex, $gt, $gte, $lt, $lte, $not, $elemMatch)
   refuses a create or update even of a row it matches (measured on the
   fourth fixture, the `W_*` entities — a rule can serve a row on a read and
   refuse its update). The engine has one model; the write answer differs for
   exactly those operators.

Who RLS applies to:
- app_user / preview / anonymous -> enforced.
- service_role -> EXEMPT. `base44.asServiceRole.*` is admin context on
  Base44 and no rule is evaluated for it. Measured 2026-08-01 from inside a
  deployed Base44 function: `asServiceRole.entities.X.create` succeeded
  against a rule pinned to a foreign `created_by_id` (a condition nothing can
  satisfy), and `asServiceRole.entities.Y.list()` returned rows whose
  `created_by_id` is an app user under the rule `created_by_id ==
  {{user.id}}` — impossible under RLS. The same function's non-service
  `base44.entities.X.create` 403'd in the same request, so RLS was live.
  The SDK sends no bypass header; the service token itself is privileged.
  FLS is NOT exempt (paired-probe 2026-05-24: a service-role write to a
  field-denied column 403s on Base44 too), which is why this lives here and
  not in fls.py.
  Enforcing RLS on service_role instead is not a smaller mistake than
  leaking: it silently empties every read a backend function makes. On one
  real app (290 asServiceRole call sites) `Activity.list()` returned 0 rows
  where Base44 returns 2,342.

Denial masking:
- list: filtered (no error)
- get: masked 404
- create: explicit 403
- update: explicit 403
- delete: masked 404 — unless the delete rule, read the way a read reads it,
  finds the row and the write evaluator refuses it: then 403 "Permission
  denied for delete operation on X entity" (measured 2026-10-21: `read: true,
  delete: {created_by: <someone else>}` answers 404; `{"data.x": {"$exists":
  true}}` for all four operations answers 403 on a delete)
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

from app.core.errors import entity_not_found, permission_denied
from app.core.schema import registry


_ALLOW = object()   # the filter that serves every row
_DENY = object()    # the filter that serves none
_MISSING = object()
_DENY_FILTER = {"$nor": [{}]}
_TEMPLATE_RE = re.compile(r"\{\{user\.([A-Za-z0-9_.]+)\}\}")

# Keys a condition reads off the stored row (`data.<field>` besides).
_STORED_KEYS = frozenset({"app_id", "created_by", "created_by_id", "environment", "id", "is_sample"})
# Documented keys the fork does not store: their value on every live row.
_KNOWN_KEYS = {"is_deleted": False, "deleted_date": None}
# The platform's own fields, not yet on a record that is being created.
_PLATFORM_KEYS = frozenset({"is_sample", "entity_name", "is_deleted", "deleted_date"})

# Empirically-observed allowlist of top-level principal keys that Base44's
# runtime looks up inside a `user_condition` expression. Probed against
# Base44 production: `{role}`, `{email}`, `{id}` evaluate; `{_app_role}`,
# `{full_name}`, etc. do NOT match (Base44 returns the rule's deny outcome
# regardless of the principal's actual value for those keys). `data.<x>`
# custom fields are handled separately and stay supported.
_USER_CONDITION_KEYS = frozenset({"role", "email", "id"})

_OPERATORS = frozenset({
    "$eq", "$ne", "$in", "$nin", "$all", "$exists",
    "$regex", "$not", "$gt", "$gte", "$lt", "$lte", "$elemMatch",
})
_LIST_OPERATORS = frozenset({"$in", "$nin", "$all"})


def _rls_exempt(ctx) -> bool:
    """Callers RLS is not evaluated for.

    Two of them, for different reasons:
    - `bypass_rls` — F-007's `X-Bypass-RLS: true`. The admin check and the
      raise-on-non-admin happen in pipeline at context-build time; here we
      just trust the flag.
    - `service_role` — `asServiceRole` is admin context on Base44 and takes
      no header to get there. See the module docstring for the measurement.
    """
    return (
        getattr(ctx, "bypass_rls", False)
        or getattr(ctx, "token_class", None) == "service_role"
    )


def filter_for_read(ctx, entity_name: str) -> dict:
    if _rls_exempt(ctx):
        return {}
    return _as_filter(_compile_rule(_entity_rule(entity_name, "read"), ctx.principal, entity_name))


def filter_for_update(ctx, entity_name: str) -> dict:
    """The rows the caller may update, as a filter — for a caller that is
    LOOKING for the row to update (an upsert matches a record to a row among
    the rows its caller may read and update)."""
    if _rls_exempt(ctx):
        return {}
    return _as_filter(_compile_rule(_entity_rule(entity_name, "update"), ctx.principal, entity_name))


def can_read(ctx, entity_name: str, record: dict) -> bool:
    """One row, one reader. The twin of `filter_for_read` for a caller that
    already holds the row and asks about one reader at a time — a realtime
    event going out to each listener of a room (core/realtime.py). Decided by
    the same model on the row in its RLS shape (`serialize_for_rls`)."""
    if _rls_exempt(ctx):
        return True
    return _rule_allows(_entity_rule(entity_name, "read"), record, ctx.principal, entity_name=entity_name)


def assert_can_create(ctx, entity_name: str, record: dict, *, one_of_many: bool = False) -> None:
    # `record` is the row AS IT WILL BE STORED — server stamps and its new id
    # included, in its RLS shape. Base44 evaluates create rules against the
    # stored record, so a rule keyed on `created_by_id`/`created_by` (the single
    # most common shape there is) only decides correctly once those are
    # present. See services.create().
    #
    # `one_of_many`: the record is one of a call's several (a bulk create, an
    # upsert) — the refusal says so (measured 2026-09-29).
    if _rls_exempt(ctx):
        return
    rule = _entity_rule(entity_name, "create")
    if not _rule_allows(rule, record, ctx.principal, entity_name=entity_name, write=True, creating=True):
        refusal = permission_denied(entity_name, "create")
        if one_of_many:
            refusal.detail = "You don't have permission to create some of these entities."
        raise refusal


def assert_can_update(ctx, entity_name: str, existing_row: dict) -> None:
    if _rls_exempt(ctx):
        return
    if not _rule_allows(_entity_rule(entity_name, "update"), existing_row, ctx.principal, entity_name=entity_name, write=True):
        raise permission_denied(entity_name, "update")


def assert_can_delete(ctx, entity_name: str, existing_row: dict) -> None:
    if _rls_exempt(ctx):
        return
    rule = _entity_rule(entity_name, "delete")
    if _rule_allows(rule, existing_row, ctx.principal, entity_name=entity_name, write=True):
        return
    # Base44 looks the row up through the delete rule as it reads, then judges
    # it with its write evaluator: a row the lookup finds and the judge refuses
    # is refused out loud, any other is not there at all.
    if _rule_allows(rule, existing_row, ctx.principal, entity_name=entity_name):
        raise permission_denied(entity_name, "delete")
    raise entity_not_found(entity_name, _record_id(existing_row))


def _entity_rule(entity_name: str, op: str):
    schema = registry.get(entity_name) or {}
    rules = schema.get("rls") or {}
    if op in {"update", "delete"} and op not in rules and "write" in rules:
        return rules["write"]
    return rules.get(op)


def _as_filter(compiled) -> dict:
    if compiled is _ALLOW:
        return {}
    if compiled is _DENY:
        return dict(_DENY_FILTER)
    return compiled


def _compile_rule(rule, principal, entity_name: str | None = None):
    """A rule as the filter of the rows it serves: `_ALLOW`, `_DENY`, or a
    Mongo filter."""
    if rule is None or rule is True:
        return _ALLOW
    if rule is False or not isinstance(rule, dict):
        return _DENY
    return _condition(rule, principal, _Rows(entity_name)).t


def _rule_allows(rule, record: dict, principal, *, entity_name: str | None = None, write: bool = False, creating: bool = False) -> bool:
    """The rule decided on one row in hand: a read of it (`write=False` — a
    realtime listener, a field's read rule) or a write (`write=True`, and
    `creating` for a record not yet stored)."""
    if rule is None or rule is True:
        return True
    if rule is False or not isinstance(rule, dict):
        return False
    return _condition(rule, principal, _Row(entity_name, record, write=write, creating=creating)).t is True


# ── The model ────────────────────────────────────────────────────────────────
#
# A condition is compiled to the pair of where it is TRUE and where it is
# FALSE; where neither, it is unknown. `$and`/`$or`/`$nor` combine pairs
# (Kleene's three-valued logic), `$not` swaps one. The same functions build
# both answers through an algebra: `_Rows` makes the parts Mongo filters over
# the stored rows (a read), `_Row` makes them booleans about one row in hand.

class _Cond(NamedTuple):
    t: Any   # where the condition is true
    f: Any   # where it is false


class _Rows:
    """A condition's parts as Mongo filters over the entity's stored rows."""

    TRUE, FALSE = _ALLOW, _DENY
    write = False
    creating = False

    def __init__(self, entity_name: str | None):
        self.entity_name = entity_name
        self.schema_fields = _schema_fields(entity_name)

    @staticmethod
    def all_of(items):
        parts = []
        for item in items:
            if item is _DENY:
                return _DENY
            if item is _ALLOW:
                continue
            parts.extend(item["$and"] if set(item) == {"$and"} else [item])
        if not parts:
            return _ALLOW
        if len(parts) > 1 and all(set(part) == {"$nor"} for part in parts):
            return {"$nor": [branch for part in parts for branch in part["$nor"]]}   # ¬a ∧ ¬b is ¬(a ∨ b)
        return parts[0] if len(parts) == 1 else {"$and": parts}

    @staticmethod
    def any_of(items):
        parts = []
        for item in items:
            if item is _ALLOW:
                return _ALLOW
            if item is not _DENY:
                parts.append(item)
        if not parts:
            return _DENY
        return parts[0] if len(parts) == 1 else {"$or": parts}

    @staticmethod
    def negate(item):
        if item is _ALLOW:
            return _DENY
        if item is _DENY:
            return _ALLOW
        if set(item) == {"$nor"}:
            return _Rows.any_of(item["$nor"])
        return {"$nor": [item]}

    def stored(self, field: str, expr):
        if isinstance(expr, dict) and "$exists" in expr and field in self.schema_fields:
            # Every field of the schema is on every row Base44 reads (null
            # where never set): it exists, whatever the row was created with.
            return _ALLOW if bool(expr["$exists"]) else _DENY
        return {field: expr}

    def known(self, value, expr):
        return _ALLOW if _match(value, expr, write=False) else _DENY


class _Row:
    """A condition's parts as booleans about one row in hand."""

    TRUE, FALSE = True, False

    def __init__(self, entity_name: str | None, record: dict, *, write: bool, creating: bool):
        self.entity_name = entity_name
        self.schema_fields = _schema_fields(entity_name)
        self.record = record
        self.write = write
        self.creating = creating

    all_of = staticmethod(lambda items: all(items))
    any_of = staticmethod(lambda items: any(items))
    negate = staticmethod(lambda item: not item)

    def stored(self, field: str, expr):
        return _match(_lookup(self.record, field), expr, write=self.write, present=field in self.schema_fields)

    def known(self, value, expr):
        return _match(value, expr, write=self.write)


def _schema_fields(entity_name: str | None) -> frozenset:
    if not entity_name:
        return frozenset()
    return frozenset(((registry.get(entity_name) or {}).get("properties") or {}))


def _unknown(alg) -> _Cond:
    return _Cond(alg.FALSE, alg.FALSE)


def _decided(alg, holds: bool) -> _Cond:
    return _Cond(alg.TRUE, alg.FALSE) if holds else _Cond(alg.FALSE, alg.TRUE)


def _condition(condition, principal, alg) -> _Cond:
    if not isinstance(condition, dict):
        return _unknown(alg)
    parts = []
    for key, value in condition.items():
        if key in ("$and", "$or", "$nor"):
            if not isinstance(value, list):
                parts.append(_unknown(alg))
                continue
            children = [_condition(item, principal, alg) for item in value]
            ts, fs = [c.t for c in children], [c.f for c in children]
            if key == "$and":
                parts.append(_Cond(alg.all_of(ts), alg.any_of(fs)))
            elif key == "$or":
                parts.append(_Cond(alg.any_of(ts), alg.all_of(fs)))
            else:
                parts.append(_Cond(alg.all_of(fs), alg.any_of(ts)))
        elif key == "user_condition":
            parts.append(_unknown(alg) if principal is None else _decided(alg, _evaluate_user_condition(value, principal)))
        else:
            parts.append(_field_condition(key, value, principal, alg))
    return _Cond(alg.all_of([p.t for p in parts]), alg.any_of([p.f for p in parts]))


def _field_condition(key: str, value, principal, alg) -> _Cond:
    target = _target(key, alg)
    if isinstance(value, dict) and value and all(k.startswith("$") for k in value):
        parts = [_operator(target, op, operand, principal, alg) for op, operand in value.items()]
        return _Cond(alg.all_of([p.t for p in parts]), alg.any_of([p.f for p in parts]))
    if isinstance(value, dict) and (not value or any(k.startswith("$") for k in value)):
        return _unknown(alg)
    return _compare(target, None, value, principal, alg)


def _target(key: str, alg) -> tuple[str, Any]:
    """What a condition's key reads: ("stored", <field>) or ("known", <value>)."""
    if alg.creating and key in _PLATFORM_KEYS:
        return ("known", _MISSING)
    if key.startswith("data.") and len(key) > 5:
        return ("stored", key[5:])
    if key in _STORED_KEYS:
        return ("stored", key)
    if key == "entity_name":
        return ("known", alg.entity_name if alg.entity_name is not None else _MISSING)
    if key in _KNOWN_KEYS:
        return ("known", _KNOWN_KEYS[key])
    return ("known", _MISSING)


def _decide(target, expr, alg):
    kind, where = target
    return alg.stored(where, expr) if kind == "stored" else alg.known(where, expr)


def _operator(target, op: str, operand, principal, alg) -> _Cond:
    if op not in _OPERATORS:
        return _unknown(alg)
    if op == "$not":
        if not (isinstance(operand, dict) and operand and all(k.startswith("$") for k in operand)):
            return _unknown(alg)
        if alg.write:
            return _Cond(alg.FALSE, alg.TRUE)   # Base44's write evaluator has no $not: false, not negated
        parts = [_operator(target, inner_op, inner_operand, principal, alg) for inner_op, inner_operand in operand.items()]
        return _Cond(alg.any_of([p.f for p in parts]), alg.all_of([p.t for p in parts]))
    if op == "$in" and isinstance(operand, list):
        return _in_list(target, operand, principal, alg)
    if op == "$in" and _whole_template(operand):
        return _in_user_value(target, operand, principal, alg)
    return _compare(target, op, operand, principal, alg)


def _compare(target, op: str | None, operand, principal, alg) -> _Cond:
    sub = _substitute(operand, principal)
    if sub.nouser:
        return _unknown(alg)
    if sub.never:
        return _Cond(alg.FALSE, alg.TRUE)
    value = sub.value
    if op in _LIST_OPERATORS and value is not None and not isinstance(value, list) and _whole_template(operand):
        # A user field that holds one value where a list belongs is that one
        # value as a list (measured on `$nin`: `N_nin_list_string`; `$in` over
        # a whole user value is `_in_user_value`).
        value = [value]
    if not _well_formed(op, value):
        return _unknown(alg)
    holds = _decide(target, value if op is None else {op: value}, alg)
    if sub.empty:
        # Base44 2026-09-02: a value that is missing or null is never matched;
        # a negation still reads the condition the old way, "equals null".
        return _Cond(alg.FALSE, alg.negate(holds))
    return _Cond(holds, alg.negate(holds))


def _in_list(target, items: list, principal, alg) -> _Cond:
    """`$in` over a list: an item that does not resolve is dropped and the
    others still decide; on the negated side a signed-in user's null item
    keeps its old meaning (measured: `P_in_missing`, `N_nor_in_missing`)."""
    true_items, false_items = [], []
    for item in items:
        sub = _substitute(item, principal)
        if sub.nouser or sub.never:
            continue
        if sub.empty:
            false_items.append(None)
            continue
        true_items.append(sub.value)
        false_items.append(sub.value)
    holds = _decide(target, {"$in": true_items}, alg) if true_items else alg.FALSE
    held_before = holds if false_items == true_items else _decide(target, {"$in": false_items}, alg)
    return _Cond(holds, alg.negate(held_before))


def _in_user_value(target, operand: str, principal, alg) -> _Cond:
    """`$in` over a whole user value (`{"$in": "{{user.data.teams}}"}`): its
    items are what the value holds — a list, one value as a one-item list, none
    when the value is null or missing or nobody is signed in — and the `$in` is
    two-valued over them, like a list whose unresolved items were dropped
    (measured: `N_in_list*`, `N_nor_in_list*` — a null list under `$nor`
    serves every row)."""
    sub = _substitute(operand, principal)
    items = [] if sub.nouser or sub.empty else sub.value if isinstance(sub.value, list) else [sub.value]
    holds = _decide(target, {"$in": items}, alg) if items else alg.FALSE
    return _Cond(holds, alg.negate(holds))


def _whole_template(operand) -> bool:
    return isinstance(operand, str) and _TEMPLATE_RE.fullmatch(operand) is not None


def _well_formed(op: str | None, operand) -> bool:
    if op in _LIST_OPERATORS:
        return isinstance(operand, list)
    if op == "$regex":
        if not isinstance(operand, str):
            return False
        try:
            re.compile(operand)
        except re.error:
            return False
    if op == "$elemMatch":
        return isinstance(operand, dict) and bool(operand)
    return True


# ── {{user.*}} templates ─────────────────────────────────────────────────────

class _Sub(NamedTuple):
    value: Any      # the operand with its templates put in (a missing or null value as None)
    empty: bool     # a template met a signed-in user whose value is missing or null
    nouser: bool    # a template met no user at all
    never: bool     # a template inside a longer string did not resolve: no row holds that string

    @property
    def resolved(self) -> bool:
        return not (self.empty or self.nouser or self.never)


_NOUSER = object()
_EMPTY = object()


def _user_value(principal, path: str):
    if principal is None:
        return _NOUSER
    if path.startswith("data."):
        value = (principal.get("data") or {}).get(path[5:])
    else:
        value = principal.get(path)
    return _EMPTY if value is None else value


def _substitute(value, principal) -> _Sub:
    if isinstance(value, str):
        matches = list(_TEMPLATE_RE.finditer(value))
        if not matches:
            return _Sub(value, False, False, False)
        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            resolved = _user_value(principal, matches[0].group(1))
            if resolved is _NOUSER:
                return _Sub(None, False, True, False)
            if resolved is _EMPTY:
                return _Sub(None, True, False, False)
            return _Sub(resolved, False, False, False)
        pieces, cursor = [], 0
        for match in matches:
            resolved = _user_value(principal, match.group(1))
            if resolved is _NOUSER or resolved is _EMPTY:
                return _Sub(value, False, False, True)
            pieces += [value[cursor:match.start()], str(resolved)]
            cursor = match.end()
        pieces.append(value[cursor:])
        return _Sub("".join(pieces), False, False, False)
    if isinstance(value, (list, dict)):
        items = value.items() if isinstance(value, dict) else enumerate(value)
        subs = {k: _substitute(v, principal) for k, v in items}
        out = {k: s.value for k, s in subs.items()} if isinstance(value, dict) else [s.value for s in subs.values()]
        return _Sub(out, any(s.empty for s in subs.values()), any(s.nouser for s in subs.values()), any(s.never for s in subs.values()))
    return _Sub(value, False, False, False)


# ── One value against a condition, the way Mongo matches it ──────────────────

def _lookup(record: dict, field: str):
    if field in record:
        return record[field]
    value = record
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _match(value, expr, *, write: bool, present: bool = False) -> bool:
    """Whether `value` (the row's, or `_MISSING`) satisfies `expr` — a plain
    value (equality) or an operator dict. `present`: the field is one of the
    schema's, on every row Base44 reads whatever it holds."""
    if isinstance(expr, dict) and expr and all(k.startswith("$") for k in expr):
        return all(_operator_match(value, op, operand, write=write, present=present) for op, operand in expr.items())
    return _equals(value, expr, write=write)


def _equals(value, expected, *, write: bool = False) -> bool:
    if expected is None:
        return value is _MISSING or value is None
    if value is _MISSING or value is None:
        return False
    if isinstance(value, list) and not isinstance(expected, list) and not write:
        return any(_same(item, expected) for item in value)   # an array matches its members
    return _same(value, expected)


def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def _operator_match(value, op: str, operand, *, write: bool, present: bool) -> bool:
    if op == "$ne":
        return not _equals(value, operand, write=write)
    if op == "$in":
        return isinstance(operand, list) and any(_equals(value, item, write=write) for item in operand)
    if op == "$nin":
        return isinstance(operand, list) and not any(_equals(value, item, write=write) for item in operand)
    if write:
        # Base44's write evaluator knows $ne, $in and $nin and no other
        # operator: every other one refuses, on a row it matches (measured).
        return False
    if op == "$eq":
        return _equals(value, operand)
    if op == "$all":
        return isinstance(value, list) and isinstance(operand, list) and all(any(_same(v, item) for v in value) for item in operand)
    if op == "$exists":
        return (value is not _MISSING or present) == bool(operand)
    if op == "$regex":
        if not isinstance(value, str) or not isinstance(operand, str):
            return False
        try:
            return re.search(operand, value) is not None
        except re.error:
            return False
    if op in {"$gt", "$gte", "$lt", "$lte"}:
        return value is not _MISSING and value is not None and _compare_values(op, value, operand)
    if op == "$not":
        return isinstance(operand, dict) and not _match(value, operand, write=False, present=present)
    if op == "$elemMatch":
        return isinstance(value, list) and isinstance(operand, dict) and any(_element_matches(item, operand) for item in value)
    return False


def _element_matches(item, condition: dict) -> bool:
    if all(k.startswith("$") for k in condition):
        return _match(item, condition, write=False)
    return isinstance(item, dict) and all(_match(_lookup(item, k), v, write=False) for k, v in condition.items())


def _compare_values(op: str, left, right) -> bool:
    # Mongo compares across types by BSON type order; a rule comparing a string
    # to a number is a rule bug either way, so mismatches just don't match.
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        if not (isinstance(left, str) and isinstance(right, str)):
            return False
    if op == "$gt":
        return left > right
    if op == "$gte":
        return left >= right
    if op == "$lt":
        return left < right
    return left <= right


def _evaluate_user_condition(condition, principal) -> bool:
    """Evaluate a `user_condition` block.

    Same-decisions contract probed against Base44:

    1. Top-level keys are restricted to `_USER_CONDITION_KEYS`
       (`role`, `email`, `id`). Any other top-level key (e.g. `_app_role`,
       `full_name`, `disabled`) is treated as not-a-match: Base44 does not
       look those keys up here even when the principal carries them. So
       `{role: "admin"}` matches against `principal.role`, but
       `{_app_role: "admin"}` ALWAYS fails to match.
    2. `data.<x>` keys look up under `principal["data"]` (custom fields
       declared in `additional_user_data_schema`).
    3. Expected values are compared LITERALLY. Base44 does NOT substitute
       `{{user.*}}` templates inside user_condition values — `{id:
       "{{user.id}}"}` literally checks that the principal's id equals the
       seven-character string "{{user.id}}", which it never does. A null
       expected value matches a null user value (re-measured 2026-10-21).
    4. Operator-object values (e.g. `{role: {$in: ["admin"]}}`) are not
       supported and return False — Base44 has no probed precedent for them.
    """
    if not isinstance(condition, dict):
        return False
    if principal is None:
        return False

    for key, expected in condition.items():
        if isinstance(expected, dict):
            return False

        if key.startswith("data."):
            user_value = principal.get("data", {}).get(key[5:], _MISSING)
        elif key in _USER_CONDITION_KEYS:
            user_value = principal.get(key, _MISSING)
        else:
            return False

        if user_value is _MISSING:
            return False

        if user_value != expected:
            return False

    return True


def _record_id(record: dict) -> str:
    value = record.get("id", _MISSING)
    return "" if value is _MISSING else str(value)
