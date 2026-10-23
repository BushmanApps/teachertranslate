"""Base44's model names — ONE table (`llm_models.json`), derived from
Base44's own wire, read by everything here that knows a model by name:
InvokeLLM's accepted and reported names, the gateway's model list, the model
each name runs on (its OpenRouter slug) and the id the gateway echoes.

The table is never typed by hand. `src/lib/base44-llm-models.ts` derives it:
the reported list and its owners from the gateway's `GET /models`; which
names are accepted by asking each one a request that fails validation AFTER
the model is looked up (free); where a name routes from the `model` a real
completion echoes; the slug by finding that echo in OpenRouter's live
catalog. A daily job keeps the derived table in our database and every
migration ships the newest one in this file's place — the copy committed
here is the table as of `observed`, and what the gates run on.

A name Base44 has stopped accepting stays in the table marked `retired`,
with the route it last had: callers are refused on it as on any unknown
name, and the code here that runs a fixed model by its Base44 name
(ExtractDataFromUploadedFile) keeps resolving it.

Before this file (2026-09-29) the names lived in four hand-typed tables and
fell behind Base44 four times in four months.
"""

from __future__ import annotations

import json
from pathlib import Path

TABLE: dict = json.loads((Path(__file__).parent / "llm_models.json").read_text())

AUTOMATIC = "automatic"
# In Base44's order — its error text and its model list print them verbatim.
REPORTED: tuple[str, ...] = tuple(model["id"] for model in TABLE["reported"])
OWNED_BY: dict[str, str] = {model["id"]: model["owned_by"] for model in TABLE["reported"]}
LIST_CREATED: int = TABLE["created"]
ALIASES: dict[str, dict] = TABLE["aliases"]
# Every name a caller may pass: the reported ones, then the ones Base44
# still takes without listing them.
ACCEPTED: tuple[str, ...] = REPORTED + tuple(
    alias for alias, entry in ALIASES.items() if alias not in REPORTED and not entry.get("retired")
)


def route(alias: str) -> str:
    return ALIASES[alias]["route"]


def echo(alias: str) -> str:
    return AUTOMATIC if alias == AUTOMATIC else ALIASES[alias]["echo"]
