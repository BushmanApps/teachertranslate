"""EscapeBase44 mobile — /api/apps/{app_id}/eb44/mobile/*.

What the mobile kit's build asks the app at build time (mobile/setup.mjs, on
the Mobile release workflow): the addresses the app answers on — its
permanent eb44 address and every custom domain attached since — so a build
with links turned on (mobile/native.json `links`) lets each of them open the
installed app. Asked of the live app because custom domains live in its
database (`_app_settings.custom_domains`), never in the repo: one added after
a build is in the next build, typed by nobody.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi.routing import APIRouter

from app.core import addresses, db

router = APIRouter(prefix="/api/apps/{app_id}/eb44/mobile", tags=["eb44-mobile"])


async def hosts(app_id: str):
    out: list[str] = []
    canonical = urlparse(await addresses.canonical_base_url()).hostname
    for host in [canonical, *((await db.app_settings()).get("custom_domains") or [])]:
        bare = str(host or "").strip().lower()
        if bare and bare not in out:
            out.append(bare)
    return {"hosts": out}


router.add_api_route("/hosts", hosts, methods=["GET"])
