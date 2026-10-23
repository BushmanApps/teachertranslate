"""Workflow definition compiler — validates the MEASURED Base44 subset and
produces an executable plan plus Base44's own content-addressed version id.

Every rule here was measured against Base44 production (2026-08-20..22); the
receipts are research/divergence-chasing/2026-08-19-workflows/HANDOFF.md,
cited per rule as (H §x.y). Two rules are OURS where Base44's exact static
rule is unmeasured beyond the observed shapes; both are marked OUR-RULE with
the reasoning inline. Do not add or relax rules from docs or intuition — only
from a probe.

Two modes, one validator:

- mode="validate" — full Base44-parity strictness. Used by the fork's
  validate/create routes (what a post-migration edit hits).
- mode="import"  — migration-time compile of a RECORD-BACKED definition.
  Base44 already accepted everything behind a workflow record, so a rule
  that polices style rather than executability (switch exhaustiveness,
  expression syntax outside `when`) downgrades to a warning: rejecting here
  would block an app Base44 demonstrably runs. Executability rules (the
  task-type/activity allowlist, transitions, structure) stay fatal in both
  modes — that is what makes the migration blocker capability-aware and
  precise instead of silently no-op'ing a construct we cannot run.

Standalone by design: stdlib + a LAZY jq import (the `workflows` optional
extra; per-app extras doctrine — see pyproject.toml). The grammar gate
(scripts/check-workflow-grammar.py) loads this file directly.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field

from .contract import (
    ACTIVITIES,
    BLOCKED_ACTIVITIES,
    DSL_MAJOR,
    NAMESPACE,
    TASK_TYPES,
)
from .jsonc import parse_jsonc

# The transition sentinel. Case-sensitive (`END` is INVALID_TRANSITION), and it
# wins over a task literally named "end" — that task never runs (H §3.4, §14.5).
END = "end"

# Task names must be jq-field-safe: space, dot and dash are all rejected by
# Base44 with INVALID_TASK_NAME ("Use snake_case…") (H §3.4). Accepting
# [A-Za-z0-9_]+ covers every measured acceptance; deliberately permissive at
# the unmeasured margins (digits-first) so a record-backed name can't be
# over-blocked.
_TASK_NAME = re.compile(r"^[A-Za-z0-9_]+$")


class WorkflowValidationError(Exception):
    """A definition rejected by the compiler. `code` mirrors Base44's coded
    errors where they were captured; where a rejection was measured but its
    code was not, the code is ours and stable."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass
class SwitchCase:
    when: str  # the jq body, unwrapped from ${ }
    then: str


@dataclass
class Task:
    name: str
    type: str  # "call" | "switch" | "wait"
    then: str | None = None  # call/wait only
    activity: str | None = None  # call only
    with_args: dict = field(default_factory=dict)  # call only
    wait: object = None  # wait only — raw value, dialect-parsed at RUNTIME (H §14.3)
    cases: list[SwitchCase] = field(default_factory=list)  # switch only
    x_base44: dict = field(default_factory=dict)


@dataclass
class CompiledWorkflow:
    definition: dict  # the parsed definition, verbatim — the hash input
    version_id: str  # Base44's own content-addressed id (H §5)
    tasks: dict[str, Task]  # insertion-ordered; execution starts at the first
    first_task: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class CompiledWorkflowFile:
    name: str
    description: str | None
    trigger: dict | None
    compiled: CompiledWorkflow


def version_id_for(definition: dict) -> str:
    """Base44's version id, reproduced bit-for-bit: verified on two unlike
    definitions against ids Base44 itself minted (H §5). The gate pins one."""
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_expression(value) -> bool:
    """A value is a jq expression iff it is a string of the form `${ … }`.
    Body may contain nested braces (jq object construction), so the wrapper is
    first-`${` to last-`}` (H §4.2 — `${ . }` args, §14.3 — expression waits)."""
    return isinstance(value, str) and value.startswith("${") and value.rstrip().endswith("}")


def expression_body(value: str) -> str:
    return value[2 : value.rstrip().rindex("}")]


def check_jq(expr_body: str) -> str | None:
    """Compile-check a jq body. Returns the jq error message, or None if it
    compiles. jq is a lazy import (the `workflows` extra); its absence raises
    so a misconfigured deploy fails loudly instead of skipping validation."""
    import jq  # lazy — per-app optional extra

    try:
        jq.compile(expr_body)
        return None
    except ValueError as e:
        return str(e)


