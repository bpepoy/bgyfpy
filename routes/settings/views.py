"""
routes/settings/views_settings.py
===================================
Settings endpoints for BlackGold PWA.

Uses Supabase for all live data (profiles, proposals, votes,
media records, notifications). Cloudinary URLs stored in Supabase.

Auth: manager_id passed in request body (honor system for now).
      Replace body.manager_id with token identity once OAuth wired.
"""

import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from supabase import create_client, Client

router = APIRouter(prefix="/settings", tags=["Settings"])

ACTIVE_MEMBERS = [
    "blake","brian","frank","jake","joey",
    "jordan","kyle","nick","rob","zef"
]
COMMISSIONER_ROLES = {"app_owner", "commissioner", "betting_czar"}
ADMIN_ROLES        = {"app_owner", "commissioner"}
VOTE_THRESHOLD     = 6   # majority of 10

# ── Supabase client ───────────────────────────────────────────────────────────

def _sb() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=500,
            detail="Supabase not configured. Check SUPABASE_URL and SUPABASE_SERVICE_KEY.")
    return create_client(url, key)


def _get_user(manager_id: str) -> dict:
    sb   = _sb()
    resp = sb.table("users").select("*").eq("manager_id", manager_id).single().execute()
    if not resp.data:
        raise HTTPException(status_code=404,
            detail=f"Manager '{manager_id}' not found.")
    return resp.data


def _require_role(manager_id: str, allowed_roles: set) -> dict:
    user = _get_user(manager_id)
    if user.get("role") not in allowed_roles:
        raise HTTPException(status_code=403,
            detail=f"'{manager_id}' does not have permission for this action.")
    return user


# ── Pydantic models ───────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    manager_id:  str
    nickname:    Optional[str] = None
    photo_url:   Optional[str] = None   # Cloudinary URL from frontend upload
    cloudinary_id: Optional[str] = None


class MediaUpload(BaseModel):
    manager_id:    str
    media_type:    str          # photo | video
    category:      str          # content | ice_video | punishment | food_review
    cloudinary_url:str
    cloudinary_id: str
    tags:          list[str] = []
    restaurant:    Optional[str] = None   # food_review only
    season:        Optional[int] = None
    caption:       Optional[str] = None


class PunishmentUpdate(BaseModel):
    manager_id:  str            # must be app_owner or commissioner
    year:        int
    punishment:  str


class ProposalSubmit(BaseModel):
    submitted_by:   str
    title:          str
    description:    str
    attachment_url: Optional[str] = None


class VoteSubmit(BaseModel):
    manager_id: str
    vote:       str   # approve | reject


class PushNotification(BaseModel):
    sent_by: str    # must be app_owner or commissioner
    message: str


# ===========================================================================
# PROFILE
# ===========================================================================

@router.get("/profile/{manager_id}")
def get_profile(manager_id: str):
    """Get a manager's profile."""
    return _get_user(manager_id)


@router.get("/profiles")
def get_all_profiles():
    """Get all manager profiles — used to populate manager cards."""
    sb   = _sb()
    resp = sb.table("users").select(
        "manager_id, display_name, nickname, photo_url, role"
    ).in_("manager_id", ACTIVE_MEMBERS).execute()
    return {"profiles": resp.data or []}


@router.post("/profile/update")
def update_profile(body: ProfileUpdate):
    """
    Update a manager's profile nickname and/or photo_url.
    Frontend uploads photo directly to Cloudinary, then sends
    the resulting URL here.
    """
    if body.manager_id not in ACTIVE_MEMBERS:
        raise HTTPException(status_code=400,
            detail=f"'{body.manager_id}' is not an active member.")

    updates: dict = {"updated_at": "now()"}
    if body.nickname   is not None: updates["nickname"]      = body.nickname
    if body.photo_url  is not None: updates["photo_url"]     = body.photo_url
    if body.cloudinary_id is not None: updates["cloudinary_id"] = body.cloudinary_id

    if len(updates) == 1:
        raise HTTPException(status_code=400,
            detail="No fields to update. Provide nickname and/or photo_url.")

    sb   = _sb()
    resp = sb.table("users").update(updates).eq(
        "manager_id", body.manager_id).execute()

    return {"status": "updated", "manager_id": body.manager_id}


# ===========================================================================
# UPLOAD (media)
# ===========================================================================

VALID_CATEGORIES = {"content", "ice_video", "punishment", "food_review"}
VALID_TYPES      = {"photo", "video"}

CATEGORY_TAGS = {
    "content":     ["meme", "trip", "faceswap"],
    "ice_video":   ["ice-video"],
    "punishment":  ["punishment"],
    "food_review": [],
}


