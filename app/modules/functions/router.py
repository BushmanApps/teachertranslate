"""
Functions module — runtime invocation routes.

Three route families, all proxying to externally deployed functions:

1. POST /api/apps/{app_id}/functions/{name:path}  — SDK invoke()
2. ALL  /api/functions/{name:path}                 — SDK fetch()
3. ALL  /functions/{name:path}                     — Non-SDK alias

All skip the app-level visibility gate.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from app.config import Settings
from app.deps import get_settings
from app.modules.functions.proxy import proxy_to_function

router = APIRouter(prefix="/api/apps/{app_id}/functions", tags=["functions"])
fetch_router = APIRouter(prefix="/api/functions", tags=["functions"])
alias_router = APIRouter(prefix="/functions", tags=["functions"])


# All three families accept the same method set. Prod treats the invoke
# route as a generic proxy: any method → lookup → 404 if missing, otherwise
# forward verbatim. POST-only here caused GET to fall through to the SPA
# HTML catch-all (returns 200 HTML — wrong contract) and PUT/PATCH/DELETE/
# OPTIONS/HEAD to return 405 instead of 404. See Owner C C-F2.
@router.api_route(
    "/{name:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def invoke_function(
    request: Request,
    app_id: str,
    name: str,
    settings: Settings = Depends(get_settings),
) -> Response:
    return await proxy_to_function(request, name, settings)


@fetch_router.api_route(
    "/{name:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def fetch_function(
    request: Request,
    name: str,
    settings: Settings = Depends(get_settings),
) -> Response:
    return await proxy_to_function(request, name, settings)


@alias_router.api_route(
    "/{name:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def alias_function(
    request: Request,
    name: str,
    settings: Settings = Depends(get_settings),
) -> Response:
    return await proxy_to_function(request, name, settings)