def compile_workflow_source(source_text: str, *, mode: str = "validate") -> CompiledWorkflowFile:
    """Parse + compile a canonical `base44/workflows/*.jsonc` file."""
    try:
        doc = parse_jsonc(source_text)
    except ValueError as e:
        raise WorkflowValidationError("INVALID_JSON", f"workflow file is not valid JSONC: {e}")
    if not isinstance(doc, dict):
        raise WorkflowValidationError("INVALID_JSON", "workflow file must be a JSON object")
    name = doc.get("name")
    if not isinstance(name, str) or not name:
        raise WorkflowValidationError("MISSING_FIELD", "'name' is required")
    definition = doc.get("definition")
    if not isinstance(definition, dict):
        raise WorkflowValidationError("MISSING_FIELD", "'definition' is required")
    compiled = compile_definition(definition, mode=mode)
    trigger = doc.get("trigger")
    return CompiledWorkflowFile(
        name=name,
        description=doc.get("description") if isinstance(doc.get("description"), str) else None,
        trigger=trigger if isinstance(trigger, dict) else None,
        compiled=compiled,
    )


def compile_definition(definition: dict, *, mode: str = "validate") -> CompiledWorkflow:
    if mode not in ("validate", "import"):
        raise ValueError(f"unknown compile mode: {mode}")
    warnings: list[str] = []

    def style_violation(code: str, message: str) -> None:
        # Style rules: fatal at validate (Base44 parity), warning at import —
        # a record-backed definition already passed Base44's validator, so a
        # rejection here would over-block (see module docstring).
        if mode == "validate":
            raise WorkflowValidationError(code, message)
        warnings.append(f"{code}: {message}")

    # ── envelope (H §3.3) ──
    document = definition.get("document")
    if not isinstance(document, dict):
        raise WorkflowValidationError("MISSING_FIELD", "'document' is required")
    for key in ("dsl", "name", "version", "namespace"):
        if not isinstance(document.get(key), str) or not document.get(key):
            raise WorkflowValidationError("MISSING_FIELD", f"'document.{key}' is required")
    # dsl must be major version 1: '0.8' and '9.9.9' rejected, '1.0.0-alpha5'
    # accepted (H §3.3) — so the rule is the major, not a full-semver match.
    if not document["dsl"].startswith(f"{DSL_MAJOR}."):
        raise WorkflowValidationError(
            "UNSUPPORTED_DSL_VERSION",
            f"'{document['dsl']}' is not supported. Expected '{DSL_MAJOR}.x.x'",
        )
    if document["namespace"] != NAMESPACE:
        raise WorkflowValidationError(
            "INVALID_NAMESPACE", f"'document.namespace' must be '{NAMESPACE}'"
        )
    # Unknown top-level keys (input/output/timeout) are IGNORED, not rejected (H §3.3).

    do = definition.get("do")
    if not isinstance(do, list) or len(do) == 0:
        raise WorkflowValidationError("MISSING_FIELD", "'do' must be a non-empty list of tasks")

    # ── task entries and names (H §3.4) ──
    tasks: dict[str, Task] = {}
    for entry in do:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise WorkflowValidationError(
                "INVALID_TASK_ENTRY", "each 'do' entry must be an object with exactly one key"
            )
        task_name, body = next(iter(entry.items()))
        if not _TASK_NAME.match(task_name):
            raise WorkflowValidationError(
                "INVALID_TASK_NAME",
                f"Task name '{task_name}' contains characters incompatible with jq field access. Use snake_case",
            )
        if task_name in tasks:
            raise WorkflowValidationError("DUPLICATE_TASK", f"Duplicate task name '{task_name}'")
        if not isinstance(body, dict):
            raise WorkflowValidationError(
                "INVALID_TASK_ENTRY", f"Task '{task_name}' body must be an object"
            )
        tasks[task_name] = _compile_task(task_name, body, mode, style_violation, warnings)

    # ── transitions (H §3.4): a `then` names an existing task or the literal
    # `end`, case-sensitively ──
    for task in tasks.values():
        targets = [task.then] if task.then is not None else [c.then for c in task.cases]
        for target in targets:
            if target != END and target not in tasks:
                raise WorkflowValidationError(
                    "INVALID_TRANSITION",
                    f"Task '{task.name}' transitions to unknown task '{target}'",
                )

    _check_cycles(tasks)

    return CompiledWorkflow(
        definition=definition,
        version_id=version_id_for(definition),
        tasks=tasks,
        # Execution starts at the first `do` entry — every observed run's step
        # ledger starts there. A first task literally named "end" would still
        # execute (the sentinel governs TRANSITIONS, not the start) — H §14.5.
        first_task=next(iter(tasks)),
        warnings=warnings,
    )


