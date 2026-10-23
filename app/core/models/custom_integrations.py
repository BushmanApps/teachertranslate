"""Custom-integrations runtime request model.

`POST /api/apps/:appId/integrations/custom/:slug/:operationId` validates
its body against `RuntimeIntegrationBody`. Validation failures emit a
**400 status** envelope variant (NOT the integrations-Core #3 envelope at
422 — Base44 quirk specifically for custom-integration validation):

```
status: 400
{
  "error_type": "HTTPException",
  "message": "Invalid request payload: [{<errors list>}]",
  "detail": "Invalid request payload: [{<errors list>}]",
  ...
}
```

### Same-decisions on the field declarations

Each field's type is the bare `dict[...]` (NOT `Optional[dict[...]]`)
with a `None` default. Pydantic 2.12 with a non-Optional type and `None`
default accepts a missing field (the default fires) but **rejects an
explicit `null`** with the standard `dict_type` error — including the
`url: "https://errors.pydantic.dev/2.12/v/dict_type"` field — which is
exactly the wire shape Base44 emits. This is the natural Pydantic way to
say "this field is optional but if you provide it, it must be a dict."

Probed against Base44 prod (see
`research/testing-server/custom_integrations/findings/2026-05-21-wave-1-base44-contract.md`,
section "B05-B08"). Both code paths (this model and Base44's) emit byte-
identical error JSON in the `dict_type` case.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class RuntimeIntegrationBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path_params: dict[str, str] = None  # type: ignore[assignment]
    query_params: dict[str, Any] = None  # type: ignore[assignment]
    payload: dict = None  # type: ignore[assignment]
    headers: dict[str, str] = None  # type: ignore[assignment]
