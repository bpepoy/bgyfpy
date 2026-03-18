"""
Auth Router
===========
Magic link authentication endpoints.

Flow:
  1. POST /auth/login        — user submits email, receives magic link
  2. GET  /auth/verify       — user clicks link, receives JWT
  3. GET  /auth/me           — frontend checks who's logged in
  4. GET  /auth/users        — app_owner only, list all users

Protected endpoint usage:
  from routes.auth import require_permission

  @router.post("/fantasy/data/refresh")
  def refresh_data(user = Depends(require_permission("refresh_data"))):
      ...
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from services.auth_service import (
    create_magic_token,
    verify_magic_token,
    create_jwt,
    decode_jwt,
    send_magic_link_email,
)
from users import is_known_user, has_permission, get_all_users, get_user

router  = APIRouter(prefix="/auth", tags=["Auth"])
bearer  = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Shared auth dependency — use this to protect any endpoint
# ---------------------------------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    """
    FastAPI dependency. Validates the JWT from the Authorization header.
    Returns the decoded payload (email, role, display_name, manager_id).

    Usage:
        @router.get("/protected")
        def protected_endpoint(user = Depends(get_current_user)):
            return {"hello": user["display_name"]}
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_jwt(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload


def require_permission(permission: str):
    """
    FastAPI dependency factory. Checks the user has a specific permission.

    Usage:
        @router.post("/fantasy/data/refresh")
        def refresh(user = Depends(require_permission("refresh_data"))):
            ...
    """
    def _check(user: dict = Depends(get_current_user)):
        if not has_permission(user["sub"], permission):
            raise HTTPException(
                status_code=403,
                detail=f"Requires '{permission}' permission. Your role: {user['role']}"
            )
        return user
    return _check


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login")
def request_login(body: LoginRequest):
    """
    Step 1 — User submits their email.

    If the email is in the USERS config, sends a magic link.
    Always returns the same response whether the email is known or not
    (prevents email enumeration).

    Example:
        POST /auth/login
        { "email": "ncpepoyds@gmail.com" }
    """
    email = body.email.lower().strip()

    if is_known_user(email):
        token     = create_magic_token(email)
        email_sent = send_magic_link_email(email, token)

        # In development — also return the token directly so you can
        # test without clicking an email. Remove this before going public.
        import os
        if os.getenv("ENVIRONMENT", "development") == "development":
            return {
                "message":    "Magic link sent (dev mode: token included below)",
                "dev_token":  token,
                "dev_verify": f"/auth/verify?token={token}",
            }

    # Production response — same for known and unknown emails
    return {
        "message": "If that email is registered, you'll receive a login link shortly."
    }


@router.get("/verify")
def verify_login(token: str = Query(..., description="Magic link token from email")):
    """
    Step 2 — User clicks the magic link.

    Validates the one-time token, returns a JWT if valid.
    The frontend stores this JWT in localStorage and sends it
    with future requests as: Authorization: Bearer <jwt>

    Example:
        GET /auth/verify?token=abc123...
    """
    email = verify_magic_token(token)
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired magic link. Please request a new one."
        )

    user = get_user(email)
    if not user:
        raise HTTPException(status_code=403, detail="Account not found.")

    jwt_token = create_jwt(email)

    return {
        "token":        jwt_token,
        "display_name": user["display_name"],
        "manager_id":   user["manager_id"],
        "role":         user["role"],
        "message":      f"Welcome back, {user['display_name']}!",
    }


@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    """
    Returns the currently logged-in user's info.
    Frontend calls this on app load to check if the stored JWT is still valid.

    Example:
        GET /auth/me
        Authorization: Bearer <jwt>
    """
    return {
        "email":        user["sub"],
        "display_name": user["display_name"],
        "manager_id":   user["manager_id"],
        "role":         user["role"],
        "expires_at":   user.get("exp"),
    }


@router.get("/users")
def list_users(user: dict = Depends(require_permission("manage_roles"))):
    """
    Returns all registered users and their roles.
    App owner only.

    Example:
        GET /auth/users
        Authorization: Bearer <jwt>  (must be app_owner)
    """
    return {
        "users": get_all_users(),
        "total": len(get_all_users()),
    }


@router.get("/check")
def check_permission(
    permission: str = Query(..., description="Permission to check e.g. 'refresh_data'"),
    user: dict = Depends(get_current_user),
):
    """
    Check if the current user has a specific permission.
    Useful for the frontend to show/hide buttons.

    Example:
        GET /auth/check?permission=refresh_data
        Authorization: Bearer <jwt>
    """
    allowed = has_permission(user["sub"], permission)
    return {
        "permission": permission,
        "allowed":    allowed,
        "role":       user["role"],
    }