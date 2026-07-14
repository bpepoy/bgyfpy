"""
routes/media/views.py
======================
Media read endpoints for BlackGold PWA.

All media records live in Supabase (media table).
Cloudinary stores the actual files — URLs returned from Supabase.

Filters available on all endpoints:
  - sort:       newest (default) | oldest
  - year:       filter by photo creation year (stored as media_year)
  - uploaded_by: filter by manager_id

Additional filters:
  - /content:      tag (all | meme | draft_weekend | faceswap)
  - /food-reviews: restaurant, min_rating, max_rating
"""

import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from supabase import create_client

router = APIRouter(prefix="/media", tags=["Media"])


# ── Supabase client ───────────────────────────────────────────────────────────

def _sb():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=500,
            detail="Supabase not configured.")
    return create_client(url, key)


def _sort_order(sort: str) -> bool:
    """Returns desc=True for newest, desc=False for oldest."""
    return sort.lower() != "oldest"


# ===========================================================================
# GET /media/content
# ===========================================================================

@router.get("/content")
def get_content(
    tag:         Optional[str] = Query(default=None,
                     description="all | meme | draft_weekend | faceswap"),
    sort:        str = Query(default="newest",
                     description="newest | oldest"),
    year:        Optional[int] = Query(default=None,
                     description="Filter by photo creation year"),
    uploaded_by: Optional[str] = Query(default=None,
                     description="Filter by manager_id"),
):
    """
    Photos and videos tagged as content.
    Default: all content newest to oldest.
    Toggle between: all, meme, draft_weekend, faceswap.
    """
    sb    = _sb()
    desc  = _sort_order(sort)
    query = sb.table("media").select("*").eq("category", "content")

    if tag and tag != "all":
        query = query.contains("tags", [tag])
    if year:
        query = query.eq("media_year", year)
    if uploaded_by:
        query = query.eq("uploaded_by", uploaded_by)

    resp = query.order("uploaded_at", desc=desc).execute()
    items = resp.data or []

    return {
        "total":       len(items),
        "category":    "content",
        "tag":         tag or "all",
        "sort":        sort,
        "filters": {
            "year":        year,
            "uploaded_by": uploaded_by,
        },
        "available_tags": ["meme", "draft_weekend", "faceswap"],
        "items":       items,
    }


# ===========================================================================
# GET /media/ice-videos
# ===========================================================================

@router.get("/ice-videos")
def get_ice_videos(
    sort:        str = Query(default="newest"),
    year:        Optional[int] = Query(default=None),
    uploaded_by: Optional[str] = Query(default=None),
):
    """
    Ice videos only. Newest to oldest by default.
    """
    sb    = _sb()
    desc  = _sort_order(sort)
    query = sb.table("media").select("*").eq("category", "ice_video")

    if year:
        query = query.eq("media_year", year)
    if uploaded_by:
        query = query.eq("uploaded_by", uploaded_by)

    resp  = query.order("uploaded_at", desc=desc).execute()
    items = resp.data or []

    return {
        "total":    len(items),
        "category": "ice_video",
        "sort":     sort,
        "filters": {
            "year":        year,
            "uploaded_by": uploaded_by,
        },
        "items": items,
    }


# ===========================================================================
# GET /media/punishment
# ===========================================================================

@router.get("/punishment")
def get_punishment(
    sort:        str = Query(default="newest"),
    year:        Optional[int] = Query(default=None),
    uploaded_by: Optional[str] = Query(default=None),
):
    """
    Punishment photos and videos. Newest to oldest by default.
    """
    sb    = _sb()
    desc  = _sort_order(sort)
    query = sb.table("media").select("*").eq("category", "punishment")

    if year:
        query = query.eq("media_year", year)
    if uploaded_by:
        query = query.eq("uploaded_by", uploaded_by)

    resp  = query.order("uploaded_at", desc=desc).execute()
    items = resp.data or []

    return {
        "total":    len(items),
        "category": "punishment",
        "sort":     sort,
        "filters": {
            "year":        year,
            "uploaded_by": uploaded_by,
        },
        "items": items,
    }


# ===========================================================================
# GET /media/food-reviews
# ===========================================================================

