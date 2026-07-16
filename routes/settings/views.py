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
# github_sync imported at runtime via _commit() helper

router = APIRouter(prefix="/settings", tags=["Settings"])

ACTIVE_MEMBERS = [
    "blake","brian","frank","jake","joey",
    "jordan","kyle","nick","rob","zef"
]
COMMISSIONER_ROLES = {"app_owner", "commissioner", "betting_czar"}
ADMIN_ROLES        = {"app_owner", "commissioner"}
VOTE_THRESHOLD     = 6   # majority of 10


def _commit(path, message):
    """Commit a file to GitHub — fully inlined."""
    import base64
    import httpx as _httpx

    token  = os.environ.get("GITHUB_TOKEN", "")
    repo   = os.environ.get("GITHUB_REPO", "bpepoy/bgyfpy")
    branch = os.environ.get("GITHUB_BRANCH", "main")
    api    = "https://api.github.com"

    if not token:
        return {"status": "error", "detail": "GITHUB_TOKEN not set"}

    _here    = os.path.dirname(os.path.abspath(__file__))
    _root    = os.path.abspath(os.path.join(_here, "..", ".."))
    abs_path = os.path.join(_root, path.lstrip("/"))

    print("[_commit] abs_path=" + abs_path)
    print("[_commit] exists=" + str(os.path.exists(abs_path)))

    if not os.path.exists(abs_path):
        return {"status": "error", "detail": "File not found: " + abs_path}

    with open(abs_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url  = api + "/repos/" + repo + "/contents/" + path.lstrip("/")
    resp = _httpx.get(url, headers=headers, params={"ref": branch})
    sha  = resp.json().get("sha") if resp.status_code == 200 else None

    print("[_commit] sha=" + str(sha))

    payload = {"message": message, "content": content_b64, "branch": branch}
    if sha:
        payload["sha"] = sha

    resp = _httpx.put(url, headers=headers, json=payload)
    print("[_commit] status=" + str(resp.status_code))

    if resp.status_code in (200, 201):
        return {
            "status": "committed",
            "path":   path,
            "url":    "https://github.com/" + repo + "/blob/" + branch + "/" + path,
        }
    return {
        "status": "error",
        "detail": resp.json().get("message", "GitHub API error"),
        "code":   resp.status_code,
    }


def _commit_tree(files, message):
    """Commit multiple files atomically — fully inlined."""
    import base64
    import httpx as _httpx

    token  = os.environ.get("GITHUB_TOKEN", "")
    repo   = os.environ.get("GITHUB_REPO", "bpepoy/bgyfpy")
    branch = os.environ.get("GITHUB_BRANCH", "main")
    api    = "https://api.github.com"

    if not token:
        return {"status": "error", "detail": "GITHUB_TOKEN not set"}

    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.abspath(os.path.join(_here, "..", ".."))

    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = api + "/repos/" + repo

    ref_resp = _httpx.get(base + "/git/ref/heads/" + branch, headers=headers)
    if ref_resp.status_code != 200:
        return {"status": "error", "detail": "Could not get branch ref"}
    base_sha = ref_resp.json()["object"]["sha"]

    commit_resp   = _httpx.get(base + "/git/commits/" + base_sha, headers=headers)
    base_tree_sha = commit_resp.json()["tree"]["sha"]

    tree_items = []
    for path in files:
        abs_path = os.path.join(_root, path.lstrip("/"))
        if not os.path.exists(abs_path):
            continue
        with open(abs_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode()
        blob_resp = _httpx.post(base + "/git/blobs", headers=headers,
                                json={"content": content_b64, "encoding": "base64"})
        blob_sha = blob_resp.json().get("sha")
        if blob_sha:
            tree_items.append({
                "path": path.lstrip("/"),
                "mode": "100644",
                "type": "blob",
                "sha":  blob_sha,
            })

    if not tree_items:
        return {"status": "error", "detail": "No files found to commit"}

    tree_resp      = _httpx.post(base + "/git/trees", headers=headers,
                                  json={"base_tree": base_tree_sha, "tree": tree_items})
    new_tree_sha   = tree_resp.json().get("sha")
    new_commit     = _httpx.post(base + "/git/commits", headers=headers,
                                  json={"message": message, "tree": new_tree_sha,
                                        "parents": [base_sha]})
    new_commit_sha = new_commit.json().get("sha")
    _httpx.patch(base + "/git/refs/heads/" + branch, headers=headers,
                 json={"sha": new_commit_sha})

    return {
        "status": "committed",
        "files":  len(tree_items),
        "commit": new_commit_sha,
        "url":    "https://github.com/" + repo + "/commit/" + new_commit_sha,
    }

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
    menu_item:     Optional[str] = None   # food_review only
    rating:        Optional[float] = None # food_review only, 0-10
    review_text:   Optional[str] = None  # food_review only
    media_year:    Optional[int] = None   # year from photo/video metadata
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
    if body.rating is not None and not (0 <= body.rating <= 10):
        raise HTTPException(status_code=400,
            detail="rating must be between 0 and 10.")
    if body.category == "ice_video" and body.media_type != "video":
        raise HTTPException(status_code=400,
            detail="ice_video must be a video.")
    # food_review allows both photo and video — no restriction needed

    # Auto-add restaurant to restaurants.json if it's a new food_review
    if body.category == "food_review" and body.restaurant:
        import json
        _here  = os.path.dirname(os.path.abspath(__file__))
        _root  = os.path.abspath(os.path.join(_here, "..", ".."))
        r_path = os.path.join(_root, "data", "media", "restaurants.json")
        try:
            with open(r_path) as f:
                raw = json.load(f)
        except FileNotFoundError:
            raw = {"data": {"restaurants": []}}
        restaurants = raw.get("data", {}).get("restaurants", [])
        exists = any(r["name"].lower() == body.restaurant.lower().strip()
                     for r in restaurants)
        if not exists:
            new_id = max((r["id"] for r in restaurants), default=0) + 1
            restaurants.append({"id": new_id, "name": body.restaurant.strip()})
            raw["data"]["restaurants"] = restaurants
            with open(r_path, "w") as f:
                json.dump(raw, f, indent=2)
            _commit("data/media/restaurants.json",
                        f"New restaurant added: {body.restaurant}")

    sb   = _sb()
    resp = sb.table("media").insert({
        "uploaded_by":    body.manager_id,
        "media_type":     body.media_type,
        "category":       body.category,
        "cloudinary_url": body.cloudinary_url,
        "cloudinary_id":  body.cloudinary_id,
        "tags":           body.tags,
        "restaurant":     body.restaurant,
        "menu_item":      body.menu_item,
        "rating":         body.rating,
        "review_text":    body.review_text,
        "media_year":     body.media_year,
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
    _here      = os.path.dirname(os.path.abspath(__file__))
    _root      = os.path.abspath(os.path.join(_here, "..", ".."))
    data_path  = os.path.join(_root, "data", "fantasy", "punishment.json")
    try:
        with open(data_path) as f:
            raw = json.load(f)
        punishment = raw.get("data", raw) if isinstance(raw, dict) and "data" in raw else raw
    except FileNotFoundError:
        punishment = {}

    punishment[str(body.year)] = {
        "year":       body.year,
        "punishment": body.punishment,
    }

    with open(data_path, "w") as f:
        json.dump(punishment, f, indent=2)
    _commit("data/fantasy/punishment.json",
                f"Punishment updated: {body.year} by {body.manager_id}")

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
    _here      = os.path.dirname(os.path.abspath(__file__))
    _root      = os.path.abspath(os.path.join(_here, "..", ".."))
    data_path  = os.path.join(_root, "data", "fantasy", "punishment.json")
    try:
        with open(data_path) as f:
            raw = json.load(f)
        # unwrap {"data": {...}} wrapper if present
        punishment = raw.get("data", raw) if isinstance(raw, dict) and "data" in raw else raw
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
    Trigger a full data refresh from Yahoo API. app_owner only.
    Runs all builders in sequence then commits all JSON to GitHub.
    """
    _require_role(manager_id, {"app_owner"})

    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.abspath(os.path.join(_here, "..", ".."))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    results = []

    # Import and run each builder
    try:
        from routes.fantasy.league import (
            build_managers, build_results, build_matchups,
            build_rosters, build_player_stats, build_player_info,
            build_drafts, build_transactions, build_payouts, build_ices,
        )
        from routes.fantasy.analytics_builder import build_analytics_endpoint
        from routes.fantasy.league import _load_json, _get_data_path, _write_json

        builders = [
            ("managers",      lambda: build_managers()),
            ("results",       lambda: build_results()),
            ("matchups",      lambda: build_matchups()),
            ("rosters",       lambda: build_rosters()),
            ("player_info",   lambda: build_player_info()),
            ("player_stats",  lambda: build_player_stats()),
            ("drafts",        lambda: build_drafts()),
            ("transactions",  lambda: build_transactions()),
            ("payouts",       lambda: build_payouts()),
            ("ices",          lambda: build_ices()),
            ("analytics",     lambda: build_analytics_endpoint(
                                  _load_json, _get_data_path, _write_json, True)),
        ]

        for name, fn in builders:
            try:
                fn()
                results.append({"file": name, "status": "ok"})
            except Exception as e:
                results.append({"file": name, "status": "error", "detail": str(e)[:200]})

    except ImportError as e:
        return {"status": "error", "detail": f"Import error: {str(e)}"}

    # Commit all updated files to GitHub in one atomic commit
    files_to_commit = [
        "data/fantasy/managers.json",
        "data/fantasy/results.json",
        "data/fantasy/matchups.json",
        "data/fantasy/rosters.json",
        "data/fantasy/player_info.json",
        "data/fantasy/player_stats.json",
        "data/fantasy/drafts.json",
        "data/fantasy/transactions.json",
        "data/fantasy/payouts.json",
        "data/fantasy/ices.json",
        "data/fantasy/analytics.json",
    ]

    # Only commit files that built successfully
    successful = [r["file"] for r in results if r["status"] == "ok"]
    commit_files = [f for f in files_to_commit
                    if any(s in f for s in successful)]

    github_result = {"status": "skipped", "detail": "No files to commit"}
    if commit_files:
        github_result = _commit_tree(
            commit_files,
            f"Auto-refresh: {len(commit_files)} files updated"
        )

    return {
        "status":        "complete",
        "builders":      results,
        "github_commit": github_result,
        "triggered_by":  manager_id,
    }