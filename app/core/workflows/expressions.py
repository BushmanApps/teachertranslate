"""jq expression evaluation for workflow runtime — sandbox included.

Semantics measured against Base44 production (H = research/divergence-chasing/
2026-08-19-workflows/HANDOFF.md):

- It IS jq — Base44 propagates jq's own compiler errors (H §4.1). We run real
  libjq via the `jq` package (the `workflows` optional extra; deploys on both
  Vercel's Python runtime and the VPS image — H §8b.1).
- THE DENYLIST (H §4.4, §13.4 — a security contract): `env`, `$ENV`, `input`,
  `inputs` are refused at RUNTIME (validation accepts them). Base44's measured
  rule is a word-boundary match that ignores occurrences immediately preceded
  by `.` — so field access (`.seed.env`) passes while the words are rejected
  anywhere else INCLUDING string literals (`has("env")`, "please input value"
  both refused). Replicated exactly: over-blocking is the safe direction, and
  no migrated workflow can contain an expression Base44 rejects — it would
  never have run there. The filter exists because libjq's `env` reads the real
  process environment; the boot-time scrub in the workflows module lifespan is
  the belt to this filter's braces.
- Runtime expression errors FAIL THE RUN with jq's message (H §4.5, §14.5) —
  they never evaluate to false/null and continue.
- Truthiness is jq's: null and false are falsy, everything else truthy —
  a non-boolean string like "yes" is truthy (H §14.5).
"""

import re


class ExpressionError(Exception):
    """A runtime expression failure. Fails the run with this message."""


# Word-boundary match on the denylisted names, ignoring occurrences
# immediately preceded by `.` (field access) or by a word character
# (`.seed.environment` never matches — `env` inside `environment` has no
# right boundary; `menv` has no left one). `$ENV` is matched as the literal
# variable. Measured classification table: H §13.4.
_DENYLIST = re.compile(r"(?<![.\w])(env|input|inputs)\b|\$ENV\b")

_DENYLIST_MESSAGE = (
    "jq expression uses a disallowed builtin (env / $ENV / input / inputs): "
    "'{expr}'. jq is scoped to the workflow data payload only."
)


def check_denylist(expr_body: str) -> None:
    """Raise ExpressionError iff Base44's runtime filter would refuse this."""
    if _DENYLIST.search(expr_body):
        raise ExpressionError(_DENYLIST_MESSAGE.format(expr=expr_body))


def evaluate(expr_body: str, context: dict):
    """Evaluate a jq expression body against the run context document.

    Returns the FIRST value the program emits (every measured Base44
    expression is single-valued; multi-output behaviour is unmeasured, so
    first-value is the smallest consistent choice). Raises ExpressionError on
    denylist hits, compile errors, runtime errors, and empty output.
    """
    import jq  # lazy — the `workflows` optional extra

    check_denylist(expr_body)
    try:
        program = jq.compile(expr_body)
    except ValueError as e:
        raise ExpressionError(f"jq compilation failed: {e}")
    try:
        results = program.input(context).all()
    except ValueError as e:
        # libjq runtime errors surface as ValueError with the jq message
        # (e.g. 'Cannot index string with string "foo"' — H §4.5 verbatim).
        raise ExpressionError(str(e))
    if not results:
        raise ExpressionError(f"jq expression produced no output: '{expr_body}'")
    return results[0]


def is_truthy(value) -> bool:
    """jq truthiness: null and false are falsy, everything else truthy
    (H §14.5 — "yes" truthy, null falsy)."""
    return value is not None and value is not False


def trigger_admits(condition, trigger_payload: dict) -> bool:
    """Whether an event is the workflow's at all: `trigger.condition` is a jq
    expression over the trigger payload, addressed as `.trigger.…` (Base44's
    own Slack example — H §14.11b), and no condition admits every event.

    Measured on an entity trigger (probe 37, round5-37-trigger-condition.log):
    a false result and a null result fire nothing, and a condition jq cannot
    evaluate fires nothing either — no run is created, failed or otherwise (an
    expression error INSIDE a run fails the run; a condition never gets that
    far). Every trigger family that fires on an event reads it: one Kordio
    "only when status is done" workflow ran on every change of every work
    order until this was read (Russell Rochambeau, 2026-10-19)."""
    if condition is None or condition == "":
        return True
    from .compiler import expression_body, is_expression

    body = expression_body(condition) if is_expression(condition) else str(condition)
    try:
        return is_truthy(evaluate(body, {"trigger": trigger_payload}))
    except ExpressionError:
        return False


# Mid-string interpolation (chase 2026-08-31-new-workflow-triggers, probes
# 16a/17/17b — Base44's own malformed programs leaked the transform): a string
# that CONTAINS `${ … }` without being one whole expression becomes a jq
# STRING-INTERPOLATION program — each `${` → `\(`, its LAZILY-matched next
# `}` → `)`, body trimmed, the rest of the string carried into a jq string
# literal RAW. Measured: "a ${ 1 + 1 } b" ran the program "a \(1 + 1) b" →
# "a 2 b". The rawness is deliberate parity, bugs included: a body containing
# `}` (jq object construction) or a suffix that breaks the string literal
# produces a jq compile error on Base44 (probe 17b's program was literally
# `"x \({"a": 1) } y"`) and must fail the same way here — never "fixed" into
# behaviour Base44 doesn't have. A whole-string `${ … }` stays the VALUE
# branch (greedy first-`${`-to-last-`}`, H §6.2) — `"${ 1 }+${ 2 }"` is
# whole-string by that detector and fails on its body, measured (probe 17).
_INTERPOLATION = re.compile(r"\$\{(.*?)\}")


def interpolation_program(value: str) -> str:
    return '"' + _INTERPOLATION.sub(lambda m: "\\(" + m.group(1).strip() + ")", value) + '"'


def evaluate_args(args: dict, context: dict) -> dict:
    """Evaluate `with.args` for a call step: a whole-`${ … }` string value is
    jq-evaluated to its VALUE (a reference to a not-yet-run step arrives
    null — jq on the context does that naturally); a string merely CONTAINING
    `${ … }` interpolates to a STRING (see interpolation_program above);
    everything else passes literally, nested containers walked (H §6.2)."""
    from .compiler import expression_body, is_expression

    def walk(value):
        if is_expression(value):
            return evaluate(expression_body(value), context)
        if isinstance(value, str) and _INTERPOLATION.search(value):
            return evaluate(interpolation_program(value), context)
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    return {k: walk(v) for k, v in args.items()}
