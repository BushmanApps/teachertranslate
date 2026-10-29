from app.core import db
from app.modules.auth.apple_signin import ensure_nonce_indexes


async def ensure_user_indexes() -> None:
    await db.coll("User").create_index(
        [("app_id", 1), ("email", 1)],
        unique=True,
        name="app_id_email_unique",
    )
    await db.coll("_private_users").create_index(
        [("app_id", 1), ("email", 1)],
        unique=True,
        name="app_id_email_unique",
    )


async def on_startup() -> None:
    await ensure_nonce_indexes()
    await ensure_user_indexes()
