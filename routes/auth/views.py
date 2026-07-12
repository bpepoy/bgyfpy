"""
routes/auth/views_auth.py
==========================
Google OAuth verification endpoint for BlackGold PWA.

Flow (Option B — frontend-handled):
  1. React frontend uses @react-oauth/google to show Google login
  2. Google returns an id_token (JWT) to the frontend
  3. Frontend sends id_token to POST /auth/verify-google-token
  4. Backend verifies token with Google, looks up manager in Supabase
  5. Returns manager identity + role + a session token for subsequent requests

No redirects needed — pure API, works perfectly for PWA/mobile.
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from supabase import create_client

router = APIRouter(prefix="/auth", tags=["Auth"])

GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
JWT_SECRET            = os.environ.get("JWT_SECRET_KEY", "")
JWT_EXPIRE_DAYS       = 30


# ── helpers ───────────────────────────────────────────────────────────────────

def _sb():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=500,
            detail="Supabase not configured.")
    return create_client(url, key)


def _make_session_token(manager_id: str, role: str) -> str:
    """Create a simple JWT for subsequent authenticated requests."""
    import jose.jwt as jwt
    payload = {
        "manager_id": manager_id,
        "role":        role,
        "exp":         datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
        "iat":         datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _verify_session_token(token: str) -> dict:
    """Verify a session token and return the payload."""
    import jose.jwt as jwt
    from jose import JWTError
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


# ── models ────────────────────────────────────────────────────────────────────

class GoogleTokenRequest(BaseModel):
    id_token: str   # the token Google returns to the frontend


class MagicLinkRequest(BaseModel):
    email: str


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/verify-google-token")
async def verify_google_token(body: GoogleTokenRequest):
    """
    Verify a Google id_token from the frontend.

    1. Validates token with Google
    2. Extracts email from verified token
    3. Looks up email in Supabase users table
    4. Returns manager identity + session token

    Frontend usage (@react-oauth/google):
      const { credential } = useGoogleLogin(...)
      await fetch('/auth/verify-google-token', {
        method: 'POST',
        body: JSON.stringify({ id_token: credential })
      })
    """
    # Step 1: verify with Google
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GOOGLE_TOKEN_INFO_URL,
            params={"id_token": body.id_token}
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=401,
            detail="Invalid Google token. Please sign in again.")

    google_data = resp.json()

    # Verify the token was issued for our app
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    if client_id and google_data.get("aud") != client_id:
        raise HTTPException(status_code=401,
            detail="Token was not issued for this application.")

    email = google_data.get("email", "").lower().strip()
    if not email:
        raise HTTPException(status_code=401,
            detail="Could not extract email from Google token.")

    # Step 2: look up in Supabase
    sb   = _sb()
    resp = sb.table("users").select("*").eq("email", email).execute()

    if not resp.data:
        raise HTTPException(status_code=403,
            detail=f"Email '{email}' is not registered in BlackGold. "
                   "Contact Brian to be added.")

    user = resp.data[0]

    # Step 3: build session token
    session_token = _make_session_token(
        user["manager_id"], user["role"]
    )

    return {
        "status":        "authenticated",
        "session_token": session_token,
        "expires_in":    f"{JWT_EXPIRE_DAYS} days",
        "manager": {
            "manager_id":   user["manager_id"],
            "display_name": user["display_name"],
            "nickname":     user.get("nickname"),
            "photo_url":    user.get("photo_url"),
            "role":         user["role"],
            "email":        email,
        },
        "permissions": _role_permissions(user["role"]),
    }


@router.post("/magic-link")
async def send_magic_link(body: MagicLinkRequest):
    """
    Send a magic link login email via Supabase Auth.
    Backup for non-Gmail users or anyone who prefers email login.

    Supabase handles the email delivery and link generation.
    When the user clicks the link, they're redirected to the frontend
    with a Supabase session that the frontend exchanges for our session token.
    """
    email = body.email.lower().strip()

    # Check email is registered first
    sb   = _sb()
    resp = sb.table("users").select("manager_id, display_name").eq(
        "email", email).execute()

    if not resp.data:
        raise HTTPException(status_code=403,
            detail=f"Email '{email}' is not registered in BlackGold. "
                   "Contact Brian to be added.")

    # Send magic link via Supabase Auth
    try:
        sb.auth.sign_in_with_otp({"email": email})
    except Exception as e:
        raise HTTPException(status_code=500,
            detail=f"Failed to send magic link: {str(e)}")

    return {
        "status":  "sent",
        "message": f"Magic link sent to {email}. Check your inbox.",
        "manager": resp.data[0]["display_name"],
    }


@router.post("/verify-magic-link")
async def verify_magic_link(token: str, type: str = "magiclink"):
    """
    After user clicks magic link, frontend receives a Supabase token.
    Exchange it here for our session token.

    Frontend flow:
      1. User clicks magic link → redirected to frontend with #access_token=xxx
      2. Frontend sends access_token here
      3. Backend verifies with Supabase, returns our session token
    """
    sb = _sb()
    try:
        session = sb.auth.get_user(token)
        email   = session.user.email.lower().strip()
    except Exception:
        raise HTTPException(status_code=401,
            detail="Invalid or expired magic link token.")

    resp = sb.table("users").select("*").eq("email", email).execute()
    if not resp.data:
        raise HTTPException(status_code=403,
            detail=f"Email '{email}' is not registered.")

    user          = resp.data[0]
    session_token = _make_session_token(user["manager_id"], user["role"])

    return {
        "status":        "authenticated",
        "session_token": session_token,
        "expires_in":    f"{JWT_EXPIRE_DAYS} days",
        "manager": {
            "manager_id":   user["manager_id"],
            "display_name": user["display_name"],
            "nickname":     user.get("nickname"),
            "photo_url":    user.get("photo_url"),
            "role":         user["role"],
            "email":        email,
        },
        "permissions": _role_permissions(user["role"]),
    }


@router.get("/me")
async def get_me(authorization: Optional[str] = None):
    """
    Verify a session token and return the current user's identity.
    Frontend sends: Authorization: Bearer <session_token>

    Use this on app load to check if the user is still logged in.
    """
    from fastapi import Header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401,
            detail="No token provided. Please sign in.")

    token   = authorization.replace("Bearer ", "")
    payload = _verify_session_token(token)
    mid     = payload.get("manager_id")

    sb   = _sb()
    resp = sb.table("users").select(
        "manager_id, display_name, nickname, photo_url, role"
    ).eq("manager_id", mid).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Manager not found.")

    user = resp.data[0]
    return {
        "manager":     user,
        "permissions": _role_permissions(user["role"]),
    }


@router.post("/logout")
async def logout():
    """
    Logout endpoint — frontend should discard the session token.
    Stateless JWT so nothing to invalidate server-side.
    """
    return {
        "status":  "logged_out",
        "message": "Discard your session token on the frontend.",
    }


# ── role permissions map ──────────────────────────────────────────────────────

def _role_permissions(role: str) -> dict:
    """
    Returns a flat permissions map the frontend can use to
    show/hide UI elements without additional API calls.
    """
    base = {
        "can_view_fantasy":      True,
        "can_view_betting":      True,
        "can_view_settings":     True,
        "can_view_media":        True,
        "can_submit_water_bet":  True,
        "can_vote_proposals":    True,
        "can_submit_proposal":   True,
        "can_upload_media":      True,
        "can_enter_parlay":      False,
        "can_update_parlay_leg": False,
        "can_update_water_bet":  False,
        "can_send_notification": False,
        "can_update_punishment": False,
        "can_refresh_data":      False,
    }

    if role in ("betting_czar", "commissioner", "app_owner"):
        base["can_enter_parlay"]      = True
        base["can_update_parlay_leg"] = True
        base["can_update_water_bet"]  = True

    if role in ("commissioner", "app_owner"):
        base["can_send_notification"] = True
        base["can_update_punishment"] = True
        base["can_refresh_data"] = True

    return base