"""
routes/betting/views_betting.py
================================
Frontend-facing betting endpoints for BlackGold.

Files used:
  data/betting/parlays.json
  data/betting/water_bets.json

parlays.json structure:
{
  "2026": {
    "season_bet": {
      "entered_by": null, "entered_at": null, "wager": null, "payout": null,
      "legs": [{ "manager_id": "blake", "bet_text": null, "result": null, ... }]
    },
    "week_1": {
      "entered_by": null, "entered_at": null, "wager": null, "payout": null,
      "legs": [{
        "manager_id": "blake", "player_name": null, "position": null,
        "stat_count": null, "stat_op": null, "stat_type": null,
        "bet_text": null, "result": null, "updated_by": null, "updated_at": null
      }, ...]
    }
  }
}
result values: null (not entered) | "waiting" | "hit" | "miss" | "no_leg"

water_bets.json structure:
{
  "2026": [
    {
      "id": "wb_2026_001",
      "season": 2026,
      "week": 3,
      "submitted_at": "2026-10-01T12:00:00",
      "submitted_by": "joey",
      "submitted_by_display": "Joey",
      "opposing_manager": "nick",
      "opposing_manager_display": "Nick",
      "bet_text": "My team scores more than 130 this week",
      "result": "waiting",          // waiting | submitter_wins | opponent_wins
      "result_updated_by": null,
      "result_updated_at": null
    }
  ]
}
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/betting", tags=["Betting"])

# ── config ────────────────────────────────────────────────────────────────────

ACTIVE_MEMBERS = [
    {"manager_id": "blake",  "display_name": "Blake"},
    {"manager_id": "brian",  "display_name": "Brian"},
    {"manager_id": "frank",  "display_name": "Frank"},
    {"manager_id": "jake",   "display_name": "Jake"},
    {"manager_id": "joey",   "display_name": "Joey"},
    {"manager_id": "jordan", "display_name": "Jordan"},
    {"manager_id": "kyle",   "display_name": "Kyle"},
    {"manager_id": "nick",   "display_name": "Nick"},
    {"manager_id": "rob",    "display_name": "Rob"},
    {"manager_id": "zef",    "display_name": "Zef"},
]
ACTIVE_IDS = {m["manager_id"] for m in ACTIVE_MEMBERS}


def _commit(path: str, message: str) -> None:
    """Commit a file to GitHub. Fails silently if github_sync unavailable."""
    try:
        import sys
        _here = os.path.dirname(os.path.abspath(__file__))
        _root = os.path.abspath(os.path.join(_here, "..", ".."))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from github_sync import commit_file
        _commit(path, message)
    except Exception as e:
        print(f"[github_sync] commit failed: {e}")

# Resolve data/betting relative to project root (works regardless of where
# this file lives within routes/)
_HERE        = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT= os.path.abspath(os.path.join(_HERE, "..", ".."))
BETTING_DIR  = os.path.join(_PROJECT_ROOT, "data", "betting")

VALID_LEG_RESULTS = {"waiting", "hit", "miss", "no_leg"}
VALID_BET_RESULTS = {"waiting", "submitter_wins", "opponent_wins"}


# ── file helpers ──────────────────────────────────────────────────────────────

def _path(filename: str) -> str:
    return os.path.join(BETTING_DIR, filename)


def _load(filename: str) -> dict:
    p = _path(filename)
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


def _save(filename: str, data: dict) -> None:
    os.makedirs(BETTING_DIR, exist_ok=True)
    with open(_path(filename), "w") as f:
        json.dump(data, f, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_season_week(matchups_path: str = "") -> tuple:
    """
    Find the current season and week from parlays.json.
    Returns the first week (excluding season_bet) where any leg result is null.
    Falls back to current year week 1 if nothing found.
    """
    try:
        parlays = _load("parlays.json")
        current_year = datetime.now().year

        # Only look at seasons up to current year
        valid_seasons = sorted(
            [int(k) for k in parlays if k.isdigit() and int(k) <= current_year],
            reverse=False
        )

        for yr in valid_seasons:
            yr_data = parlays.get(str(yr), {})
            # Check weekly keys only, sorted ascending
            week_keys = sorted(
                [k for k in yr_data if k.startswith("week_")],
                key=lambda x: int(x.replace("week_", ""))
            )
            for wk_key in week_keys:
                wk_data = yr_data[wk_key]
                legs = wk_data.get("legs", [])
                # If any leg has null result, this is the current week
                if any(l.get("result") is None for l in legs):
                    return (yr, int(wk_key.replace("week_", "")))

        # All weeks complete — return current year week 1
        return (current_year, 1)
    except Exception:
        return (datetime.now().year, 1)


def _week_result(legs: list) -> dict:
    """Compute aggregate result from a list of legs. null result = not yet entered."""
    counts = {"hit": 0, "miss": 0, "waiting": 0, "no_leg": 0, "null": 0}
    for leg in legs:
        r = leg.get("result")
        if r is None:
            counts["null"] += 1
        else:
            counts[r] = counts.get(r, 0) + 1
    active = [l for l in legs if l.get("result") not in (None, "no_leg")]
    return {
        "total_hit":     counts["hit"],
        "total_miss":    counts["miss"],
        "total_waiting": counts["waiting"],
        "total_no_leg":  counts["no_leg"],
        "total_null":    counts["null"],
        "is_complete":   counts["waiting"] == 0 and counts["null"] == 0,
        "is_entered":    counts["null"] == 0,
        "hit_pct": round(counts["hit"] / len(active) * 100, 1) if active else None,
    }


# ── Pydantic models ───────────────────────────────────────────────────────────

class ParlayLeg(BaseModel):
    manager_id:  str
    player_name: Optional[str] = None
    player_pos:  Optional[str] = None
    stat_count:  Optional[float] = None
    stat_op:     Optional[str] = None    # over | under | equal
    stat_type:   Optional[str] = None
    bet_text:    Optional[str] = None    # optional free-text override


class ParlaySubmit(BaseModel):
    season:           int
    week:             int                # use 0 for season_bet
    entered_by:       str
    wager:            Optional[float] = None
    payout:           Optional[float] = None
    no_leg_managers:  list[str] = []     # immediately set to no_leg
    legs:             list[ParlayLeg]    # one per participating manager
    is_season_bet:    bool = False


class LegUpdate(BaseModel):
    updated_by:  str
    result:      str              # hit | miss | no_leg | waiting
    # Optional fields to update the leg detail after entry
    player_name: Optional[str] = None
    player_pos:  Optional[str] = None
    stat_count:  Optional[float] = None
    stat_op:     Optional[str] = None
    stat_type:   Optional[str] = None


class WaterBetSubmit(BaseModel):
    season:                  int
    ending_week:             int    # week by which the bet resolves (or 17 for full season)
    submitted_by:            str
    submitted_by_display:    str
    opposing_manager:        str
    opposing_manager_display:str
    bet_text:                str


class WaterBetResult(BaseModel):
    updated_by:  str
    winner_id:   str   # manager_id of the winner — either submitted_by or opposing_manager


# ===========================================================================
# GET /betting/parlay-options
# ===========================================================================

PLAYER_POSITIONS = [
    "QB", "RB", "WR", "TE", "K", "DEF",
    "DB", "LB", "DL", "OL", "LS",
]

STAT_OPERATIONS = [
    {"value": "over",  "label": "Over"},
    {"value": "under", "label": "Under"},
    {"value": "equal", "label": "Equal to"},
]

STAT_TYPES = [
    # Passing
    {"value": "passing_yards",       "label": "Passing Yards",       "group": "Passing"},
    {"value": "passing_tds",         "label": "Passing TDs",         "group": "Passing"},
    {"value": "completions",         "label": "Completions",         "group": "Passing"},
    {"value": "attempts",            "label": "Attempts",            "group": "Passing"},
    {"value": "interceptions_thrown","label": "Interceptions Thrown","group": "Passing"},
    # Rushing
    {"value": "rushing_yards",       "label": "Rushing Yards",       "group": "Rushing"},
    {"value": "rushing_tds",         "label": "Rushing TDs",         "group": "Rushing"},
    {"value": "carries",             "label": "Carries",             "group": "Rushing"},
    # Receiving
    {"value": "receiving_yards",     "label": "Receiving Yards",     "group": "Receiving"},
    {"value": "receiving_tds",       "label": "Receiving TDs",       "group": "Receiving"},
    {"value": "receptions",          "label": "Receptions",          "group": "Receiving"},
    {"value": "targets",             "label": "Targets",             "group": "Receiving"},
    # Combined
    {"value": "total_yards",         "label": "Total Yards",         "group": "Combined"},
    {"value": "total_tds",           "label": "Total TDs",           "group": "Combined"},
    {"value": "fantasy_points",      "label": "Fantasy Points",      "group": "Combined"},
    # Defense / Special
    {"value": "sacks",               "label": "Sacks",               "group": "Defense"},
    {"value": "interceptions",       "label": "Interceptions",       "group": "Defense"},
    {"value": "tackles",             "label": "Tackles",             "group": "Defense"},
    {"value": "forced_fumbles",      "label": "Forced Fumbles",      "group": "Defense"},
    {"value": "defensive_tds",       "label": "Defensive TDs",       "group": "Defense"},
    {"value": "field_goals_made",    "label": "Field Goals Made",    "group": "Kicking"},
    {"value": "field_goal_pct",      "label": "Field Goal %",        "group": "Kicking"},
    {"value": "longest_fg",          "label": "Longest FG",          "group": "Kicking"},
]


@router.get("/parlay-options")
def get_parlay_options():
    """
    Returns dropdown options for parlay entry form.
    Frontend uses these to populate player_pos and stat_type dropdowns.
    """
    return {
        "player_positions": PLAYER_POSITIONS,
        "stat_operations":  STAT_OPERATIONS,
        "stat_types":       STAT_TYPES,
        "active_members":   ACTIVE_MEMBERS,
    }


# ===========================================================================
# GET /betting/parlays
# ===========================================================================

@router.get("/parlays")
def get_parlays(
    season:        Optional[int]  = Query(default=None),
    week:          Optional[int]  = Query(default=None),
    is_season_bet: Optional[bool] = Query(default=False),
):
    import traceback
    try:
        return _get_parlays_inner(season, week, is_season_bet=is_season_bet or False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{str(e)}\n{traceback.format_exc()[:800]}")


def _get_parlays_inner(season, week, is_season_bet=False):
    """
    Returns parlay data.
    No params → auto-detect current season/week (first with null results).
    ?season=2026&week=3 → specific week.
    ?season=2026&week=0 → season_bet.
    """
    parlays = _load("parlays.json")

    if season is None or week is None:
        detected_season, detected_week = _current_season_week()
        season = season if season is not None else detected_season
        week   = week   if week   is not None else detected_week

    yr_key = str(season)

    # week=0 means season_bet
    if week == 0 or is_season_bet:
        wk_key = "season_bet"
    else:
        wk_key = f"week_{week}"

    yr_data = parlays.get(yr_key, {})
    wk_data = yr_data.get(wk_key)

    # Build available weeks — only seasons up to current year, skip all-future
    current_year = datetime.now().year
    available = []
    for yr, wks in sorted(parlays.items(), reverse=True):
        if not isinstance(wks, dict): continue
        if int(yr) > current_year: continue
        for wk_k in sorted(
            [k for k in wks if k.startswith("week_")],
            key=lambda x: int(x.replace("week_","")),
            reverse=True
        ):
            wk_n = int(wk_k.replace("week_", ""))
            wk_d = wks[wk_k]
            wr   = _week_result(wk_d.get("legs", []))
            available.append({
                "season":      int(yr),
                "week":        wk_n,
                "is_complete": wr.get("is_complete", False),
                "is_entered":  wr.get("is_entered",  False),
            })

    return {
        "season":         season,
        "week":           week,
        "active_members": ACTIVE_MEMBERS,
        "parlay":         {
            "entered_by":  wk_data.get("entered_by")  if wk_data else None,
            "entered_at":  wk_data.get("entered_at")  if wk_data else None,
            "wager":       wk_data.get("wager")        if wk_data else None,
            "payout":      wk_data.get("payout")       if wk_data else None,
            "legs":        wk_data.get("legs", [])     if wk_data else [],
            "week_result": _week_result(wk_data.get("legs", [])) if wk_data else None,
            "no_leg_managers": [
                l["manager_id"] for l in (wk_data.get("legs", []) if wk_data else [])
                if l.get("result") == "no_leg"
            ],
            "exists":      wk_data is not None,
            "is_season_bet": wk_key == "season_bet",
        },
        "available_weeks": available,
    }


# ===========================================================================
# POST /betting/parlays/submit
# ===========================================================================

@router.post("/parlays/submit")
def submit_parlay(body: ParlaySubmit):
    """
    Enter or update a parlay week. Weeks are pre-populated with null values
    in the JSON so this always updates existing entries rather than creating new ones.
    week=0 means season_bet.
    """
    parlays = _load("parlays.json")
    yr_key  = str(body.season)
    wk_key  = "season_bet" if (body.week == 0 or body.is_season_bet) else f"week_{body.week}"

    if yr_key not in parlays:
        parlays[yr_key] = {}

    now = _now()
    leg_map = {l.manager_id: l for l in body.legs if l.manager_id in ACTIVE_IDS}

    # Build legs — preserve existing data for fields not provided
    existing_legs = parlays[yr_key].get(wk_key, {}).get("legs", [])
    existing_map  = {l["manager_id"]: l for l in existing_legs}

    legs = []
    for m in ACTIVE_MEMBERS:
        mid      = m["manager_id"]
        existing = existing_map.get(mid, {})
        new_data = leg_map.get(mid)
        is_no_leg = mid in body.no_leg_managers

        if wk_key == "season_bet":
            # Season bet legs only have bet_text and result
            legs.append({
                "manager_id":   mid,
                "display_name": m["display_name"],
                "bet_text":     new_data.bet_text if new_data else existing.get("bet_text"),
                "result":       "no_leg" if is_no_leg else (existing.get("result") or "waiting"),
                "updated_by":   body.entered_by if is_no_leg else existing.get("updated_by"),
                "updated_at":   now if is_no_leg else existing.get("updated_at"),
            })
        else:
            legs.append({
                "manager_id":   mid,
                "display_name": m["display_name"],
                "player_name":  new_data.player_name if new_data else existing.get("player_name"),
                "position":     new_data.player_pos  if new_data else existing.get("position"),
                "stat_count":   new_data.stat_count  if new_data else existing.get("stat_count"),
                "stat_op":      new_data.stat_op     if new_data else existing.get("stat_op"),
                "stat_type":    new_data.stat_type   if new_data else existing.get("stat_type"),
                "bet_text":     new_data.bet_text    if new_data else existing.get("bet_text"),
                "result":       "no_leg" if is_no_leg else (existing.get("result") or "waiting"),
                "updated_by":   body.entered_by if is_no_leg else existing.get("updated_by"),
                "updated_at":   now if is_no_leg else existing.get("updated_at"),
            })

    parlays[yr_key][wk_key] = {
        "entered_by": body.entered_by,
        "entered_at": now,
        "wager":      body.wager,
        "payout":     body.payout,
        "legs":       legs,
    }

    _save("parlays.json", parlays)
    label = "season bet" if wk_key == "season_bet" else f"week {body.week}"
    _commit("data/betting/parlays.json",
            f"Parlay entered: {body.season} {label} by {body.entered_by}")
    return {
        "status":  "updated",
        "season":  body.season,
        "week":    body.week,
        "legs":    len(legs),
    }


# ===========================================================================
# POST /betting/parlays/{season}/{week}/update-leg
# ===========================================================================

@router.post("/parlays/{season}/{week}/update-leg/{manager_id}")
def update_parlay_leg(
    season:     int,
    week:       int,
    manager_id: str,
    body:       LegUpdate,
):
    """
    Update a single leg result.
    result: hit | miss | no_leg | waiting (reset)
    """
    import traceback
    try:
        return _update_parlay_leg_inner(season, week, manager_id, body)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500,
            detail=str(e) + " | " + traceback.format_exc()[:600])


def _update_parlay_leg_inner(season, week, manager_id, body):
    if body.result not in VALID_LEG_RESULTS:
        raise HTTPException(status_code=400,
            detail=f"Invalid result '{body.result}'. Must be: {VALID_LEG_RESULTS}")

    parlays = _load("parlays.json")
    yr_key  = str(season)
    wk_key  = f"week_{week}"

    wk_data = parlays.get(yr_key, {}).get(wk_key)
    if not wk_data:
        raise HTTPException(status_code=404,
            detail=f"No parlay found for {season} week {week}.")

    leg = next((l for l in wk_data["legs"] if l["manager_id"] == manager_id), None)
    if not leg:
        raise HTTPException(status_code=404,
            detail=f"No leg found for manager '{manager_id}'.")

    leg["result"]     = body.result
    leg["updated_by"] = body.updated_by
    leg["updated_at"] = _now()
    # Update leg detail fields if provided
    if body.player_name is not None: leg["player_name"] = body.player_name
    if body.player_pos  is not None: leg["player_pos"]  = body.player_pos
    if body.stat_count  is not None: leg["stat_count"]  = body.stat_count
    if body.stat_op     is not None: leg["stat_op"]     = body.stat_op
    if body.stat_type   is not None: leg["stat_type"]   = body.stat_type

    _save("parlays.json", parlays)
    _commit("data/betting/parlays.json",
                f"Parlay leg updated: {season} wk{week} {manager_id}={body.result}")
    return {
        "status":      "updated",
        "manager_id":  manager_id,
        "result":      body.result,
        "week_result": _week_result(wk_data["legs"]),
    }


# ===========================================================================
# GET /betting/water-bets
# ===========================================================================

@router.get("/water-bets")
def get_water_bets(
    season: Optional[int] = Query(default=None),
):
    """
    Returns water bets for a season (default: current season).
    Shows all bets with results. Sorted newest first.
    """
    water_bets = _load("water_bets.json")

    if season is None:
        season, _ = _current_season_week("")

    yr_key = str(season)
    bets   = water_bets.get(yr_key, [])

    # Sort newest first
    bets_sorted = sorted(bets, key=lambda x: x.get("submitted_at", ""), reverse=True)

    waiting  = [b for b in bets_sorted if b["result"] == "waiting"]
    resolved = [b for b in bets_sorted if b["result"] != "waiting"]

    available_seasons = sorted(
        [int(k) for k in water_bets.keys() if k.isdigit()],
        reverse=True
    )

    return {
        "season":             season,
        "active_members":     ACTIVE_MEMBERS,
        "total_bets":         len(bets),
        "waiting_count":      len(waiting),
        "resolved_count":     len(resolved),
        "waiting_bets":       waiting,
        "resolved_bets":      resolved,
        "available_seasons":  available_seasons,
    }


# ===========================================================================
# POST /betting/water-bets/submit
# ===========================================================================

@router.post("/water-bets/submit")
def submit_water_bet(body: WaterBetSubmit):
    """
    Submit a new water bet. Any member can submit.
    Honor system — submitted_by identifies who submitted.
    """
    if body.submitted_by not in ACTIVE_IDS:
        raise HTTPException(status_code=400,
            detail=f"Unknown manager '{body.submitted_by}'.")
    if body.opposing_manager not in ACTIVE_IDS:
        raise HTTPException(status_code=400,
            detail=f"Unknown opposing manager '{body.opposing_manager}'.")
    if body.submitted_by == body.opposing_manager:
        raise HTTPException(status_code=400,
            detail="submitted_by and opposing_manager cannot be the same.")

    water_bets = _load("water_bets.json")
    yr_key     = str(body.season)

    if yr_key not in water_bets:
        water_bets[yr_key] = []

    # Generate ID
    existing_count = len(water_bets[yr_key])
    bet_id = f"wb_{body.season}_{existing_count + 1:03d}"

    water_bets[yr_key].append({
        "id":                      bet_id,
        "season":                  body.season,
        "ending_week":             body.ending_week,
        "submitted_at":            _now(),
        "submitted_by":            body.submitted_by,
        "submitted_by_display":    body.submitted_by_display,
        "opposing_manager":        body.opposing_manager,
        "opposing_manager_display":body.opposing_manager_display,
        "bet_text":                body.bet_text,
        "result":                  "waiting",
        "result_updated_by":       None,
        "result_updated_at":       None,
    })

    _save("water_bets.json", water_bets)
    _commit("data/betting/water_bets.json",
                f"Water bet added: {body.submitted_by} vs {body.opposing_manager} ({body.season})")
    return {"status": "created", "id": bet_id}


# ===========================================================================
# POST /betting/water-bets/{id}/result
# ===========================================================================

@router.post("/water-bets/{bet_id}/result")
def update_water_bet_result(bet_id: str, body: WaterBetResult):
    """
    Update a water bet result.
    result: submitter_wins | opponent_wins | waiting (reset)
    """
    if body.result not in VALID_BET_RESULTS:
        raise HTTPException(status_code=400,
            detail=f"Invalid result '{body.result}'. Must be: {VALID_BET_RESULTS}")

    water_bets = _load("water_bets.json")

    # Find bet across all seasons
    found_bet = None
    found_yr  = None
    for yr, bets in water_bets.items():
        if not isinstance(bets, list): continue
        for bet in bets:
            if bet.get("id") == bet_id:
                found_bet = bet
                found_yr  = yr
                break
        if found_bet: break

    if not found_bet:
        raise HTTPException(status_code=404, detail=f"Water bet '{bet_id}' not found.")

    # Derive result from winner_id
    if body.winner_id == found_bet.get("submitted_by"):
        result = "submitter_wins"
    elif body.winner_id == found_bet.get("opposing_manager"):
        result = "opponent_wins"
    elif body.winner_id == "reset":
        result = "waiting"
    else:
        raise HTTPException(status_code=400,
            detail=f"winner_id must be '{found_bet.get('submitted_by')}', "
                   f"'{found_bet.get('opposing_manager')}', or 'reset'.")

    found_bet["result"]            = result
    found_bet["result_updated_by"] = body.updated_by
    found_bet["result_updated_at"] = _now()

    _save("water_bets.json", water_bets)
    _commit("data/betting/water_bets.json",
                f"Water bet result: {bet_id} winner={body.winner_id}")
    return {
        "status":    "updated",
        "id":        bet_id,
        "result":    result,
        "winner_id": body.winner_id,
    }


# ===========================================================================
# GET /betting/season
# ===========================================================================

@router.get("/season/{year}")
def betting_season_by_year(year: int):
    """Season betting summary for a specific year."""
    return _betting_season_inner(year)


@router.get("/season")
def betting_season(
    season: Optional[int] = Query(default=None),
):
    """
    Season-level betting summary — parlays + water bets for one season.

    Parlay stats per manager:
      - total_hit, total_miss, total_no_leg, total_weeks
      - hit_pct, current_streak (consecutive hit/miss from latest week)
      - solo_hit: weeks you were the ONLY hit leg
      - solo_miss: weeks you were the ONLY missed leg

    Water bet stats per manager:
      - total as submitter and as opponent
      - wins and losses in each role
    """
    if season is None:
        season, _ = _current_season_week("")
    return _betting_season_inner(season)


def _betting_season_inner(season: int) -> dict:
    parlays    = _load("parlays.json")
    water_bets = _load("water_bets.json")
    yr_key     = str(season)

    yr_parlays = parlays.get(yr_key, {})
    yr_wbets   = water_bets.get(yr_key, [])

    # ── parlay stats ──────────────────────────────────────────────────────────
    mgr_parlay: dict = {
        m["manager_id"]: {
            "manager_id":    m["manager_id"],
            "display_name":  m["display_name"],
            "total_hit":     0,
            "total_miss":    0,
            "total_no_leg":  0,
            "total_waiting": 0,
            "total_weeks":   0,
            "solo_hit":      0,
            "solo_miss":     0,
            "_streak_results": [],   # for streak calc, newest-first
        }
        for m in ACTIVE_MEMBERS
    }

    # Process weeks newest-first for streak
    sorted_weeks = sorted(
        [k for k in yr_parlays if k.startswith("week_")],
        key=lambda x: int(x.replace("week_","")),
        reverse=True
    )

    for wk_key in sorted_weeks:
        wk_data = yr_parlays[wk_key]
        legs    = wk_data.get("legs", [])
        wr      = _week_result(legs)

        for leg in legs:
            mid = leg.get("manager_id")
            if mid not in mgr_parlay: continue
            result = leg.get("result", "waiting")
            m = mgr_parlay[mid]
            m["total_weeks"] += 1
            if result == "hit":
                m["total_hit"] += 1
                m["_streak_results"].append("hit")
                if wr["total_hit"] == 1:
                    m["solo_hit"] += 1
            elif result == "miss":
                m["total_miss"] += 1
                m["_streak_results"].append("miss")
                if wr["total_miss"] == 1:
                    m["solo_miss"] += 1
            elif result == "no_leg":
                m["total_no_leg"] += 1
                m["_streak_results"].append("no_leg")
            else:
                m["total_waiting"] += 1
                m["_streak_results"].append("waiting")

    # Compute streak and hit_pct, clean up temp field
    for mid, m in mgr_parlay.items():
        active_weeks = m["total_hit"] + m["total_miss"]
        m["hit_pct"] = round(m["total_hit"] / active_weeks * 100, 1) if active_weeks else None

        # Streak: walk newest-first, skip no_leg and waiting
        streak_type  = None
        streak_count = 0
        for r in m["_streak_results"]:
            if r in ("no_leg", "waiting"): continue
            if streak_type is None:
                streak_type  = r
                streak_count = 1
            elif r == streak_type:
                streak_count += 1
            else:
                break
        m["current_streak"] = {
            "type":  streak_type,
            "count": streak_count,
        }
        del m["_streak_results"]

    # ── water bet stats ───────────────────────────────────────────────────────
    mgr_water: dict = {
        m["manager_id"]: {
            "manager_id":    m["manager_id"],
            "display_name":  m["display_name"],
            "as_submitter":  {"total":0,"wins":0,"losses":0,"waiting":0},
            "as_opponent":   {"total":0,"wins":0,"losses":0,"waiting":0},
        }
        for m in ACTIVE_MEMBERS
    }

    for bet in yr_wbets:
        sub  = bet.get("submitted_by")
        opp  = bet.get("opposing_manager")
        res  = bet.get("result","waiting")

        if sub in mgr_water:
            s = mgr_water[sub]["as_submitter"]
            s["total"] += 1
            if res == "submitter_wins":   s["wins"]    += 1
            elif res == "opponent_wins":  s["losses"]  += 1
            else:                         s["waiting"] += 1

        if opp in mgr_water:
            o = mgr_water[opp]["as_opponent"]
            o["total"] += 1
            if res == "opponent_wins":    o["wins"]    += 1
            elif res == "submitter_wins": o["losses"]  += 1
            else:                         o["waiting"] += 1

    # ── week-by-week parlay summary ───────────────────────────────────────────
    weeks_summary = []
    for wk_key in sorted(
        [k for k in yr_parlays if k.startswith("week_")],
        key=lambda x: int(x.replace("week_",""))
    ):
        wk_num  = int(wk_key.replace("week_",""))
        wk_data = yr_parlays[wk_key]
        wr      = _week_result(wk_data.get("legs", []))
        weeks_summary.append({
            "week":        wk_num,
            "entered_by":  wk_data.get("entered_by"),
            "legs":        wk_data.get("legs", []),
            "week_result": wr,
        })

    return {
        "season":           season,
        "parlay_stats":     list(mgr_parlay.values()),
        "water_bet_stats":  list(mgr_water.values()),
        "weeks":            weeks_summary,
        "water_bets":       sorted(yr_wbets,
                                   key=lambda x: x.get("submitted_at",""),
                                   reverse=True),
    }


# ===========================================================================
# GET /betting/overall
# ===========================================================================

@router.get("/overall")
def betting_overall():
    """
    All-time betting summary across all seasons.
    Same stats as /season but accumulated across every season.
    """
    parlays    = _load("parlays.json")
    water_bets = _load("water_bets.json")

    mgr_parlay: dict = {
        m["manager_id"]: {
            "manager_id":    m["manager_id"],
            "display_name":  m["display_name"],
            "total_hit":     0,
            "total_miss":    0,
            "total_no_leg":  0,
            "total_waiting": 0,
            "total_weeks":   0,
            "solo_hit":      0,
            "solo_miss":     0,
            "seasons":       0,
        }
        for m in ACTIVE_MEMBERS
    }

    mgr_water: dict = {
        m["manager_id"]: {
            "manager_id":    m["manager_id"],
            "display_name":  m["display_name"],
            "as_submitter":  {"total":0,"wins":0,"losses":0,"waiting":0},
            "as_opponent":   {"total":0,"wins":0,"losses":0,"waiting":0},
        }
        for m in ACTIVE_MEMBERS
    }

    # Track which seasons each manager participated in parlays
    mgr_seasons: dict = {m["manager_id"]: set() for m in ACTIVE_MEMBERS}

    for yr, yr_parlays in sorted(parlays.items()):
        if not isinstance(yr_parlays, dict): continue
        for wk_key, wk_data in yr_parlays.items():
            if not wk_key.startswith("week_"): continue  # skip season_bet
            legs = wk_data.get("legs", [])
            wr   = _week_result(legs)

            for leg in legs:
                mid = leg.get("manager_id")
                if mid not in mgr_parlay: continue
                result = leg.get("result", "waiting")
                m = mgr_parlay[mid]
                m["total_weeks"] += 1
                mgr_seasons[mid].add(yr)
                if result == "hit":
                    m["total_hit"] += 1
                    if wr["total_hit"] == 1: m["solo_hit"] += 1
                elif result == "miss":
                    m["total_miss"] += 1
                    if wr["total_miss"] == 1: m["solo_miss"] += 1
                elif result == "no_leg":
                    m["total_no_leg"] += 1
                else:
                    m["total_waiting"] += 1

    for yr, bets in water_bets.items():
        if not isinstance(bets, list): continue
        for bet in bets:
            sub = bet.get("submitted_by")
            opp = bet.get("opposing_manager")
            res = bet.get("result","waiting")
            if sub in mgr_water:
                s = mgr_water[sub]["as_submitter"]
                s["total"] += 1
                if res == "submitter_wins":   s["wins"]    += 1
                elif res == "opponent_wins":  s["losses"]  += 1
                else:                         s["waiting"] += 1
            if opp in mgr_water:
                o = mgr_water[opp]["as_opponent"]
                o["total"] += 1
                if res == "opponent_wins":    o["wins"]    += 1
                elif res == "submitter_wins": o["losses"]  += 1
                else:                         o["waiting"] += 1

    # Finalize parlay stats
    for mid, m in mgr_parlay.items():
        m["seasons"] = len(mgr_seasons[mid])
        active = m["total_hit"] + m["total_miss"]
        m["hit_pct"] = round(m["total_hit"] / active * 100, 1) if active else None

    # Sort by hit_pct desc
    parlay_sorted = sorted(mgr_parlay.values(),
                           key=lambda x: -(x["hit_pct"] or 0))
    water_sorted  = sorted(mgr_water.values(),
                           key=lambda x: -(x["as_submitter"]["wins"] +
                                           x["as_opponent"]["wins"]))

    # Season index
    all_seasons = sorted(
        [int(k) for k in set(list(parlays.keys()) + list(water_bets.keys()))
         if k.isdigit()],
        reverse=True
    )

    return {
        "seasons_tracked":  all_seasons,
        "parlay_stats":     parlay_sorted,
        "water_bet_stats":  water_sorted,
    }