def _compile_task(name: str, body: dict, mode: str, style_violation, warnings: list[str]) -> Task:
    type_keys = [k for k in body if k in TASK_TYPES]
    if len(type_keys) != 1:
        # Zero type keys is Base44's UNSUPPORTED_TASK_TYPE for try/for/fork/
        # set/raise/emit/listen/run/nested-do — the whole rejected CNCF
        # surface (H §3.1). More than one is unmeasured; ambiguity is fatal.
        raise WorkflowValidationError(
            "UNSUPPORTED_TASK_TYPE",
            f"Task '{name}' has no supported type key. Supported: {sorted(TASK_TYPES)}",
        )
    task_type = type_keys[0]

    x = body.get("x-base44")
    if x is not None:
        # Strict model: {title, description} only; an extra key inside is
        # INVALID_X_BASE44, while unknown x-* SIBLINGS are ignored (H §3.7).
        if not isinstance(x, dict) or not set(x) <= {"title", "description"}:
            raise WorkflowValidationError(
                "INVALID_X_BASE44", f"Task '{name}' x-base44 allows only title and description"
            )

    task = Task(name=name, type=task_type, x_base44=x or {})

    if task_type == "switch":
        # A switch must NOT carry its own `then` (H §3.5).
        if "then" in body:
            raise WorkflowValidationError(
                "SWITCH_TASK_THEN", f"Task '{name}' is a switch and cannot have its own 'then'"
            )
        cases = body["switch"]
        if not isinstance(cases, list) or len(cases) == 0:
            raise WorkflowValidationError(
                "MISSING_FIELD", f"Task '{name}' switch needs at least one case"
            )
        for case in cases:
            # Flat {when, then} objects only — the CNCF named-case form is
            # rejected (H §3.5).
            if not isinstance(case, dict) or "when" not in case:
                raise WorkflowValidationError(
                    "INVALID_SWITCH_CASE",
                    f"Task '{name}' switch cases must be flat objects with 'when' and 'then'",
                )
            if "then" not in case:
                raise WorkflowValidationError(
                    "MISSING_THEN", f"Task '{name}' switch case is missing 'then'"
                )
            when = case["when"]
            if not is_expression(when):
                raise WorkflowValidationError(
                    "INVALID_WHEN_CONDITION",
                    f"Task '{name}' switch 'when' must be a ${{ }} jq expression",
                )
            when_body = expression_body(when)
            if when_body.strip() == "":
                raise WorkflowValidationError(
                    "INVALID_WHEN_CONDITION",
                    f"Task '{name}': empty ${{ }} always matches — put a jq boolean expression inside",
                )
            # `when` syntax IS checked at Base44's validation layer, with jq's
            # own compiler output propagated (H §4.1) — fatal in both modes.
            jq_error = check_jq(when_body)
            if jq_error is not None:
                raise WorkflowValidationError(
                    "INVALID_WHEN_CONDITION",
                    f"Switch case 'when' is not valid jq: jq compilation failed: {jq_error}",
                )
            task.cases.append(SwitchCase(when=when_body, then=case["then"]))
        # Exhaustiveness rules (H §3.5) are STYLE: Base44 enforced them at
        # authoring time, so at import they can only over-block.
        if not _is_catch_all(task.cases[-1].when):
            style_violation(
                "SWITCH_NOT_EXHAUSTIVE",
                f"Task '{name}' switch must end in a ${{ true }} catch-all case",
            )
        if len(task.cases) == 1 and _is_catch_all(task.cases[0].when):
            style_violation(
                "SWITCH_SINGLE_CATCH_ALL",
                f"Task '{name}' switch always takes the same path. Remove the switch",
            )
        return task

    # call / wait both require `then` (H §3.4).
    then = body.get("then")
    if not isinstance(then, str) or not then:
        raise WorkflowValidationError("MISSING_THEN", f"Task '{name}' is missing 'then'")
    task.then = then

    if task_type == "call":
        activity = body["call"]
        if activity in BLOCKED_ACTIVITIES:
            # Known to Base44's global registry but not runnable here (gated /
            # unreleased on Base44 itself, zero occurrences in the wild —
            # H §3.2). Fatal in BOTH modes: precision-blocking beats a silent
            # no-op (AGENTS §21.6 of the round-1 report).
            raise WorkflowValidationError(
                "BLOCKED_ACTIVITY", f"Task '{name}' activity '{activity}' is not supported"
            )
        if activity not in ACTIVITIES:
            raise WorkflowValidationError(
                "UNKNOWN_ACTIVITY",
                f"Activity '{activity}' not found. Available: {sorted(ACTIVITIES)}",
            )
        task.activity = activity
        with_args = body.get("with")
        if with_args is not None and not isinstance(with_args, dict):
            raise WorkflowValidationError(
                "MISSING_REQUIRED_ARG", f"Task '{name}' 'with' must be an object"
            )
        task.with_args = with_args or {}
        for required in ACTIVITIES[activity]["required_args"]:
            if required not in task.with_args:
                raise WorkflowValidationError(
                    "MISSING_REQUIRED_ARG",
                    f"Task '{name}' activity '{activity}' requires '{required}'",
                )
        # Arg-expression SYNTAX at validation is unmeasured (runtime errors
        # fail the run either way — H §4.5), so bad syntax is style-only: at
        # import it must not block, because Base44 demonstrably stored it.
        for expr_body in _walk_expressions(task.with_args):
            jq_error = check_jq(expr_body)
            if jq_error is not None:
                style_violation(
                    "INVALID_ARG_EXPRESSION",
                    f"Task '{name}' arg expression is not valid jq: {jq_error}",
                )
        return task

    # wait — validation accepts nearly anything; the four runtime dialects are
    # the ENGINE's job (H §3.6, §14.3). The one shape validation refuses is
    # null (H §14.3).
    wait_value = body["wait"]
    if wait_value is None:
        raise WorkflowValidationError("INVALID_WAIT", f"Task '{name}' wait cannot be null")
    if is_expression(wait_value):
        jq_error = check_jq(expression_body(wait_value))
        if jq_error is not None:
            style_violation(
                "INVALID_WAIT_EXPRESSION",
                f"Task '{name}' wait expression is not valid jq: {jq_error}",
            )
    task.wait = wait_value
    return task


