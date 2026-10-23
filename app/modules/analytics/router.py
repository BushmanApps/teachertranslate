"""Analytics module — no-op stub.

The SDK's `analytics` module posts events to track user activity. We don't
collect any of this, so the endpoint accepts the request and returns an
empty object. The SDK ignores the response and swallows errors regardless.
"""

from fastapi import APIRouter

router = APIRouter(tags=["analytics"])


@router.post("/api/apps/{app_id}/analytics/track/batch")
async def track_batch(app_id: str) -> dict:
    return {}
