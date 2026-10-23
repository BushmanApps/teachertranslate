"""The one gate on the fork's `/api/internal/*` routes.

Every internal route (the scheduled-automation trigger, the workflows tick,
the one reconcile door in main.py) is reached by
infrastructure that holds the app's `EB44_CRON_SECRET` — pg_cron or the
on-box crond, and the deploy runner. One constant-time comparison, one
refusal shape (403 "forbidden"), in one place.
"""

from __future__ import annotations

import hmac

from app.core.errors import AppHTTPException


def check_cron_secret(provided: str | None, expected: str | None) -> None:
    if not provided or not expected or not hmac.compare_digest(provided, expected):
        raise AppHTTPException(403, "forbidden")
