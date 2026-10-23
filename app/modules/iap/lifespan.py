from app.modules.iap.store import ensure_indexes


async def on_startup() -> None:
    await ensure_indexes()
