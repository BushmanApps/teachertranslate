"""Credit packs — which products add credits, to which field, how many.

Declared where every non-secret fact of a migrated app lives, the repo's
`.escapebase44/config.json`, as one env value the deploy hands the backend:

    "IAP_CREDIT_PACKS": "credits_100=credits+100, credits_500=credits+500"

A product named here is a credit pack on both stores: buying it adds the
number to that field of the buyer's own User record (a number field the app
already reads — Base44's own credits template keeps credits on the user), once
per purchase. A product not named here is never a credit pack, whatever the
app's code calls it — so a pack cannot be bought for more credits than the
owner priced it at.

An entry that does not parse is left out and logged, never fatal: the app
keeps serving, and a purchase of the left-out pack is refused at verify (and
stays pending in the store until the declaration is fixed — nothing is lost).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache

from app.modules.entities.helpers import _USER_ANCHORED_FIELDS, _USER_VALUE_IMMUTABLE_FIELDS

logger = logging.getLogger("escapebase44.iap")

_ENTRY = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*=\s*([A-Za-z][A-Za-z0-9_]*)\s*\+\s*(\d+)\s*$")
_PROTECTED = _USER_ANCHORED_FIELDS | _USER_VALUE_IMMUTABLE_FIELDS


@dataclass(frozen=True)
class Pack:
    product_id: str
    field: str
    amount: int


def parse(value: str | None) -> dict[str, Pack]:
    return dict(_parse(value or ""))


# Parsed once per value (the deploy fixes it for the process's life), so a
# left-out entry is logged once, not on every purchase.
@lru_cache(maxsize=8)
def _parse(value: str) -> tuple[tuple[str, Pack], ...]:
    packs: dict[str, Pack] = {}
    for raw in value.split(","):
        if not raw.strip():
            continue
        m = _ENTRY.match(raw)
        if not m:
            logger.warning("IAP_CREDIT_PACKS: %r is not product=field+amount — left out", raw.strip())
            continue
        product_id, field, amount = m.group(1), m.group(2), int(m.group(3))
        if field in _PROTECTED or amount <= 0:
            logger.warning("IAP_CREDIT_PACKS: %r names a field a purchase may not change — left out", raw.strip())
            continue
        packs[product_id] = Pack(product_id, field, amount)
    return tuple(packs.items())
