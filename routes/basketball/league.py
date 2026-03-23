"""
routes/basketball/league.py
============================
All data-generation and exploration endpoints for the Real Bros NBA league.

URL prefix: /basketball/league
Mounted in main.py:
    from routes.basketball.league import router as basketball_league_router
    app.include_router(basketball_league_router)

League info
-----------
  league_key : 466.l.38685  (or season-specific key discovered via /explore)
  league_id  : 38685
  league_name: Real Bros

Data pipeline pattern per file
-------------------------------
  GET /basketball/league/data/<file>/build-all?skip_existing=true   ← weekly refresh
  GET /basketball/league/data/<file>/build-all?force_clean=true     ← full rebuild
  GET /basketball/league/data/<file>/status                         ← enrichment state
  GET /basketball/league/data/<file>/download                       ← save to local git

Files: managers, results, transactions, drafts

Notes
-----
- NBA seasons span two calendar years; league keys use a game_id prefix that
  increments each season (e.g. 428.l.38685 for 2024-25).
- Use /basketball/league/explore to discover all season keys before building data.
- Playoff definition: top seeds only (Yahoo flags consolation rounds as playoffs —
  use is_consolation flag or seed cutoff to exclude them).
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from routes.auth import require_permission

router = APIRouter(prefix="/basketball/league", tags=["Basketball League"])

# Known league constants
NBA_LEAGUE_ID   = "38685"
NBA_LEAGUE_NAME = "Real Bros"

# Known NBA Yahoo game_ids by season-start year (update annually)
NBA_GAME_IDS = {
    2024: 428,
    2023: 418,
    2022: 406,
    2021: 396,
    2020: 385,
    2019: 375,
    2018: 363,
    2017: 352,
    2016: 341,
    2015: 331,
    2014: 321,
    2013: 310,
    2012: 299,
    2011: 285,
    2010: 271,
}


# ===========================================================================
# Shared helpers
# ===========================================================================

def _get_data_path(filename: str) -> str:
    import os
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "basketball", filename,
    )


def _load_json(path: str) -> dict:
    import json, os
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _write_json(path: str, data: dict):
    import json, os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _year_sort(d: dict) -> dict:
    return dict(sorted(d.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else -1, reverse=True))


def _get_all_nba_season_keys() -> dict:
    """
    Returns a dict of {season_start_year: league_key} for all known NBA seasons.
    Tries each game_id from NBA_GAME_IDS against the fixed league_id.
    Results are cached in data/basketball/season_keys.json to avoid redundant API calls.
    """
    import os, json

    cache_path = _get_data_path("season_keys.json")
    if os.path.exists(cache_path):
        cached = _load_json(cache_path)
        if cached:
            return cached

    return {}  # Return empty — populate via /explore/discover-seasons


def _league_key_for_season(year: int | str) -> str:
    """
    Return the correct league_key for a given NBA season start year.
    Looks up the cache; raises ValueError if not found.
    """
    yr  = int(year)
    keys = _get_all_nba_season_keys()
    if str(yr) in keys:
        return keys[str(yr)]
    # Fallback: construct directly if game_id is known
    if yr in NBA_GAME_IDS:
        return f"{NBA_GAME_IDS[yr]}.l.{NBA_LEAGUE_ID}"
    raise ValueError(
        f"No league key found for NBA season {yr}. "
        f"Run GET /basketball/league/explore/discover-seasons first."
    )


def _extract_player_from_yfpy(pw: dict) -> dict:
    """
    Extract player info from a YFPY player entry.
    Handles both {"player": {...}} wrapped and flat shapes.
    name is always {"full": "..."} in YFPY.
    transaction_data is always a list — take [0].
    """
    p = pw.get("player", pw) if isinstance(pw, dict) else {}

    name_raw = p.get("name", {})
    if isinstance(name_raw, dict):
        name = name_raw.get("full") or p.get("full_name") or "Unknown"
    else:
        name = p.get("full_name") or str(name_raw) or "Unknown"

    td_raw = p.get("transaction_data", [])
    if isinstance(td_raw, list):
        td = td_raw[0] if td_raw else {}
    elif isinstance(td_raw, dict):
        td = td_raw
    else:
        td = {}

    return {
        "name":       name,
        "position":   p.get("display_position") or p.get("primary_position"),
        "player_key": p.get("player_key"),
        "td":         td,
    }


def _unwrap_picks_raw(draft_raw, convert_fn) -> list:
    """
    Safely extract a flat list of pick dicts from a YFPY draft response.
    Handles all YFPY return shapes including the numbered-dict collapse bug.
    """
    if isinstance(draft_raw, list):
        return draft_raw
    converted = convert_fn(draft_raw)
    if isinstance(converted, list):
        return converted
    if not isinstance(converted, dict):
        return []
    for key in ("draft_results", "picks", "draft_result"):
        val = converted.get(key)
        if isinstance(val, list) and val:
            return val
    keys = list(converted.keys())
    if keys and all(str(k).isdigit() for k in keys):
        return [converted[k] for k in sorted(keys, key=lambda x: int(x))]
    return [v for v in converted.values()
            if isinstance(v, dict) and ("player_key" in v or "team_key" in v)]


def _build_week_map(query, league_key: str) -> list:
    """Build week→date-range map using game weeks API."""
    from services.fantasy.league_service import _convert_to_dict
    try:
        game_id = str(league_key).split(".")[0]
        data    = _convert_to_dict(query.get_game_weeks_by_game_id(game_id))
        weeks   = data if isinstance(data, list) else data.get("game_weeks", [])
        result  = []
        for w in weeks:
            week_obj = w.get("game_week", w) if isinstance(w, dict) else {}
            result.append({
                "week":       int(week_obj.get("week") or week_obj.get("display_name") or 0),
                "start_date": week_obj.get("start") or week_obj.get("start_date"),
                "end_date":   week_obj.get("end")   or week_obj.get("end_date"),
            })
        return sorted(result, key=lambda x: x["week"])
    except Exception:
        return []


def _date_to_week(date_str: str, week_map: list) -> int | None:
    if not date_str or not week_map:
        return None
    try:
        import datetime
        d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        for w in week_map:
            try:
                start = datetime.datetime.strptime(w["start_date"], "%Y-%m-%d").date()
                end   = datetime.datetime.strptime(w["end_date"],   "%Y-%m-%d").date()
                if start <= d <= end:
                    return w["week"]
            except (TypeError, ValueError):
                continue
    except (TypeError, ValueError):
        pass
    return None


# ===========================================================================
# Season discovery + exploration
# ===========================================================================

@router.get("/seasons")
def get_nba_seasons():
    """
    Returns all known Real Bros NBA seasons with their league keys.
    Populated from the season_keys.json cache (built by /explore/discover-seasons).
    """
    keys = _get_all_nba_season_keys()
    if not keys:
        return {
            "message": "No seasons cached yet.",
            "next_step": "Run GET /basketball/league/explore/discover-seasons to build the cache.",
            "seasons": [],
        }
    seasons = [
        {"season_year": int(yr), "league_key": lk}
        for yr, lk in sorted(keys.items(), reverse=True)
    ]
    return {"total_seasons": len(seasons), "seasons": seasons}


@router.get("/explore/discover-seasons")
def discover_nba_seasons(save: bool = Query(default=True, description="Save results to season_keys.json")):
    """
    Discovers all Real Bros NBA seasons by trying each known game_id against
    league_id 38685. Saves results to data/basketball/season_keys.json.

    Run this once to bootstrap, then re-run each new season.

    Usage:
        GET /basketball/league/explore/discover-seasons
        GET /basketball/league/explore/discover-seasons?save=false  (dry run)
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        found  = {}
        errors = []

        for season_year, game_id in sorted(NBA_GAME_IDS.items(), reverse=True):
            league_key = f"{game_id}.l.{NBA_LEAGUE_ID}"
            try:
                query = get_query(league_key)
                meta  = _convert_to_dict(query.get_league_metadata())
                # Verify it's actually our league
                if str(meta.get("league_id")) == NBA_LEAGUE_ID or \
                   (meta.get("name") and NBA_LEAGUE_NAME.lower() in str(meta.get("name", "")).lower()):
                    found[str(season_year)] = league_key
                    errors.append({
                        "season_year": season_year,
                        "league_key":  league_key,
                        "status":      "✅ found",
                        "league_name": meta.get("name"),
                        "season":      meta.get("season"),
                        "num_teams":   meta.get("num_teams"),
                        "is_finished": meta.get("is_finished"),
                    })
                else:
                    errors.append({
                        "season_year": season_year,
                        "league_key":  league_key,
                        "status":      "⚠️ different league",
                        "name_found":  meta.get("name"),
                    })
            except Exception as e:
                errors.append({
                    "season_year": season_year,
                    "league_key":  league_key,
                    "status":      f"❌ {str(e)[:80]}",
                })

        if save and found:
            _write_json(_get_data_path("season_keys.json"), found)

        return {
            "league_id":       NBA_LEAGUE_ID,
            "seasons_found":   len(found),
            "season_keys":     found,
            "details":         errors,
            "saved":           save and bool(found),
            "next_step":       "Run GET /basketball/league/explore/season/{year} to inspect any season.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/season/{year}")
