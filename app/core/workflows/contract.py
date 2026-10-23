"""Loader for the measured Base44 Workflows subset (contract.json).

The JSON file — not this module — is the source of truth, because three
consumers read it: this compiler, the migrator's TypeScript analysis gate
(which imports the JSON directly), and the contract-drift probe that diffs it
against Base44's live `validate-definition` response. Keep additions measured;
the file's `_readme` says where the evidence lives.
"""

import json
from pathlib import Path

_CONTRACT_PATH = Path(__file__).parent / "contract.json"

with _CONTRACT_PATH.open(encoding="utf-8") as f:
    CONTRACT: dict = json.load(f)

TASK_TYPES: frozenset[str] = frozenset(CONTRACT["task_types"])
ACTIVITIES: dict = CONTRACT["activities"]
BLOCKED_ACTIVITIES: frozenset[str] = frozenset(CONTRACT["blocked_activities"])
JQ_DENYLIST: tuple[str, ...] = tuple(CONTRACT["jq_denylist"])
RUNTIME_STEP_LIMIT: int = CONTRACT["runtime_step_limit"]
CASCADE_DEPTH_LIMIT: int = CONTRACT["cascade_depth_limit"]
DSL_MAJOR: str = CONTRACT["dsl_major"]
NAMESPACE: str = CONTRACT["namespace"]
