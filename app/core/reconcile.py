"""The ONE internal reconcile door: `POST /api/internal/reconcile`.

The deploy runner calls it once after every deploy with everything the repo
carries that the backend keeps a registry of — the deployed functions and
their addresses, the canonical workflow files, the actors. The repo is the
source of truth; each registry converges onto it.

The runner never knows which modules a migrated backend ships (the migrator
prunes modules the app does not use — `backend-prune/manifest.ts`). So the
door lives here, in core, which ships with every app, and the modules
contribute: a module that owns a registry exposes `reconcile.py` with

    async def reconcile(payload: dict) -> dict | None

and is called with the whole payload; it reads its own key and answers with
what it registered. A pruned module contributes nothing — the same shape as
`_run_module_startup_hooks` in main.py for `lifespan.py`.

One registry is core's own: the app's email templates (`base44/emails/
**.html`, core/email_templates.py), read by Core SendEmail and by the
workflows engine alike. The runner sends them in the `workflows` file map,
next to the workflow files — the shape every runner since 2026-08-31 posts.

Before this door
(2026-09-19) each module mounted its own `/api/internal/<module>/reconcile`
and the runner decided by proxies (a manifest file, a folder) which ones to
call — a zero-function app whose builder had seeded an empty functions
manifest got a 405 from the pruned module's missing route, and its deploy
went red after the app was already live.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.exceptions import RequestValidationError
from pydantic import TypeAdapter, ValidationError

from app.core import email_templates

_FILES = TypeAdapter(dict[str, str])


async def converge(payload: dict) -> dict:
    modules_dir = Path(__file__).parent.parent / "modules"
    results: dict[str, object] = {}
    if "workflows" in payload:
        try:
            files = _FILES.validate_python(payload["workflows"])
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        results["email_templates"] = await email_templates.converge(files)
    for module_path in sorted(modules_dir.iterdir()):
        hook_file = module_path / "reconcile.py"
        if not (module_path.is_dir() and hook_file.exists()):
            continue
        mod = importlib.import_module(f"app.modules.{module_path.name}.reconcile")
        try:
            result = await mod.reconcile(payload)
        except ValidationError as exc:
            # A module validates its own slice of the payload; a bad slice is a
            # 422 like any body model's, not a 500.
            raise RequestValidationError(exc.errors()) from exc
        if result is not None:
            results[module_path.name] = result
    return results
