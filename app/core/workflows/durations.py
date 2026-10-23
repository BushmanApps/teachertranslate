"""`wait` runtime dialect parsing — measured behaviour, quirks included.

Base44's runtime accepts FOUR wait dialects, with an asymmetry a sane person
would not design but which we replicate exactly because migrated definitions
were written against it (H §14.3, probes 17/17b/17c):

  1. jq expression `${ … }` — evaluated FIRST, result re-parsed by these rules
     (a real customer idiom: eNook builds "PT"+N+"S" at runtime — H §8.3).
  2. bare number — that many SECONDS; zero and negatives complete with ~0 wait.
  3. object — known components summed ({minutes: 1, seconds: 30} → 90s);
     unknown keys and {} are silently ZERO.
  4. string — STRICT ISO-8601 duration that must have a non-zero component:
     `PT0S`/`PT0M`/`P0D` FAIL ("ISO 8601 duration has no time components"),
     any unparseable string FAILS ("Invalid ISO 8601 duration: '…'") — and a
     numeric STRING like "9" is not a number, it fails.

So `0` completes while `"PT0S"` fails, and `{}` completes while `""` fails.
Do not normalise the asymmetry away.
"""

import re


class WaitError(Exception):
    """A wait value the runtime refuses. Fails the run with this message."""


# Component keys observed in the object dialect (H §14.3 measured minutes +
# seconds; hours/days follow the same pattern and cost nothing — an unknown
# key contributes zero either way, matching {fortnights: 1} → ~0 wait).
_OBJECT_COMPONENTS = {"seconds": 1.0, "minutes": 60.0, "hours": 3600.0, "days": 86400.0}

_ISO_DURATION = re.compile(
    r"^P"
    r"(?:(?P<weeks>\d+(?:\.\d+)?)W)?"
    r"(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    r")?$"
)

_ISO_MULTIPLIERS = {"weeks": 604800.0, "days": 86400.0, "hours": 3600.0, "minutes": 60.0, "seconds": 1.0}


def parse_wait(value) -> float:
    """Resolve a (post-jq-evaluation) wait value to seconds. Raises WaitError
    with Base44's measured message shapes on refusal."""
    if isinstance(value, bool):
        # Unmeasured margin; a boolean wait is nonsense — fail loudly rather
        # than let True count as 1 second.
        raise WaitError(f"Invalid ISO 8601 duration: '{value}'")
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    if isinstance(value, dict):
        return sum(
            float(v) * _OBJECT_COMPONENTS[k]
            for k, v in value.items()
            if k in _OBJECT_COMPONENTS and isinstance(v, (int, float)) and not isinstance(v, bool)
        )
    if isinstance(value, str):
        match = _ISO_DURATION.match(value)
        if not match or not any(match.groupdict().values()):
            raise WaitError(f"Invalid ISO 8601 duration: '{value}'")
        total = sum(
            float(raw) * _ISO_MULTIPLIERS[name]
            for name, raw in match.groupdict().items()
            if raw is not None
        )
        if total == 0:
            raise WaitError("ISO 8601 duration has no time components")
        return total
    raise WaitError(f"Invalid ISO 8601 duration: '{value}'")