@router.get("/food-reviews")
def get_food_reviews(
    sort:        str = Query(default="newest"),
    year:        Optional[int] = Query(default=None),
    uploaded_by: Optional[str] = Query(default=None),
    restaurant:  Optional[str] = Query(default=None),
    min_rating:  Optional[float] = Query(default=None,
                     description="Only show reviews with rating >= this value"),
    max_rating:  Optional[float] = Query(default=None,
                     description="Only show reviews with rating <= this value"),
):
    """
    Food review videos. Newest to oldest by default.
    Filter by restaurant, rating range, year, or uploader.
    """
    sb    = _sb()
    desc  = _sort_order(sort)
    query = sb.table("media").select("*").eq("category", "food_review")

    if year:
        query = query.eq("media_year", year)
    if uploaded_by:
        query = query.eq("uploaded_by", uploaded_by)
    if restaurant:
        query = query.ilike("restaurant", f"%{restaurant}%")
    if min_rating is not None:
        query = query.gte("rating", min_rating)
    if max_rating is not None:
        query = query.lte("rating", max_rating)

    resp  = query.order("uploaded_at", desc=desc).execute()
    items = resp.data or []

    # Available restaurants for filter dropdown
    rest_resp  = sb.table("media").select("restaurant").eq(
        "category", "food_review").not_.is_("restaurant", "null").execute()
    restaurants = sorted(set(
        r["restaurant"] for r in (rest_resp.data or []) if r.get("restaurant")
    ))

    return {
        "total":    len(items),
        "category": "food_review",
        "sort":     sort,
        "filters": {
            "year":        year,
            "uploaded_by": uploaded_by,
            "restaurant":  restaurant,
            "min_rating":  min_rating,
            "max_rating":  max_rating,
        },
        "available_restaurants": restaurants,
        "items": items,
    }


# ===========================================================================
# GET /media/all
# ===========================================================================

@router.get("/all")
def get_all_media(
    category:    Optional[str] = Query(default=None,
                     description="content | ice_video | punishment | food_review"),
    sort:        str = Query(default="newest"),
    year:        Optional[int] = Query(default=None),
    uploaded_by: Optional[str] = Query(default=None),
):
    """
    All media across all categories. Filterable by category.
    """
    sb    = _sb()
    desc  = _sort_order(sort)
    query = sb.table("media").select("*")

    if category:
        query = query.eq("category", category)
    if year:
        query = query.eq("media_year", year)
    if uploaded_by:
        query = query.eq("uploaded_by", uploaded_by)

    resp  = query.order("uploaded_at", desc=desc).execute()
    items = resp.data or []

    # Summary counts by category
    counts = {}
    for item in items:
        cat = item.get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1

    return {
        "total":           len(items),
        "category_counts": counts,
        "sort":            sort,
        "filters": {
            "category":    category,
            "year":        year,
            "uploaded_by": uploaded_by,
        },
        "items": items,
    }


# ===========================================================================
# GET /media/restaurants
# ===========================================================================

@router.get("/restaurants")
def get_restaurants():
    """
    Returns list of all restaurants from restaurants.json.
    Used to populate the dropdown in the upload form.
    """
    import json
    _here  = os.path.dirname(os.path.abspath(__file__))
    _root  = os.path.abspath(os.path.join(_here, "..", ".."))
    path   = os.path.join(_root, "data", "media", "restaurants.json")

    try:
        with open(path) as f:
            raw = json.load(f)
        restaurants = raw.get("data", {}).get("restaurants", [])
    except FileNotFoundError:
        restaurants = []

    return {
        "restaurants": restaurants,
        "total":       len(restaurants),
    }


# ===========================================================================
# POST /media/restaurants/add
# ===========================================================================

@router.post("/restaurants/add")
def add_restaurant(name: str):
    """
    Add a new restaurant to restaurants.json.
    Called when user selects "New Restaurant" in the upload form.
    """
    import json
    _here  = os.path.dirname(os.path.abspath(__file__))
    _root  = os.path.abspath(os.path.join(_here, "..", ".."))
    path   = os.path.join(_root, "data", "media", "restaurants.json")

    try:
        with open(path) as f:
            raw = json.load(f)
    except FileNotFoundError:
        raw = {"data": {"restaurants": []}}

    restaurants = raw.get("data", {}).get("restaurants", [])

    # Check if already exists (case-insensitive)
    existing = [r for r in restaurants
                if r["name"].lower() == name.lower().strip()]
    if existing:
        return {
            "status":     "exists",
            "restaurant": existing[0],
        }

    # Add new
    new_id = max((r["id"] for r in restaurants), default=0) + 1
    new_restaurant = {"id": new_id, "name": name.strip()}
    restaurants.append(new_restaurant)
    raw["data"]["restaurants"] = restaurants

    with open(path, "w") as f:
        json.dump(raw, f, indent=2)

    return {
        "status":     "added",
        "restaurant": new_restaurant,
    }