"""
App visibility gate — to be implemented by the security agent.

Reads the app's public_settings (one of: public_without_login, public_with_login,
private_with_login, workspace_with_login) and checks whether the current caller
is allowed through.

Token class behavior:
- public_without_login: everyone passes
- public_with_login: app_user and service_role pass; anonymous/preview/platform get 403
- private_with_login: same as above, different error message
- workspace_with_login: same as above, different error message

Platform tokens do not satisfy login gates (they are not runtime user credentials).

Exact error messages are pinned in security.md.

Raises errors.visibility_deny() on failure.
"""

from __future__ import annotations

from app.core.errors import visibility_deny


_VISIBILITY_MESSAGES = {
    "public_with_login": "You must be logged in to access this app",
    "private_with_login": "This app is private, You do not have access to this app",
    "workspace_with_login": "This app is restricted to workspace members, You do not have access to this app",
}


def assert_app_visible(
    token_class: str,
    app_settings: dict,
    app_id: str,
    user: dict | None = None,
) -> None:
    mode = app_settings.get("public_settings", "public_without_login")
    if mode == "public_without_login":
        return

    if token_class == "service_role":
        return

    if token_class == "app_user" and user is not None:
        return

    message = _VISIBILITY_MESSAGES.get(mode, _VISIBILITY_MESSAGES["private_with_login"])
    raise visibility_deny(message, app_id)