def explore_nba_season(year: str):
    """
    Shows ALL available data for a Real Bros NBA season from the Yahoo API.
    Use this to understand what fields are available before building data files.

    Usage: GET /basketball/league/explore/season/2024
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        league_key = _league_key_for_season(year)
        query      = get_query(league_key)
        data       = {}
        team_key   = None

        for label, fetcher in [
            ("league_metadata",   lambda: query.get_league_metadata()),
            ("league_settings",   lambda: query.get_league_settings()),
            ("league_standings",  lambda: query.get_league_standings()),
            ("scoreboard_week_1", lambda: query.get_league_scoreboard_by_week(1)),
            ("league_teams",      lambda: query.get_league_teams()),
            ("draft_results",     lambda: query.get_league_draft_results()),
            ("transactions",      lambda: query.get_league_transactions()),
        ]:
            try:
                data[label] = _convert_to_dict(fetcher())
            except Exception as e:
                data[label] = {"error": str(e)}

        # Sample roster / stats / matchups for first team
        try:
            teams_dict = _convert_to_dict(query.get_league_teams())
            teams_list = teams_dict if isinstance(teams_dict, list) else teams_dict.get("teams", [])
            first      = teams_list[0] if teams_list else {}
            first_team = first.get("team", first) if isinstance(first, dict) else {}
            team_key   = first_team.get("team_key")
        except Exception:
            pass

        if team_key:
            for label, fetcher in [
                ("sample_team_roster_week_1", lambda: query.get_team_roster_by_week(team_key, 1)),
                ("sample_team_stats_week_1",  lambda: query.get_team_stats_by_week(team_key, 1)),
                ("sample_team_matchups",      lambda: query.get_team_matchups(team_key)),
            ]:
                try:
                    data[label] = _convert_to_dict(fetcher())
                except Exception as e:
                    data[label] = {"error": str(e)}

        return {
            "year":           year,
            "league_key":     league_key,
            "available_data": data,
            "note":           "Use these field names when building data files.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/availability-matrix")
def check_nba_data_availability():
    """
    Tests what data is available across sample NBA seasons.
    Useful for understanding which historical seasons have full data.
    """
    try:
        from services.yahoo_service import get_query

        known_years = sorted(NBA_GAME_IDS.keys(), reverse=True)
        test_years  = known_years[:5]  # test 5 most recent
        results     = []

        for yr in test_years:
            league_key   = f"{NBA_GAME_IDS[yr]}.l.{NBA_LEAGUE_ID}"
            availability = {"year": yr, "league_key": league_key, "data_available": {}}
            try:
                query = get_query(league_key)
                for dtype, fetcher in [
                    ("standings",         lambda: query.get_league_standings()),
                    ("settings",          lambda: query.get_league_settings()),
                    ("teams",             lambda: query.get_league_teams()),
                    ("draft_results",     lambda: query.get_league_draft_results()),
                    ("transactions",      lambda: query.get_league_transactions()),
                    ("scoreboard_week_1", lambda: query.get_league_scoreboard_by_week(1)),
                ]:
                    try:
                        fetcher()
                        availability["data_available"][dtype] = "✅ Available"
                    except Exception as e:
                        availability["data_available"][dtype] = f"❌ {str(e)[:50]}"
            except Exception as e:
                availability["error"] = str(e)
            results.append(availability)

        return {
            "tested_years": test_years,
            "results":      results,
            "note":         "Run /explore/discover-seasons first if results show errors.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/raw-league-key/{league_key}")
def explore_by_league_key(league_key: str):
    """
    Explore any league key directly — useful when you have the exact key.
    league_key format: 428.l.38685  (use dots, not slashes)

    Usage: GET /basketball/league/explore/raw-league-key/428.l.38685
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        query = get_query(league_key)
        data  = {}

        for label, fetcher in [
            ("league_metadata",  lambda: query.get_league_metadata()),
            ("league_settings",  lambda: query.get_league_settings()),
            ("league_standings", lambda: query.get_league_standings()),
            ("league_teams",     lambda: query.get_league_teams()),
            ("draft_results",    lambda: query.get_league_draft_results()),
            ("transactions",     lambda: query.get_league_transactions()),
            ("scoreboard_week_1",lambda: query.get_league_scoreboard_by_week(1)),
        ]:
            try:
                data[label] = _convert_to_dict(fetcher())
            except Exception as e:
                data[label] = {"error": str(e)[:100]}

        return {"league_key": league_key, "available_data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/yfpy-methods")
