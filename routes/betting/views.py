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
    "week_3": {
      "entered_by": "frank",
      "entered_at": "2026-10-01T12:00:00",
      "legs": [
        {
          "manager_id": "blake",
          "display_name": "Blake",
          "bet_text": "Mahomes over 2.5 TDs",
          "result": "waiting",      // waiting | hit | miss | no_leg
          "updated_by": null,
          "updated_at": null
        },
        ... one per active member
      ]
    }
  }
}

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


def _current_season_week(matchups_path: str) -> tuple:
    """
    Detect current season and upcoming week from matchups.json.
    Returns (season_int, next_week_int).
    """
    try:
        data_dir = os.path.join(_PROJECT_ROOT, "data", "fantasy")
        mu_path  = os.path.join(data_dir, "matchups.json")
        if not os.path.exists(mu_path):
            return (datetime.now().year, 1)
        with open(mu_path) as f:
            matchups = json.load(f)
        latest_yr = max((int(k) for k in matchups if k.isdigit()), default=datetime.now().year)
        yr_data   = matchups.get(str(latest_yr), {})
        ps        = yr_data.get("playoff_start") or 99
        completed = [
            wk["week"] for wk in yr_data.get("weeks", [])
            if wk.get("week", 0) < ps
            and all(t.get("points", 0) > 0
                    for m in wk.get("matchups", [])
                    for t in m.get("teams", []))
        ]
        next_wk = (max(completed) + 1) if completed else 1
        return (latest_yr, next_wk)
    except Exception:
        return (datetime.now().year, 1)


def _week_result(legs: list) -> dict:
    """Compute aggregate result from a list of legs."""
    counts = {"hit": 0, "miss": 0, "waiting": 0, "no_leg": 0}
    for leg in legs:
        r = leg.get("result", "waiting")
        counts[r] = counts.get(r, 0) + 1
    active = [l for l in legs if l.get("result") != "no_leg"]
    return {
        "total_hit":     counts["hit"],
        "total_miss":    counts["miss"],
        "total_waiting": counts["waiting"],
        "total_no_leg":  counts["no_leg"],
        "is_complete":   counts["waiting"] == 0,
        "hit_pct": round(counts["hit"] / len(active) * 100, 1) if active else None,
    }


# ── Pydantic models ───────────────────────────────────────────────────────────

class ParlaySubmit(BaseModel):
    season:      int
    week:        int
    entered_by:  str
    legs: list[dict]   # [{manager_id, bet_text}] — 1 per member max


class LegUpdate(BaseModel):
    updated_by: str
    result:     str    # hit | miss | no_leg


class WaterBetSubmit(BaseModel):
    season:                  int
    week:                    int
    submitted_by:            str
    submitted_by_display:    str
    opposing_manager:        str
    opposing_manager_display:str
    bet_text:                str


class WaterBetResult(BaseModel):
    updated_by: str
    result:     str   # submitter_wins | opponent_wins


# ===========================================================================
# GET /betting/parlays
# ===========================================================================

@router.get("/parlays")
def get_parlays(
    season: Optional[int] = Query(default=None),
    week:   Optional[int] = Query(default=None),
):
    import traceback
    try:
        return _get_parlays_inner(season, week)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{str(e)}\n{traceback.format_exc()[:800]}")


def _get_parlays_inner(season, week):
    """
    Returns parlay data.

    No params → current season, upcoming week (auto-detected).
    ?season=2026&week=3 → specific week.

    Response includes:
      - active_members list (for enter-parlay UI)
      - current week's legs with results
      - is_complete flag
    """
    parlays = _load("parlays.json")

    if season is None or week is None:
        detected_season, detected_week = _current_season_week("")
        season = season or detected_season
        week   = week   or detected_week

    yr_key = str(season)
    wk_key = f"week_{week}"

    yr_data = parlays.get(yr_key, {})
    wk_data = yr_data.get(wk_key)

    # Build available weeks for navigation
    available = []
    for yr, wks in sorted(parlays.items(), reverse=True):
        if not isinstance(wks, dict): continue   # skip _note, _results keys
        for wk_k in sorted(wks.keys(), reverse=True):
            wk_n = int(wk_k.replace("week_", ""))
            wk_d = wks[wk_k]
            available.append({
                "season":      int(yr),
                "week":        wk_n,
                "is_complete": _week_result(wk_d.get("legs", [])).get("is_complete", False),
            })

    return {
        "season":         season,
        "week":           week,
        "active_members": ACTIVE_MEMBERS,
        "parlay":         {
            "entered_by":  wk_data.get("entered_by")  if wk_data else None,
            "entered_at":  wk_data.get("entered_at")  if wk_data else None,
            "legs":        wk_data.get("legs", [])    if wk_data else [],
            "week_result": _week_result(wk_data.get("legs", [])) if wk_data else None,
            "exists":      wk_data is not None,
        },
        "available_weeks": available,
    }


# ===========================================================================
# POST /betting/parlays/submit
# ===========================================================================

@router.post("/parlays/submit")
def submit_parlay(body: ParlaySubmit):
    """
    Enter a new parlay week. One leg per active member max.
    Honor system — entered_by field identifies who submitted.

    legs format: [{manager_id: "blake", bet_text: "..."}]
    Members not included get a blank "waiting" leg with no bet_text.
    """
    parlays = _load("parlays.json")
    yr_key  = str(body.season)
    wk_key  = f"week_{body.week}"

    if yr_key not in parlays:
        parlays[yr_key] = {}
    if wk_key in parlays[yr_key]:
        raise HTTPException(status_code=409,
            detail=f"Parlay for {body.season} week {body.week} already exists. "
                   f"Use update-leg to change individual legs.")

    # Build legs — ensure all active members present
    leg_map = {l["manager_id"]: l.get("bet_text", "") for l in body.legs
               if l.get("manager_id") in ACTIVE_IDS}

    legs = []
    for m in ACTIVE_MEMBERS:
        mid = m["manager_id"]
        legs.append({
            "manager_id":   mid,
            "display_name": m["display_name"],
            "bet_text":     leg_map.get(mid, ""),
            "result":       "waiting",
            "updated_by":   None,
            "updated_at":   None,
        })

    parlays[yr_key][wk_key] = {
        "entered_by": body.entered_by,
        "entered_at": _now(),
        "legs":       legs,
    }

    _save("parlays.json", parlays)
    return {
        "status":  "created",
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

    _save("parlays.json", parlays)
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
        "week":                    body.week,
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

    found_bet["result"]            = body.result
    found_bet["result_updated_by"] = body.updated_by
    found_bet["result_updated_at"] = _now()

    _save("water_bets.json", water_bets)
    return {
        "status": "updated",
        "id":     bet_id,
        "result": body.result,
    }


# ===========================================================================
# GET /betting/season
# ===========================================================================

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
    sorted_weeks = sorted(yr_parlays.keys(),
                          key=lambda x: int(x.replace("week_","")),
                          reverse=True)

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
    for wk_key in sorted(yr_parlays.keys(),
                          key=lambda x: int(x.replace("week_",""))):
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