"""
routes/views.py
================
Top-level app views — sits above all sections (Fantasy, Basketball, Betting, Media).

No prefix — mounted directly in main.py so endpoints are at the root level.

Endpoints
---------
GET /home   — app landing page, all sections visible, fantasy snapshot
"""

from fastapi import APIRouter, HTTPException
import os
import json

router = APIRouter(tags=["App Views"])


# ── shared helpers ────────────────────────────────────────────────────────────

def _data_path(filename: str) -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "fantasy", filename,
    )


def _load(filename: str) -> dict:
    path = _data_path(filename)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _year_keyed(data: dict) -> dict:
    """Return only numeric-year top-level keys, sorted newest first."""
    return {
        k: v for k, v in sorted(
            ((k, v) for k, v in data.items() if str(k).isdigit()),
            key=lambda x: int(x[0]),
            reverse=True,
        )
    }


def _finished_seasons(results: dict) -> dict:
    """
    Seasons that are complete — have at least one manager with a final rank.
    Returns year-keyed dict, newest first.
    """
    finished = {}
    for yr, season in results.items():
        managers = season.get("managers", {})
        has_rank  = any(
            (m.get("playoff") or {}).get("rank") or
            (m.get("regular_season") or {}).get("rank")
            for m in managers.values()
        )
        if has_rank:
            finished[yr] = season
    return finished


# ===========================================================================
# GET /home
# ===========================================================================