def get_yfpy_methods():
    """Returns all available YFPY query methods for debugging."""
    try:
        from services.yahoo_service import get_query
        league_key = _league_key_for_season(max(NBA_GAME_IDS.keys()))
        query      = get_query(league_key)
        methods    = [m for m in dir(query) if not m.startswith("_")]
        return {
            "user_related":  [m for m in methods if "user"   in m.lower()],
            "league_related":[m for m in methods if "league" in m.lower()],
            "game_related":  [m for m in methods if "game"   in m.lower()],
            "all_methods":   methods,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/season/{year}/settings")
def nba_season_settings(year: str):
    """League settings for a given NBA season start year."""
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        league_key = _league_key_for_season(year)
        query      = get_query(league_key)
        return _convert_to_dict(query.get_league_settings())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/season/{year}/standings")
def nba_season_standings(year: str):
    """League standings for a given NBA season start year."""
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        league_key = _league_key_for_season(year)
        query      = get_query(league_key)
        return _convert_to_dict(query.get_league_standings())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Data generation — managers.json
# ===========================================================================

@router.get("/data/managers/build-all")
def build_nba_managers(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None, description="Single year e.g. '2024', or omit for all"),
    force_clean: bool  = Query(default=False),
):
    """
    Generates data/basketball/managers.json — team and manager info per season.
    Keyed by season start year: {"2024": {"managers": [...], ...}}

    Usage:
        GET /basketball/league/data/managers/build-all
        GET /basketball/league/data/managers/build-all?year=2024
        GET /basketball/league/data/managers/build-all?force_clean=true
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict, _safe_get
        from services.fantasy.team_service import _extract_teams_list

        path     = _get_data_path("managers.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        season_keys = _get_all_nba_season_keys()
        if not season_keys:
            raise HTTPException(
                status_code=400,
                detail="No season keys cached. Run GET /basketball/league/explore/discover-seasons first.",
            )

        all_years    = sorted(season_keys.keys())
        target_years = [year] if year else all_years
        results      = {"success": [], "skipped": [], "failed": {}}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr].get("url") is not None:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key     = season_keys.get(str(yr)) or _league_key_for_season(yr)
                query          = get_query(league_key)
                meta           = _convert_to_dict(query.get_league_metadata())
                standings_dict = _convert_to_dict(query.get_league_standings())
                teams_list     = _extract_teams_list(standings_dict)

                managers = []
                for t in teams_list:
                    if not isinstance(t, dict):
                        continue
                    team_key = t.get("team_key", "")
                    team_id  = team_key.split(".t.")[-1] if ".t." in team_key else ""

                    managers_raw = t.get("managers", {})
                    if isinstance(managers_raw, list):
                        mgr_wrapper = managers_raw[0] if managers_raw else {}
                    else:
                        mgr_wrapper = managers_raw
                    mgr = mgr_wrapper.get("manager", mgr_wrapper) if isinstance(mgr_wrapper, dict) else {}

                    guid         = mgr.get("guid")
                    nickname     = mgr.get("nickname")
                    is_comanager = bool(int(mgr.get("is_comanager", 0) or 0))

                    logos    = t.get("team_logos", {})
                    if isinstance(logos, list): logos = logos[0] if logos else {}
                    logo_obj = logos.get("team_logo", {}) if isinstance(logos, dict) else {}
                    if isinstance(logo_obj, list): logo_obj = logo_obj[0] if logo_obj else {}
                    team_logo = logo_obj.get("url") if isinstance(logo_obj, dict) else None

                    managers.append({
                        "guid":         guid,
                        "nickname":     nickname,
                        "team_key":     team_key,
                        "team_id":      team_id,
                        "team_name":    t.get("name"),
                        "is_comanager": is_comanager,
                        "logo_url":     team_logo,
                        "team_url":     t.get("url"),
                    })

                managers.sort(key=lambda m: int(m["team_id"]) if str(m["team_id"]).isdigit() else 0)

                existing[yr] = {
                    "year":        int(yr),
                    "league_key":  league_key,
                    "league_id":   _safe_get(meta, "league_id") or NBA_LEAGUE_ID,
                    "league_name": _safe_get(meta, "name") or NBA_LEAGUE_NAME,
                    "url":         _safe_get(meta, "url"),
                    "logo_url":    _safe_get(meta, "logo_url"),
                    "num_teams":   _safe_get(meta, "num_teams"),
                    "season":      _safe_get(meta, "season"),
                    "is_finished": bool(int(_safe_get(meta, "is_finished") or 0)),
                    "managers":    managers,
                }
                results["success"].append(int(yr))
            except Exception as e:
                results["failed"][yr] = str(e)

        sorted_data = _year_sort({k: v for k, v in existing.items() if str(k).isdigit()})
        _write_json(path, sorted_data)

        return {
            "status":          "complete",
            "seasons_updated": results["success"],
            "seasons_skipped": results["skipped"],
            "seasons_failed":  results["failed"],
            "total_seasons":   len(sorted_data),
            "file_written":    path,
            "next_step":       "GET /basketball/league/data/managers/download to save locally",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/managers/status")
def nba_managers_status():
    """Shows which years are in managers.json and enrichment state."""
    try:
        path = _get_data_path("managers.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season = data[yr]
            managers = season.get("managers", [])
            summary.append({
                "year":          int(yr),
                "num_managers":  len(managers),
                "league_enriched": season.get("url") is not None,
                "needs_api_call":  season.get("url") is None,
            })
        return {
            "total_seasons":    len(data),
            "fully_enriched":   sum(1 for s in summary if not s["needs_api_call"]),
            "needs_enrichment": [s["year"] for s in summary if s["needs_api_call"]],
            "seasons":          summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/managers/download")
def download_nba_managers():
    """Returns current managers.json for local save."""
    try:
        data = _load_json(_get_data_path("managers.json"))
        if not data:
            raise HTTPException(status_code=404, detail="managers.json not found. Run build-all first.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Data generation — results.json
# ===========================================================================

def _build_nba_results_for_season(yr: str, query, league_key: str) -> dict:
    """
    Fetch standings + scoreboard for one NBA season.
    Returns dict keyed by team_key (NBA doesn't have a global manager identity map yet).

    Structure mirrors the NFL version for frontend consistency:
      {team_key: {team_name, regular_season: {...}, playoffs: {...}}}
    """
    from services.fantasy.league_service import _convert_to_dict
    from services.fantasy.team_service import (
        _extract_teams_list, _extract_team_standings, _extract_outcome_totals,
    )

    standings_dict = _convert_to_dict(query.get_league_standings())
    teams_list     = _extract_teams_list(standings_dict)

    def _rank_map(field):
        vals = sorted(
            [(t.get("team_key"), float(_extract_team_standings(t).get(field) or 0))
             for t in teams_list if isinstance(t, dict)],
            key=lambda x: x[1], reverse=True,
        )
        return {tk: i + 1 for i, (tk, _) in enumerate(vals)}

    pf_rank_map = _rank_map("points_for")
    pa_rank_map = _rank_map("points_against")

    season_data = {}

    for t in teams_list:
        if not isinstance(t, dict):
            continue
        team_key = t.get("team_key", "")
        ts  = _extract_team_standings(t)
        ot  = _extract_outcome_totals(ts)

        wins   = int(ot.get("wins")   or 0)
        losses = int(ot.get("losses") or 0)
        ties   = int(ot.get("ties")   or 0)
        games  = wins + losses + ties
        pf     = float(ts.get("points_for")    or 0)
        pa     = float(ts.get("points_against") or 0)

        # Manager info
        managers_raw = t.get("managers", {})
        if isinstance(managers_raw, list):
            mgr_wrapper = managers_raw[0] if managers_raw else {}
        else:
            mgr_wrapper = managers_raw
        mgr      = mgr_wrapper.get("manager", mgr_wrapper) if isinstance(mgr_wrapper, dict) else {}
        nickname = mgr.get("nickname") or team_key

        season_data[team_key] = {
            "team_name": t.get("name"),
            "nickname":  nickname,
            "_rs": {
                "wins": wins, "losses": losses, "ties": ties, "games": games,
                "pf": pf, "pa": pa, "proj_pf": 0.0, "proj_pa": 0.0,
                "rank": ts.get("rank"), "seed": ts.get("playoff_seed"),
            },
            "_pl": {
                "wins": 0, "losses": 0, "ties": 0, "games": 0,
                "pf": 0.0, "pa": 0.0, "proj_pf": 0.0, "proj_pa": 0.0,
            },
        }

    # Scoreboard loop
    try:
        settings_dict = _convert_to_dict(query.get_league_settings())
        playoff_start = int(settings_dict.get("playoff_start_week") or 20)
        end_week      = int(settings_dict.get("end_week") or 22)
    except Exception:
        playoff_start, end_week = 20, 22

    for week in range(1, end_week + 1):
        try:
            sb_dict  = _convert_to_dict(query.get_league_scoreboard_by_week(week))
            matchups = sb_dict.get("matchups", []) if isinstance(sb_dict, dict) else \
                       (sb_dict if isinstance(sb_dict, list) else [])
            is_playoff_week = week >= playoff_start

            for m in matchups:
                matchup = m.get("matchup", m) if isinstance(m, dict) else {}
                teams_m = matchup.get("teams", [])
                if isinstance(teams_m, dict):
                    teams_m = list(teams_m.values())

                winner_key = matchup.get("winner_team_key")
                is_tied    = bool(int(matchup.get("is_tied", 0) or 0))

                team_pts  = {}
                team_proj = {}
                tkeys     = []

                for tw in teams_m:
                    tm   = tw.get("team", tw) if isinstance(tw, dict) else {}
                    tk   = tm.get("team_key", "")
                    pts  = float((tm.get("team_points") or {}).get("total") or tm.get("points") or 0)
                    proj = float((tm.get("team_projected_points") or {}).get("total") or 0)
                    team_pts[tk]  = pts
                    team_proj[tk] = proj
                    tkeys.append(tk)

                for tk in tkeys:
                    if tk not in season_data:
                        continue

                    opp_tk   = next((k for k in tkeys if k != tk), None)
                    my_pts   = team_pts.get(tk, 0)
                    opp_pts  = team_pts.get(opp_tk, 0)
                    my_proj  = team_proj.get(tk, 0)
                    opp_proj = team_proj.get(opp_tk, 0)

                    seed_val = season_data[tk]["_rs"].get("seed")
                    try:
                        is_true_playoff = is_playoff_week and int(seed_val or 99) <= 4
                    except (TypeError, ValueError):
                        is_true_playoff = False

                    if is_true_playoff:
                        b = season_data[tk]["_pl"]
                        b["pf"]      = round(b["pf"]      + my_pts,  2)
                        b["pa"]      = round(b["pa"]      + opp_pts, 2)
                        b["proj_pf"] = round(b["proj_pf"] + my_proj, 2)
                        b["proj_pa"] = round(b["proj_pa"] + opp_proj,2)
                        b["games"] += 1
                        if is_tied:            b["ties"]   += 1
                        elif winner_key == tk: b["wins"]   += 1
                        else:                  b["losses"] += 1
                    elif not is_playoff_week:
                        b = season_data[tk]["_rs"]
                        b["proj_pf"] = round(b["proj_pf"] + my_proj, 2)
                        b["proj_pa"] = round(b["proj_pa"] + opp_proj,2)
        except Exception:
            continue

    # Finalise
    def _cross_rank(field, bucket):
        vals = sorted(
            [(tk, d[bucket][field]) for tk, d in season_data.items()],
            key=lambda x: x[1], reverse=True,
        )
        return {tk: i + 1 for i, (tk, _) in enumerate(vals)}

    pl_pf_rank = _cross_rank("pf", "_pl")
    pl_pa_rank = _cross_rank("pa", "_pl")

    for tk, d in season_data.items():
        rs = d["_rs"]
        pl = d["_pl"]
        g_rs, g_pl = rs["games"], pl["games"]

        d["regular_season"] = {
            "wins": rs["wins"], "losses": rs["losses"], "ties": rs["ties"], "games": g_rs,
            "win_pct": round(rs["wins"] / g_rs, 4) if g_rs else None,
            "rank": rs["rank"], "playoff_seed": rs["seed"],
            "points_for":          round(rs["pf"], 2),
            "points_for_rank":     pf_rank_map.get(tk),
            "avg_points_for":      round(rs["pf"] / g_rs, 2) if g_rs else None,
            "points_against":      round(rs["pa"], 2),
            "points_against_rank": pa_rank_map.get(tk),
            "avg_points_against":  round(rs["pa"] / g_rs, 2) if g_rs else None,
        }

        try:
            seed_int = int(d["_rs"].get("seed") or 99)
        except (TypeError, ValueError):
            seed_int = 99

        if seed_int <= 4 and g_pl > 0:
            d["playoffs"] = {
                "made_playoffs": True,
                "wins": pl["wins"], "losses": pl["losses"], "ties": pl["ties"], "games": g_pl,
                "win_pct": round(pl["wins"] / g_pl, 4) if g_pl else None,
                "points_for":          round(pl["pf"], 2),
                "points_for_rank":     pl_pf_rank.get(tk),
                "avg_points_for":      round(pl["pf"] / g_pl, 2),
                "points_against":      round(pl["pa"], 2),
                "points_against_rank": pl_pa_rank.get(tk),
                "avg_points_against":  round(pl["pa"] / g_pl, 2),
            }
        else:
            d["playoffs"] = {"made_playoffs": False}

        del d["_rs"]
        del d["_pl"]

    return season_data


@router.get("/data/results/build-all")
def build_nba_results(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None),
    force_clean: bool  = Query(default=False),
):
    """
    Generates data/basketball/results.json — W-L-T, points, ranks per season.

    Usage:
        GET /basketball/league/data/results/build-all
        GET /basketball/league/data/results/build-all?year=2024
        GET /basketball/league/data/results/build-all?force_clean=true
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict, _safe_get

        path        = _get_data_path("results.json")
        existing    = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}
        season_keys = _get_all_nba_season_keys()

        if not season_keys:
            raise HTTPException(
                status_code=400,
                detail="No season keys cached. Run GET /basketball/league/explore/discover-seasons first.",
            )

        all_years    = sorted(season_keys.keys())
        target_years = [year] if year else all_years
        results      = {"success": [], "skipped": [], "failed": {}}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key  = season_keys.get(str(yr)) or _league_key_for_season(yr)
                query       = get_query(league_key)
                meta        = _convert_to_dict(query.get_league_metadata())
                is_finished = bool(int(_safe_get(meta, "is_finished") or 0))
                season_data = _build_nba_results_for_season(yr, query, league_key)
                existing[yr] = {"is_finished": is_finished, "teams": season_data}
                results["success"].append(int(yr))
            except Exception as e:
                results["failed"][yr] = str(e)

        sorted_data = _year_sort(existing)
        _write_json(path, sorted_data)

        return {
            "status":          "complete",
            "seasons_updated": results["success"],
            "seasons_skipped": results["skipped"],
            "seasons_failed":  results["failed"],
            "total_seasons":   len(sorted_data),
            "file_written":    path,
            "next_step":       "GET /basketball/league/data/results/download to save locally",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/results/status")
def nba_results_status():
    """Shows which years are in results.json."""
    try:
        path = _get_data_path("results.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season = data[yr]
            teams  = season.get("teams", {})
            summary.append({
                "year":        int(yr),
                "is_finished": season.get("is_finished"),
                "num_teams":   len(teams),
            })
        return {"total_seasons": len(data), "seasons": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/results/download")
def download_nba_results():
    """Returns current results.json for local save."""
    try:
        data = _load_json(_get_data_path("results.json"))
        if not data:
            raise HTTPException(status_code=404, detail="results.json not found.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Data generation — transactions.json
# ===========================================================================

@router.get("/data/transactions/build-all")
def build_nba_transactions(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None),
    force_clean: bool  = Query(default=False),
):
    """
    Generates data/basketball/transactions.json — trades and waiver/FA moves per season.
    Keyed by year: {"2024": {"trades": [...], "moves": [...]}}

    Usage:
        GET /basketball/league/data/transactions/build-all
        GET /basketball/league/data/transactions/build-all?year=2024
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        import datetime

        path        = _get_data_path("transactions.json")
        existing    = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}
        season_keys = _get_all_nba_season_keys()

        if not season_keys:
            raise HTTPException(status_code=400, detail="No season keys cached. Run discover-seasons first.")

        all_years    = sorted(season_keys.keys())
        target_years = [year] if year else all_years
        results      = {"success": [], "skipped": [], "failed": {}}

        def _ts_to_date(ts):
            try:
                return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                return None

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = season_keys.get(str(yr)) or _league_key_for_season(yr)
                query      = get_query(league_key)
                week_map   = _build_week_map(query, league_key)

                tx_dict = _convert_to_dict(query.get_league_transactions())
                tx_list = tx_dict if isinstance(tx_dict, list) else tx_dict.get("transactions", [])

                trades = []
                moves  = []

                for item in tx_list:
                    tx     = item if isinstance(item, dict) else {}
                    ttype  = tx.get("type", "")
                    status = tx.get("status", "")
                    if status != "successful":
                        continue

                    ts       = tx.get("timestamp")
                    date_str = _ts_to_date(ts)
                    faab     = tx.get("faab_bid")
                    try:
                        faab_int = int(faab) if faab is not None else None
                    except (TypeError, ValueError):
                        faab_int = None

                    # Normalize players_raw
                    players_raw = tx.get("players", [])
                    if isinstance(players_raw, dict):
                        if all(str(k).isdigit() for k in players_raw.keys()):
                            players_raw = [players_raw[k]
                                           for k in sorted(players_raw, key=lambda x: int(x))]
                        else:
                            players_raw = list(players_raw.values())

                    ttype_norm = ttype.lower().replace(" ", "_")
                    is_trade   = ttype_norm == "trade"
                    is_move    = ttype_norm in ("add", "drop", "add/drop", "waiver", "free_agent")

                    if is_trade:
                        trader_tk = str(tx.get("trader_team_key") or "")
                        tradee_tk = str(tx.get("tradee_team_key") or "")
                        a_received, b_received = [], []

                        for pw in players_raw:
                            pi      = _extract_player_from_yfpy(pw)
                            dest_tk = str(pi["td"].get("destination_team_key") or "")
                            entry   = {"name": pi["name"], "position": pi["position"], "player_key": pi["player_key"]}
                            if dest_tk == trader_tk:
                                a_received.append(entry)
                            else:
                                b_received.append(entry)

                        trades.append({
                            "week":       _date_to_week(date_str, week_map),
                            "date":       date_str,
                            "team_a_key": trader_tk,
                            "team_b_key": tradee_tk,
                            "a_received": a_received,
                            "b_received": b_received,
                        })

                    elif is_move:
                        added, dropped = [], []
                        for pw in players_raw:
                            pi        = _extract_player_from_yfpy(pw)
                            move_type = (pi["td"].get("type") or "").lower()
                            entry     = {"name": pi["name"], "position": pi["position"], "player_key": pi["player_key"]}
                            if move_type == "add":
                                added.append({**entry, "source_type": pi["td"].get("source_type", "")})
                            elif move_type == "drop":
                                dropped.append(entry)

                        team_key = None
                        for pw in players_raw:
                            pi = _extract_player_from_yfpy(pw)
                            mt = (pi["td"].get("type") or "").lower()
                            if mt == "add":
                                team_key = str(pi["td"].get("destination_team_key") or "")
                                break
                            elif mt == "drop":
                                team_key = str(pi["td"].get("source_team_key") or "")
                                break

                        if added or dropped:
                            moves.append({
                                "week":     _date_to_week(date_str, week_map),
                                "date":     date_str,
                                "team_key": team_key,
                                "added":    added,
                                "dropped":  dropped,
                                "faab_bid": faab_int,
                            })

                existing[yr] = {
                    "trades": sorted(trades, key=lambda x: (x.get("week") or 99, x.get("date") or "")),
                    "moves":  sorted(moves,  key=lambda x: (x.get("week") or 99, x.get("date") or "")),
                }
                results["success"].append(int(yr))
            except Exception as e:
                results["failed"][yr] = str(e)

        sorted_data = _year_sort(existing)
        _write_json(path, sorted_data)

        return {
            "status":          "complete",
            "seasons_updated": results["success"],
            "seasons_skipped": results["skipped"],
            "seasons_failed":  results["failed"],
            "total_seasons":   len(sorted_data),
            "file_written":    path,
            "next_step":       "GET /basketball/league/data/transactions/download to save locally",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/transactions/status")
def nba_transactions_status():
    """Shows which years are in transactions.json."""
    try:
        path = _get_data_path("transactions.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = [
            {"year": int(yr), "trades": len(s.get("trades", [])), "moves": len(s.get("moves", []))}
            for yr, s in sorted(data.items(), reverse=True)
        ]
        return {"total_seasons": len(data), "seasons": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/transactions/download")
def download_nba_transactions():
    """Returns current transactions.json for local save."""
    try:
        data = _load_json(_get_data_path("transactions.json"))
        if not data:
            raise HTTPException(status_code=404, detail="transactions.json not found.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/transactions/debug")
def debug_nba_transactions(year: str = Query(default="2024")):
    """Raw YFPY transaction response for a season. Use to diagnose parsing issues."""
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        league_key = _league_key_for_season(year)
        query      = get_query(league_key)
        raw        = query.get_league_transactions()
        converted  = _convert_to_dict(raw)
        tx_list    = converted if isinstance(converted, list) else converted.get("transactions", [])
        return {
            "year":         year,
            "total_count":  len(tx_list) if hasattr(tx_list, "__len__") else "N/A",
            "sample_items": tx_list[:2] if tx_list else [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Data generation — drafts.json
# ===========================================================================

@router.get("/data/drafts/build-all")
def build_nba_drafts(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None),
    force_clean: bool  = Query(default=False),
):
    """
    Generates data/basketball/drafts.json — full draft board per season.
    Keyed by year: {"2024": {"draft_type": "snake", "picks": [...]}}

    Usage:
        GET /basketball/league/data/drafts/build-all
        GET /basketball/league/data/drafts/build-all?year=2024
        GET /basketball/league/data/drafts/build-all?force_clean=true
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        path        = _get_data_path("drafts.json")
        existing    = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}
        season_keys = _get_all_nba_season_keys()

        if not season_keys:
            raise HTTPException(status_code=400, detail="No season keys cached. Run discover-seasons first.")

        all_years    = sorted(season_keys.keys())
        target_years = [year] if year else all_years
        results      = {"success": [], "skipped": [], "failed": {}}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = season_keys.get(str(yr)) or _league_key_for_season(yr)
                query      = get_query(league_key)

                try:
                    settings_dict = _convert_to_dict(query.get_league_settings())
                    is_auction    = bool(int(settings_dict.get("is_auction_draft") or 0))
                    draft_type    = "auction" if is_auction else "snake"
                    num_teams     = int(settings_dict.get("num_teams") or 10)
                except Exception:
                    draft_type, num_teams = "unknown", 10

                draft_raw = query.get_league_draft_results()
                picks_raw = _unwrap_picks_raw(draft_raw, _convert_to_dict)

                picks = []
                for item in picks_raw:
                    p = item["draft_result"] if isinstance(item, dict) and "draft_result" in item \
                        else (item if isinstance(item, dict) else {})

                    team_key   = str(p.get("team_key")   or "")
                    player_key = str(p.get("player_key") or "")
                    pick_num   = p.get("pick")
                    round_num  = p.get("round")
                    cost       = p.get("cost")

                    if not team_key and not player_key:
                        continue

                    try:
                        pick_int = int(pick_num) if pick_num is not None else None
                    except (TypeError, ValueError):
                        pick_int = None

                    try:
                        round_int = int(round_num) if round_num is not None else None
                        if round_int is None and pick_int is not None:
                            round_int = ((pick_int - 1) // num_teams) + 1
                    except (TypeError, ValueError):
                        round_int = None

                    try:
                        cost_int = int(cost) if cost is not None else None
                    except (TypeError, ValueError):
                        cost_int = None

                    picks.append({
                        "overall_pick": pick_int,
                        "round":        round_int,
                        "team_key":     team_key or None,
                        "player_key":   player_key or None,
                        "player_name":  None,  # enrich via player_info.json
                        "position":     None,  # enrich via player_info.json
                        "cost":         cost_int,
                    })

                picks.sort(key=lambda x: x.get("overall_pick") or 9999)

                existing[yr] = {
                    "year":        int(yr),
                    "draft_type":  draft_type,
                    "total_picks": len(picks),
                    "picks":       picks,
                }
                results["success"].append(int(yr))
            except Exception as e:
                results["failed"][yr] = str(e)

        sorted_data = _year_sort(existing)
        _write_json(path, sorted_data)

        return {
            "status":          "complete",
            "seasons_updated": results["success"],
            "seasons_skipped": results["skipped"],
            "seasons_failed":  results["failed"],
            "total_seasons":   len(sorted_data),
            "file_written":    path,
            "next_step":       "GET /basketball/league/data/drafts/download to save locally",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/drafts/debug")
def debug_nba_drafts(year: str = Query(default="2024")):
    """Raw YFPY draft response before parsing. Use to diagnose pick extraction issues."""
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        league_key = _league_key_for_season(year)
        query      = get_query(league_key)
        raw        = query.get_league_draft_results()
        picks_raw  = _unwrap_picks_raw(raw, _convert_to_dict)
        return {
            "year":          year,
            "league_key":    league_key,
            "raw_type":      str(type(raw)),
            "unwrapped_len": len(picks_raw),
            "first_pick":    picks_raw[0] if picks_raw else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/drafts/status")
def nba_drafts_status():
    """Shows which years are in drafts.json."""
    try:
        path = _get_data_path("drafts.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season = data[yr]
            picks  = season.get("picks", [])
            with_names = sum(1 for p in picks if p.get("player_name"))
            summary.append({
                "year":             int(yr),
                "draft_type":       season.get("draft_type"),
                "total_picks":      len(picks),
                "picks_with_names": with_names,
            })
        return {"total_seasons": len(data), "seasons": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/drafts/download")
def download_nba_drafts():
    """Returns current drafts.json for local save."""
    try:
        data = _load_json(_get_data_path("drafts.json"))
        if not data:
            raise HTTPException(status_code=404, detail="drafts.json not found.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))