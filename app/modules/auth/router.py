"""Auth module — three routers for three URL prefixes.

- router:        /api/apps/{app_id}/auth/...  (register, login, OTP, password)
- oauth_router:  /api/apps/auth/...           (Google, Microsoft OAuth, no app_id)
- users_router:  /api/apps/{app_id}/users/... (invite-user)
"""

from fastapi import APIRouter

from app.modules.auth.apple_signin import apple_native_login, apple_nonce
from app.modules.auth.change_password import change_password
from app.modules.auth.google_oauth import auth_error, google_callback, google_login, logout
from app.modules.auth.invite_user import invite_user
from app.modules.auth.login import login
from app.modules.auth.microsoft_oauth import microsoft_callback, microsoft_login
from app.modules.auth.register import register
from app.modules.auth.resend_otp import resend_otp
from app.modules.auth.reset_password import reset_password
from app.modules.auth.reset_password_request import reset_password_request
from app.modules.auth.sso import get_access_token
from app.modules.auth.verify_otp import verify_otp

router = APIRouter(prefix="/api/apps/{app_id}/auth", tags=["auth"])

router.add_api_route("/register", register, methods=["POST"])
router.add_api_route("/login", login, methods=["POST"])
router.add_api_route("/verify-otp", verify_otp, methods=["POST"])
router.add_api_route("/resend-otp", resend_otp, methods=["POST"])
router.add_api_route("/reset-password-request", reset_password_request, methods=["POST"])
router.add_api_route("/reset-password", reset_password, methods=["POST"])
router.add_api_route("/change-password", change_password, methods=["POST"])
router.add_api_route("/sso/accesstoken/{user_id}", get_access_token, methods=["GET"])
router.add_api_route("/apple/nonce", apple_nonce, methods=["GET"])
router.add_api_route("/apple/native", apple_native_login, methods=["POST"])

oauth_router = APIRouter(prefix="/api/apps/auth", tags=["auth-oauth"])

oauth_router.add_api_route("/login", google_login, methods=["GET"])
oauth_router.add_api_route("/callback", google_callback, methods=["GET"])
oauth_router.add_api_route("/microsoft/login", microsoft_login, methods=["GET"])
oauth_router.add_api_route("/microsoft/callback", microsoft_callback, methods=["GET"])
oauth_router.add_api_route("/auth-error", auth_error, methods=["GET"])
oauth_router.add_api_route("/logout", logout, methods=["GET"])

users_router = APIRouter(prefix="/api/apps/{app_id}/users", tags=["auth-users"])

users_router.add_api_route("/invite-user", invite_user, methods=["POST"])