@router.post("/upload")
def upload_media(body: MediaUpload):
    """
    Record a media upload after Cloudinary upload completes.
    Frontend uploads to Cloudinary first (using unsigned preset),
    then sends the resulting URL + public_id here.

    Categories:
      content     — photo or video: tags from [meme, trip, faceswap] + custom
      ice_video   — video only, tied to season
      punishment  — photo or video
      food_review — video only, requires restaurant name
    """
    if body.manager_id not in ACTIVE_MEMBERS:
        raise HTTPException(status_code=400, detail="Unknown manager.")
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400,
            detail=f"category must be one of {VALID_CATEGORIES}")
    if body.media_type not in VALID_TYPES:
        raise HTTPException(status_code=400,
            detail=f"media_type must be photo or video")
    if body.category == "food_review" and not body.restaurant:
        raise HTTPException(status_code=400,
            detail="food_review uploads require a restaurant name.")
    if body.category == "ice_video" and body.media_type != "video":
        raise HTTPException(status_code=400,
            detail="ice_video must be a video.")

    sb   = _sb()
    resp = sb.table("media").insert({
        "uploaded_by":    body.manager_id,
        "media_type":     body.media_type,
        "category":       body.category,
        "cloudinary_url": body.cloudinary_url,
        "cloudinary_id":  body.cloudinary_id,
        "tags":           body.tags,
        "restaurant":     body.restaurant,
        "season":         body.season,
        "caption":        body.caption,
    }).execute()

    return {
        "status": "uploaded",
        "id":     resp.data[0]["id"] if resp.data else None,
    }


@router.get("/upload/tags")
def get_available_tags():
    """Returns available tags per category for the upload UI."""
    return {"category_tags": CATEGORY_TAGS}


@router.get("/upload/restaurants")
def get_restaurants():
    """Returns distinct restaurant names from food_review uploads."""
    sb   = _sb()
    resp = sb.table("media").select("restaurant").eq(
        "category", "food_review").not_.is_("restaurant", "null").execute()
    restaurants = sorted(set(
        r["restaurant"] for r in (resp.data or []) if r.get("restaurant")
    ))
    return {"restaurants": restaurants}


# ===========================================================================
# PUNISHMENT (commissioner/app_owner only)
# ===========================================================================

@router.post("/punishment/update")
def update_punishment(body: PunishmentUpdate):
    """
    Update punishment.json for a specific year.
    Only app_owner and commissioner can do this.
    Defaults to the newest year not yet in punishment.json.
    """
    _require_role(body.manager_id, ADMIN_ROLES)

    import json
    data_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "fantasy", "punishment.json"
    )
    try:
        with open(data_path) as f:
            punishment = json.load(f)
    except FileNotFoundError:
        punishment = {}

    punishment[str(body.year)] = {
        "year":       body.year,
        "punishment": body.punishment,
    }

    with open(data_path, "w") as f:
        json.dump(punishment, f, indent=2)

    return {
        "status": "updated",
        "year":   body.year,
        "punishment": body.punishment,
    }


@router.get("/punishment/next-year")
def get_punishment_next_year():
    """
    Returns the next year needing a punishment entry.
    Auto-detects by finding highest year in punishment.json + 1.
    """
    import json
    data_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "fantasy", "punishment.json"
    )
    try:
        with open(data_path) as f:
            punishment = json.load(f)
        existing = [int(k) for k in punishment.keys() if k.isdigit()]
        next_yr  = max(existing) + 1 if existing else 2025
    except Exception:
        next_yr  = 2025

    return {"next_year": next_yr}


# ===========================================================================
# RULE PROPOSALS
# ===========================================================================

@router.get("/proposals")
def get_proposals(status: Optional[str] = Query(default=None)):
    """
    Get rule change proposals.
    status=open     → only open proposals
    status=passed   → only passed proposals
    status=rejected → only rejected proposals
    (none)          → all proposals, open first
    """
    sb    = _sb()
    query = sb.table("proposals").select(
        "*, votes(manager_id, vote, voted_at)"
    )
    if status:
        query = query.eq("status", status)

    resp = query.order("created_at", desc=True).execute()
    proposals = resp.data or []

    # Enrich each proposal with vote summary
    for p in proposals:
        votes = p.get("votes", [])
        p["vote_summary"] = {
            "approve": sum(1 for v in votes if v["vote"] == "approve"),
            "reject":  sum(1 for v in votes if v["vote"] == "reject"),
            "pending": len(ACTIVE_MEMBERS) - len(votes),
            "total_voted": len(votes),
            "threshold": VOTE_THRESHOLD,
        }

    open_first = sorted(proposals,
                        key=lambda x: (x["status"] != "open", x["created_at"]),
                        reverse=False)
    return {"proposals": open_first, "total": len(open_first)}