@router.get("/home")
def app_home():
    """
    App landing page — the first screen every user sees.

    Sits above all sections (Fantasy, Betting, Basketball, Media).
    Returns everything the home screen needs in a single call.

    league_snapshot:  current season year, champion, last place + punishment
    stat_tiles:       total seasons, active members, unique champions, years active
    recent_champions: last 5 champions newest first
    era_pills:        era filter options with year ranges
    sections:         all app sections with label, icon, pills, available flag
                      available=false → render as coming-soon card in the UI
    """
    results    = _year_keyed(_load("results.json"))
    punishment = _load("punishment.json")
    matchups   = _load("matchups.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    finished       = _finished_seasons(results)
    finished_years = sorted(finished.keys(), reverse=True)
    latest_yr      = finished_years[0] if finished_years else None
    all_years      = sorted(results.keys())

    # ── latest season snapshot ────────────────────────────────────────────────
    champion     = None
    last_place   = None
    current_week = None
    num_teams    = 10

    if latest_yr:
        season    = finished[latest_yr]
        managers  = season.get("managers", {})
        num_teams = len(managers)

        for mid, m in managers.items():
            rs   = m.get("regular_season", {})
            po   = m.get("playoff", {})
            seed = rs.get("rank") or 99
            rank = po.get("rank") or seed

            if rank == 1:
                champion = {
                    "manager_id":   mid,
                    "display_name": m.get("display_name") or mid.title(),
                    "team_name":    m.get("team_name"),
                    "year":         int(latest_yr),
                    "wins":         rs.get("wins"),
                    "losses":       rs.get("losses"),
                    "points_for":   rs.get("points_for"),
                }

            if rank == num_teams:
                pun_entry = punishment.get(str(latest_yr), {})
                pun_text  = pun_entry.get("punishment") if isinstance(pun_entry, dict) else None
                last_place = {
                    "manager_id":   mid,
                    "display_name": m.get("display_name") or mid.title(),
                    "team_name":    m.get("team_name"),
                    "year":         int(latest_yr),
                    "wins":         rs.get("wins"),
                    "losses":       rs.get("losses"),
                    "punishment":   pun_text,
                }

        # Current week from matchups
        yr_mu = matchups.get(latest_yr, {})
        weeks = yr_mu.get("weeks", [])
        if weeks:
            current_week = max(w.get("week", 0) for w in weeks)

    # ── recent champions + unique count ──────────────────────────────────────
    champ_counts: dict   = {}
    recent_champions     = []
    active_mids: set     = set()

    for yr in finished_years:
        season    = finished[yr]
        managers  = season.get("managers", {})

        for mid, m in managers.items():
            rs   = m.get("regular_season", {})
            po   = m.get("playoff", {})
            seed = rs.get("rank") or 99
            rank = po.get("rank") or seed

            if rank == 1:
                champ_counts[mid] = champ_counts.get(mid, 0) + 1
                if len(recent_champions) < 5:
                    recent_champions.append({
                        "year":         int(yr),
                        "manager_id":   mid,
                        "display_name": m.get("display_name") or mid.title(),
                        "team_name":    m.get("team_name"),
                    })

    # Active managers — appeared in any of the last 3 seasons
    for yr in sorted(results.keys(), reverse=True)[:3]:
        active_mids.update(results[yr].get("managers", {}).keys())

    # ── era pills ─────────────────────────────────────────────────────────────
    era_pills = [
        {"key": "all_time",    "label": "All-Time",    "icon": "infinity",
         "years": f"{all_years[0]}–{all_years[-1]}"},
        {"key": "darkness",    "label": "Darkness",    "icon": "moon",
         "years": "2007–2009"},
        {"key": "sam_era",     "label": "Sam Era",     "icon": "user",
         "years": "2010–2013"},
        {"key": "frank_era",   "label": "Frank Era",   "icon": "user",
         "years": "2014–2017"},
        {"key": "jordan_era",  "label": "Jordan Era",  "icon": "user",
         "years": "2018–2022"},
        {"key": "auction_era", "label": "Auction",     "icon": "gavel",
         "years": "2023–present"},
    ]

    # ── app sections ──────────────────────────────────────────────────────────
    sections = [
        {
            "key":         "fantasy",
            "label":       "Fantasy",
            "description": f"{len(finished)} seasons of BlackGold NFL fantasy",
            "icon":        "shield",
            "color":       "gold",
            "pills": [
                {"key": "home",    "label": "Home",    "icon": "home"},
                {"key": "records", "label": "Records", "icon": "trophy"},
                {"key": "history", "label": "History", "icon": "clock-history"},
                {"key": "rules",   "label": "Rules",   "icon": "file-text"},
            ],
            "bottom_tabs": [
                {"key": "league", "label": "League", "icon": "layout-dashboard"},
                {"key": "season", "label": "Season", "icon": "calendar-stats"},
                {"key": "teams",  "label": "Teams",  "icon": "users"},
            ],
            "available":   True,
        },
        {
            "key":         "betting",
            "label":       "Betting",
            "description": "Weekly parlays — hits, misses, all-time records",
            "icon":        "currency-dollar",
            "color":       "green",
            "pills": [
                {"key": "parlays", "label": "Parlays", "icon": "ticket"},
                {"key": "season",  "label": "Season",  "icon": "calendar-stats"},
                {"key": "overall", "label": "Overall", "icon": "chart-bar"},
            ],
            "bottom_tabs": [
                {"key": "parlays", "label": "Parlays", "icon": "ticket"},
                {"key": "season",  "label": "Season",  "icon": "calendar-stats"},
                {"key": "overall", "label": "Overall", "icon": "chart-bar"},
            ],
            "available":   False,
            "coming_soon": True,
        },
        {
            "key":         "basketball",
            "label":       "Basketball",
            "description": "Real Bros NBA league",
            "icon":        "ball-basketball",
            "color":       "orange",
            "pills": [
                {"key": "league", "label": "League", "icon": "layout-dashboard"},
                {"key": "season", "label": "Season", "icon": "calendar-stats"},
                {"key": "teams",  "label": "Teams",  "icon": "users"},
            ],
            "bottom_tabs": [
                {"key": "league", "label": "League", "icon": "layout-dashboard"},
                {"key": "season", "label": "Season", "icon": "calendar-stats"},
                {"key": "teams",  "label": "Teams",  "icon": "users"},
            ],
            "available":   False,
            "coming_soon": True,
        },
        {
            "key":         "media",
            "label":       "Media",
            "description": "Punishments, ice videos, photos",
            "icon":        "device-tv",
            "color":       "blue",
            "pills": [
                {"key": "punishment", "label": "Punishment", "icon": "mood-sad"},
                {"key": "ice",        "label": "Ice Videos",  "icon": "player-play"},
                {"key": "photos",     "label": "Photos",      "icon": "photo"},
            ],
            "bottom_tabs": [
                {"key": "punishment", "label": "Punishment", "icon": "mood-sad"},
                {"key": "ice",        "label": "Ice Videos",  "icon": "player-play"},
                {"key": "photos",     "label": "Photos",      "icon": "photo"},
            ],
            "available":   False,
            "coming_soon": True,
        },
    ]

    return {
        "app_name":    "BlackGold",
        "tagline":     "19 seasons. One league.",
        "league_snapshot": {
            "year":         int(latest_yr) if latest_yr else None,
            "current_week": current_week,
            "champion":     champion,
            "last_place":   last_place,
        },
        "stat_tiles": {
            "total_seasons":    len(finished),
            "years_active":     f"{all_years[0]}–{all_years[-1]}",
            "active_members":   len(active_mids),
            "unique_champions": len(champ_counts),
            "num_teams":        num_teams,
        },
        "recent_champions": recent_champions,
        "era_pills":        era_pills,
        "sections":         sections,
    }


@router.get("/home/debug")
def home_debug():
    """Temporary debug — shows exact file paths being read."""
    import os
    path = _data_path("results.json")
    return {
        "file":              __file__,
        "resolved_root":     os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "results_json_path": path,
        "results_exists":    os.path.exists(path),
        "data_dir":          os.path.dirname(path),
        "data_dir_exists":   os.path.exists(os.path.dirname(path)),
        "data_dir_contents": os.listdir(os.path.dirname(path)) if os.path.exists(os.path.dirname(path)) else [],
    }