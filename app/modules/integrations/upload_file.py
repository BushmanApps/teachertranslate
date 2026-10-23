"""POST /api/apps/:appId/integration-endpoints/Core/UploadFile"""

from __future__ import annotations

import uuid

from fastapi import Depends, UploadFile

from app.core.errors import AppHTTPException
from app.core.security.pipeline import AuthedContext, get_authed_context
from app.deps import get_storage_provider


async def upload_file(
    app_id: str,
    file: UploadFile,
    ctx: AuthedContext = Depends(get_authed_context),
    storage=Depends(get_storage_provider),
):
    if storage is None:
        raise AppHTTPException(500, "Storage provider not configured")

    data = await file.read()
    # 9-char prefix matches Base44's wire format (own-probes 2026-05-20:
    # every captured prefix is 9 lowercase-hex chars). 36 bits = ~64B
    # combinations — collision-safe at single-app scale.
    random_prefix = uuid.uuid4().hex[:9]
    filename = f"{random_prefix}_{file.filename or 'upload'}"
    content_type = file.content_type or "application/octet-stream"

    file_url = await storage.upload(
        data=data,
        filename=filename,
        content_type=content_type,
        private=False,
    )

    return {"file_url": file_url}