@router.post("/proposals/submit")
def submit_proposal(body: ProposalSubmit):
    """Submit a new rule change proposal. Any active member can submit."""
    if body.submitted_by not in ACTIVE_MEMBERS:
        raise HTTPException(status_code=400, detail="Unknown manager.")

    sb   = _sb()
    resp = sb.table("proposals").insert({
        "submitted_by":   body.submitted_by,
        "title":          body.title,
        "description":    body.description,
        "attachment_url": body.attachment_url,
        "status":         "open",
    }).execute()

    return {
        "status": "submitted",
        "id":     resp.data[0]["id"] if resp.data else None,
    }


@router.post("/proposals/{proposal_id}/vote")
def vote_on_proposal(proposal_id: str, body: VoteSubmit):
    """
    Cast or update a vote on a proposal.
    vote: approve | reject

    Auto-closes the proposal when all 10 members have voted,
    or when approve count reaches VOTE_THRESHOLD (6).
    """
    if body.manager_id not in ACTIVE_MEMBERS:
        raise HTTPException(status_code=400, detail="Unknown manager.")
    if body.vote not in ("approve", "reject"):
        raise HTTPException(status_code=400,
            detail="vote must be 'approve' or 'reject'.")

    sb = _sb()

    # Check proposal exists and is open
    p_resp = sb.table("proposals").select("*").eq(
        "id", proposal_id).single().execute()
    if not p_resp.data:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    if p_resp.data["status"] != "open":
        raise HTTPException(status_code=400,
            detail=f"Proposal is already {p_resp.data['status']}.")

    # Upsert vote (allows changing vote while proposal is open)
    sb.table("votes").upsert({
        "proposal_id": proposal_id,
        "manager_id":  body.manager_id,
        "vote":        body.vote,
    }, on_conflict="proposal_id,manager_id").execute()

    # Check if proposal should close
    votes_resp = sb.table("votes").select("vote").eq(
        "proposal_id", proposal_id).execute()
    all_votes = votes_resp.data or []
    approve_count = sum(1 for v in all_votes if v["vote"] == "approve")
    total_voted   = len(all_votes)

    new_status = None
    if approve_count >= VOTE_THRESHOLD:
        new_status = "passed"
    elif (total_voted - approve_count) > (len(ACTIVE_MEMBERS) - VOTE_THRESHOLD):
        # Mathematically impossible to reach threshold
        new_status = "rejected"
    elif total_voted == len(ACTIVE_MEMBERS):
        new_status = "passed" if approve_count >= VOTE_THRESHOLD else "rejected"

    if new_status:
        from datetime import datetime, timezone
        sb.table("proposals").update({
            "status":    new_status,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", proposal_id).execute()

    return {
        "status":        "voted",
        "vote":          body.vote,
        "approve_count": approve_count,
        "total_voted":   total_voted,
        "proposal_status": new_status or "open",
        "threshold":     VOTE_THRESHOLD,
    }


# ===========================================================================
# PUSH NOTIFICATIONS (app_owner + commissioner only)
# ===========================================================================

@router.post("/notifications/send")
def send_notification(body: PushNotification):
    """
    Send a push notification to all members.
    Only app_owner (Brian) and commissioner (Zef) can send.

    Currently logs to Supabase notifications table.
    Wire to Firebase Cloud Messaging or Web Push in Phase 2.
    """
    _require_role(body.sent_by, ADMIN_ROLES)

    sb   = _sb()
    resp = sb.table("notifications").insert({
        "sent_by": body.sent_by,
        "message": body.message,
    }).execute()

    # TODO Phase 2: send actual push via FCM or Web Push API
    return {
        "status":  "sent",
        "message": body.message,
        "sent_by": body.sent_by,
        "note":    "Logged to DB. Wire FCM/Web Push for actual device delivery.",
    }


@router.get("/notifications")
def get_notifications(limit: int = Query(default=20)):
    """Recent notification history."""
    sb   = _sb()
    resp = sb.table("notifications").select(
        "*, users(display_name)"
    ).order("sent_at", desc=True).limit(limit).execute()
    return {"notifications": resp.data or []}


# ===========================================================================
# REFRESH DATA (app_owner only)
# ===========================================================================

@router.post("/refresh-data")
def refresh_data(manager_id: str = Query(...)):
    """
    Trigger a data refresh. app_owner only.
    Currently returns instructions — wire to Yahoo API builders
    once automated refresh strategy is confirmed.
    """
    _require_role(manager_id, {"app_owner"})

    return {
        "status": "acknowledged",
        "message": "Manual refresh: run the build-all endpoints in order.",
        "endpoints": [
            "GET /league/data/managers/build-all",
            "GET /league/data/results/build-all",
            "GET /league/data/matchups/build-all",
            "GET /league/data/rosters/build-all",
            "GET /league/data/player-stats/build-all",
            "GET /league/data/payouts/build-all",
            "GET /league/data/ices/build-all",
            "GET /league/data/analytics/build-all?force_clean=true",
        ],
        "note": "Automated refresh via cron will be added in Phase 2.",
    }