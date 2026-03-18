"""
User & Role Configuration
=========================
Add all league members here. Roles control what each user can do in the app.

Roles:
  app_owner    — Brian. Full access including managing user roles.
  commissioner — Zef. Can trigger data refreshes and edit league settings.
  member       — Everyone else. Read-only access.

To add a new user: add their entry to USERS below, matching their
display_name to the manager_id in MANAGER_IDENTITY_MAP in config.py.
"""

USERS = {
    "ncpepoyds@gmail.com": {
        "display_name": "Brian",
        "manager_id":   "brian",
        "role":         "app_owner",
    },
    "zdema6789@gmail.com": {
        "display_name": "Zef",
        "manager_id":   "zef",
        "role":         "commissioner",
    },
    # --- League members (add emails as they're confirmed) ---
    # "example@gmail.com": {
    #     "display_name": "Nick",
    #     "manager_id":   "nick",
    #     "role":         "member",
    # },
}

ROLE_PERMISSIONS = {
    "app_owner":    ["read", "refresh_data", "edit_settings", "manage_roles"],
    "commissioner": ["read", "refresh_data", "edit_settings"],
    "member":       ["read"],
}


def get_user(email: str) -> dict | None:
    """Look up a user by email. Returns None if not found."""
    return USERS.get(email.lower().strip())


def get_user_role(email: str) -> str | None:
    """Return the role string for an email, or None if not a known user."""
    user = get_user(email)
    return user["role"] if user else None


def has_permission(email: str, permission: str) -> bool:
    """Check if a user has a specific permission."""
    role = get_user_role(email)
    if not role:
        return False
    return permission in ROLE_PERMISSIONS.get(role, [])


def is_known_user(email: str) -> bool:
    """Return True if the email is in the USERS dict."""
    return email.lower().strip() in USERS


def get_all_users() -> list:
    """Return all users as a list (without exposing emails directly)."""
    return [
        {
            "display_name": data["display_name"],
            "manager_id":   data["manager_id"],
            "role":         data["role"],
        }
        for data in USERS.values()
    ]