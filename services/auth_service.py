"""
Auth Service
============
Handles magic link generation, JWT creation/verification, and email sending.

Environment variables required:
  JWT_SECRET_KEY  — random hex string, generated during setup
  RESEND_API_KEY  — from resend.com dashboard (starts with re_)
  FRONTEND_URL    — your Vercel URL (e.g. https://bgyfpy.vercel.app)
                    Falls back to http://localhost:3000 in development
"""

import os
import secrets
import time
from jose import jwt, JWTError
from config.users import get_user, is_known_user

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JWT_SECRET      = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRE_HOURS= 24        # JWT valid for 24 hours
MAGIC_EXPIRE_MIN= 15        # Magic link token valid for 15 minutes
FROM_EMAIL      = "onboarding@resend.dev"   # Resend test address — works without a domain
FROM_NAME       = "BlackGold Fantasy"

# In-memory store for pending magic link tokens
# { token: { email, expires_at } }
# Fine for a small private app — resets on server restart (Render redeploys)
_pending_tokens: dict = {}


# ---------------------------------------------------------------------------
# Magic link token management
# ---------------------------------------------------------------------------

def create_magic_token(email: str) -> str:
    """
    Generate a one-time magic link token for the given email.
    Token expires in MAGIC_EXPIRE_MIN minutes.
    """
    token = secrets.token_urlsafe(32)
    _pending_tokens[token] = {
        "email":      email,
        "expires_at": time.time() + (MAGIC_EXPIRE_MIN * 60),
    }
    return token


def verify_magic_token(token: str) -> str | None:
    """
    Validate a magic link token. Returns the email if valid, None otherwise.
    Deletes the token after use (one-time only).
    """
    entry = _pending_tokens.get(token)
    if not entry:
        return None
    if time.time() > entry["expires_at"]:
        del _pending_tokens[token]
        return None
    del _pending_tokens[token]   # consume — single use
    return entry["email"]


# ---------------------------------------------------------------------------
# JWT management
# ---------------------------------------------------------------------------

def create_jwt(email: str) -> str:
    """
    Create a signed JWT for a verified user.
    Payload includes email, role, display_name, and expiry.
    """
    user = get_user(email)
    if not user:
        raise ValueError(f"Unknown user: {email}")

    payload = {
        "sub":          email,
        "display_name": user["display_name"],
        "manager_id":   user["manager_id"],
        "role":         user["role"],
        "iat":          int(time.time()),
        "exp":          int(time.time()) + (JWT_EXPIRE_HOURS * 3600),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    """
    Decode and verify a JWT. Returns the payload dict or None if invalid/expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Email sending via Resend
# ---------------------------------------------------------------------------

def send_magic_link_email(email: str, magic_token: str) -> bool:
    """
    Send a magic link email using Resend.
    Returns True on success, False on failure.
    """
    try:
        import resend

        resend.api_key = os.getenv("RESEND_API_KEY", "")
        if not resend.api_key:
            print("⚠️  RESEND_API_KEY not set — magic link email not sent")
            return False

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        magic_url    = f"{frontend_url}/auth/verify?token={magic_token}"

        user         = get_user(email)
        display_name = user["display_name"] if user else "there"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
            <h2 style="color: #1a1a1a; margin-bottom: 8px;">BlackGold Fantasy</h2>
            <p style="color: #444; font-size: 16px;">Hey {display_name},</p>
            <p style="color: #444; font-size: 16px;">Click the button below to log in. This link expires in {MAGIC_EXPIRE_MIN} minutes.</p>
            <a href="{magic_url}"
               style="display: inline-block; margin: 24px 0; padding: 14px 28px;
                      background: #1a1a1a; color: #ffffff; text-decoration: none;
                      border-radius: 8px; font-size: 16px; font-weight: 500;">
                Log in to BlackGold
            </a>
            <p style="color: #888; font-size: 13px;">
                If you didn't request this, you can safely ignore this email.
            </p>
            <p style="color: #bbb; font-size: 12px;">
                Link expires in {MAGIC_EXPIRE_MIN} minutes.
            </p>
        </div>
        """

        resend.Emails.send({
            "from":    f"{FROM_NAME} <{FROM_EMAIL}>",
            "to":      [email],
            "subject": f"Your BlackGold login link",
            "html":    html_body,
        })

        print(f"✅ Magic link sent to {email}")
        return True

    except Exception as e:
        print(f"❌ Failed to send magic link to {email}: {str(e)}")
        return False