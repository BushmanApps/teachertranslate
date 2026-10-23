from app.modules.auth.apple_signin import ensure_nonce_indexes


async def on_startup() -> None:
    await ensure_nonce_indexes()