def _is_catch_all(when_body: str) -> bool:
    # Base44's observed catch-all is `${ true }` (H §3.5). Literal-true
    # detection matches the measurement; anything cleverer is unmeasured.
    return when_body.strip() == "true"


def _walk_expressions(value):
    if is_expression(value):
        yield expression_body(value)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_expressions(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_expressions(v)


def _check_cycles(tasks: dict[str, Task]) -> None:
    """Reject cycles that cannot terminate.

    Measured: a self-transition and an unconditional 2-cycle are rejected at
    validation with UNBOUNDED_CYCLE ("Ensure the workflow has a termination
    condition"), and the interpreter carries a 10,000-step runtime cap
    (H §3.4, §14.5). A cycle with a conditional exit is unmeasured — but the
    runtime cap existing at all implies reachable loops are constructible.

    OUR-RULE: a cycle is unbounded iff no task on it can reach `end` at all.
    That rejects both measured shapes, cannot over-block a record-backed
    definition, and leaves conditional loops to the runtime step cap — the
    permissive side of an unmeasured margin, chosen deliberately.
    """
    edges: dict[str, list[str]] = {
        name: ([t.then] if t.then is not None else [c.then for c in t.cases])
        for name, t in tasks.items()
    }

    # Tasks that can reach the END sentinel, computed backwards.
    can_end: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, targets in edges.items():
            if name in can_end:
                continue
            if any(t == END or t in can_end for t in targets):
                can_end.add(name)
                changed = True

    # A task on a cycle: reachable from itself.
    for start in edges:
        if start in can_end:
            continue
        seen: set[str] = set()
        stack = [t for t in edges[start] if t != END]
        while stack:
            node = stack.pop()
            if node == start:
                raise WorkflowValidationError(
                    "UNBOUNDED_CYCLE",
                    f"Cycle detected: task '{start}' can transition back to itself with no "
                    f"termination condition",
                )
            if node in seen or node == END or node not in edges:
                continue
            seen.add(node)
            stack.extend(t for t in edges[node] if t != END)
