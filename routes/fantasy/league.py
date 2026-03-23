"""
routes/fantasy/league.py
========================
All data-generation and exploration endpoints for the BlackGold NFL fantasy league.

URL prefix: /league  (mounted in main.py as-is — kept for backward compatibility)

Data pipeline pattern per file
-------------------------------
  GET /league/data/<file>/build-all?skip_existing=true   ← weekly refresh
  GET /league/data/<file>/build-all?force_clean=true     ← full rebuild
  GET /league/data/<file>/status                         ← enrichment state
  GET /league/data/<file>/download                       ← save to local git

Files: managers, results, transactions, drafts, punishment
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from routes.auth import require_permission
from services.fantasy.league_service import (
    get_league_settings,
    get_all_seasons,
    get_league_key_for_season,
    get_current_season,
    get_league_standings,
)

router = APIRouter(prefix="/league", tags=["League"])


# ===========================================================================
# Seasons / Settings
# ===========================================================================

@router.get("/seasons")
def get_seasons():
    """
    Get all available seasons for BlackGold (2007-present).
    Follows the renew chain; auto-discovers new seasons without code changes.
    """
    try:
        return get_all_seasons()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seasons/refresh")
def refresh_seasons():
    """Force-refresh the season cache. Call at the start of a new season."""
    try:
        return get_all_seasons(force_refresh=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/season/{year}/settings")
def season_settings(year: str):
    """
    League settings for a given season year, or "current".
    Example: /league/season/2024/settings
    """
    try:
        if year == "current":
            year = str(get_current_season())
        league_key = get_league_key_for_season(year)
        return get_league_settings(league_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{league_key}/settings")
def league_settings_legacy(league_key: str):
    """Legacy endpoint — prefer /league/season/{year}/settings."""
    try:
        return get_league_settings(league_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{league_key}/raw")
def league_raw_data(league_key: str):
    """Raw league metadata for debugging."""
    try:
        from services.yahoo_service import get_query
        import json

        query   = get_query(league_key)
        raw     = query.get_league_metadata()
        raw_dict = raw.to_json() if hasattr(raw, "to_json") else \
                   raw.__dict__  if hasattr(raw, "__dict__") else raw
        if isinstance(raw_dict, str):
            raw_dict = json.loads(raw_dict)
        return {"message": "All available fields from Yahoo API", "data": raw_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/season/{year}/standings")
def season_standings(year: str):
    """League standings for a season year or "current"."""
    try:
        if year == "current":
            year = str(get_current_season())
        league_key = get_league_key_for_season(year)
        return get_league_standings(league_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/season/{year}/standings/raw")
def season_standings_raw(year: str):
    """Debug — raw standings object from Yahoo API."""
    try:
        from services.yahoo_service import get_query

        if year == "current":
            year = str(get_current_season())
        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)
        standings  = query.get_league_standings()
        result = {
            "type":     type(standings).__name__,
            "is_list":  isinstance(standings, list),
            "length":   len(standings) if isinstance(standings, (list, tuple)) else "N/A",
        }
        if isinstance(standings, list) and standings:
            first = standings[0]
            result["first_item_json"] = first.to_json() if hasattr(first, "to_json") else \
                                        first.__dict__  if hasattr(first, "__dict__") else str(first)[:500]
        else:
            result["full_json"] = standings.to_json() if hasattr(standings, "to_json") else \
                                  standings.__dict__  if hasattr(standings, "__dict__") else str(standings)[:1000]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/season/{year}/settings/raw")
def season_settings_raw(year: str):
    """Debug — raw settings including scoring rules."""
    try:
        from services.yahoo_service import get_query
        import json

        if year == "current":
            year = str(get_current_season())
        league_key   = get_league_key_for_season(year)
        query        = get_query(league_key)
        settings     = query.get_league_settings()
        settings_dict = settings.to_json() if hasattr(settings, "to_json") else \
                        settings.__dict__  if hasattr(settings, "__dict__") else settings
        if isinstance(settings_dict, str):
            settings_dict = json.loads(settings_dict)
        return {"type": type(settings).__name__, "data": settings_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules")
def get_rules():
    """All league rules for the current season (scoring, roster, settings, payments)."""
    try:
        from services.fantasy.league_service import get_league_rules
        return get_league_rules()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Explore / Debug
# ===========================================================================

@router.get("/explore/season/{year}")
def explore_season_data(year: str):
    """Shows ALL available data for a season from Yahoo API."""
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        league_key = get_league_key_for_season(year)
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

        return {"year": year, "league_key": league_key, "available_data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/what-yahoo-has")
def explore_what_yahoo_has():
    """Documents what data Yahoo API provides across different seasons."""
    return {
        "yahoo_api_capabilities": {
            "league_level": {
                "metadata":     "League info, season, teams count, etc.",
                "settings":     "Scoring, roster, draft, playoff settings",
                "standings":    "Final rankings, records, points",
                "teams":        "Team names, managers, logos",
                "draft_results":"Who drafted who (may be limited to recent seasons)",
                "transactions": "Trades, adds, drops (may be limited)",
                "scoreboard":   "Weekly matchups with scores",
            },
            "team_level": {
                "roster":   "Players on team by week",
                "stats":    "Team stats by week",
                "matchups": "All matchups for a team",
            },
            "player_level": {
                "stats":     "Individual player stats",
                "ownership": "Which team owns a player",
            },
            "limitations": {
                "historical_rosters":       "May only be available for recent seasons",
                "trades_historical":        "Transaction data may be limited",
                "draft_historical":         "Draft results may not be available pre-2010",
            },
        }
    }


@router.get("/explore/availability-matrix")
def check_data_availability():
    """Tests what data is available across sample seasons."""
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import get_all_seasons, _convert_to_dict

        seasons_data = get_all_seasons()
        test_years   = [2025, 2020, 2015, 2010, 2007]
        results      = []

        for season in seasons_data.get("seasons", []):
            year = season.get("year")
            if year not in test_years:
                continue
            league_key = season.get("league_key")
            query      = get_query(league_key)
            availability = {"year": year, "league_key": league_key, "data_available": {}}
            for dtype, fetcher in [
                ("standings",        lambda: query.get_league_standings()),
                ("settings",         lambda: query.get_league_settings()),
                ("teams",            lambda: query.get_league_teams()),
                ("draft_results",    lambda: query.get_league_draft_results()),
                ("transactions",     lambda: query.get_league_transactions()),
                ("scoreboard_week_1",lambda: query.get_league_scoreboard_by_week(1)),
            ]:
                try:
                    fetcher()
                    availability["data_available"][dtype] = "✅ Available"
                except Exception as e:
                    availability["data_available"][dtype] = f"❌ {str(e)[:50]}"
            results.append(availability)

        return {"tested_years": test_years, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/historical-depth")
def test_historical_depth():
    """Tests how far back detailed data goes across key seasons."""
    from services.yahoo_service import get_query
    from services.fantasy.league_service import _convert_to_dict

    test_years = [2007, 2010, 2015, 2020, 2025]
    results    = {}

    for year in test_years:
        try:
            league_key = get_league_key_for_season(str(year))
            query      = get_query(league_key)
            year_data  = {"year": year}

            try:
                teams      = _convert_to_dict(query.get_league_teams())
                first_key  = teams["teams"][0]["team"]["team_key"]
                query.get_team_roster_by_week(first_key, 1)
                year_data["roster_week_1"] = "✅ Available"
            except Exception as e:
                year_data["roster_week_1"] = f"❌ {str(e)[:50]}"

            for label, fetcher in [
                ("scoreboard", lambda: query.get_league_scoreboard_by_week(1)),
                ("transactions", lambda: query.get_league_transactions()),
                ("draft",        lambda: query.get_league_draft_results()),
            ]:
                try:
                    fetcher()
                    year_data[label] = "✅ Available"
                except Exception as e:
                    year_data[label] = f"❌ {str(e)[:50]}"

            results[str(year)] = year_data
        except Exception as e:
            results[str(year)] = {"error": str(e)}

    return {"test_years": test_years, "results": results}


@router.get("/explore/nba-discovery")
def discover_nba_league(league_id: str = Query(..., description="NBA league ID e.g. '38685'")):
    """
    Discovers the correct league key for a Yahoo NBA Fantasy league.
    Tries known NBA game_ids to find the matching league.
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        nba_game_ids = {
            2024: 428, 2023: 418, 2022: 406, 2021: 396, 2020: 385,
            2019: 375, 2018: 363, 2017: 352, 2016: 341, 2015: 331,
        }
        found  = []
        errors = []

        for season_year, game_id in sorted(nba_game_ids.items(), reverse=True):
            league_key = f"{game_id}.l.{league_id}"
            try:
                query = get_query(league_key)
                meta  = _convert_to_dict(query.get_league_metadata())
                found.append({
                    "season_year": season_year,
                    "game_id":     game_id,
                    "league_key":  league_key,
                    "league_name": meta.get("name"),
                    "season":      meta.get("season"),
                    "num_teams":   meta.get("num_teams"),
                    "game_code":   meta.get("game_code"),
                    "renew":       meta.get("renew"),
                    "renewed":     meta.get("renewed"),
                    "start_date":  meta.get("start_date"),
                    "end_date":    meta.get("end_date"),
                    "is_finished": meta.get("is_finished"),
                })
            except Exception as e:
                errors.append({"season_year": season_year, "league_key": league_key, "error": str(e)[:80]})

        return {
            "league_id":       league_id,
            "found_seasons":   found,
            "failed_attempts": errors,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/nba-season/{league_key}")
def explore_nba_season(league_key: str):
    """Full data exploration for an NBA league key."""
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


@router.get("/explore/my-leagues")
def get_my_leagues():
    """Returns all Yahoo Fantasy leagues for the authenticated account."""
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        from config import get_known_league_key

        query   = get_query(get_known_league_key())
        results = {}

        try:
            results["user_games"] = _convert_to_dict(query.get_user_games())
        except Exception as e:
            results["user_games"] = {"error": str(e)}

        nba_attempts = {}
        for game_id in range(420, 460):
            try:
                raw  = query.get_user_leagues_by_game_key(str(game_id))
                data = _convert_to_dict(raw)
                if data and "error" not in str(data).lower():
                    nba_attempts[str(game_id)] = data
                    break
            except Exception:
                continue
        results["nba_league_search"] = nba_attempts or "No NBA leagues found in range 420-459"

        try:
            results["nba_by_code"] = _convert_to_dict(query.get_user_leagues_by_game_key("nba"))
        except Exception as e:
            results["nba_by_code"] = {"error": str(e)}

        return {"message": "Yahoo account league data", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/yfpy-methods")
def get_yfpy_methods():
    """Returns all available YFPY query methods."""
    try:
        from services.yahoo_service import get_query
        from config import get_known_league_key

        query   = get_query(get_known_league_key())
        methods = [m for m in dir(query) if not m.startswith("_")]
        return {
            "user_related":  [m for m in methods if "user"   in m.lower()],
            "league_related":[m for m in methods if "league" in m.lower()],
            "game_related":  [m for m in methods if "game"   in m.lower()],
            "all_methods":   methods,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
def league_history():
    """Season-by-season notable data for all BlackGold seasons (2007–present)."""
    try:
        from services.fantasy.league_service import get_league_history
        return get_league_history()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/seed-players")
def seed_top_players(year: str):
    """Admin — fetch top scorer per position for a season and return config block."""
    try:
        from services.fantasy.league_service import (
            get_league_key_for_season, _fetch_top_players, _fetch_first_pick,
        )
        import json

        league_key  = get_league_key_for_season(year)
        top_players = _fetch_top_players(league_key)
        first_pick  = _fetch_first_pick(league_key)
        config_block = {int(year): {"punishment": None, "first_pick": first_pick, "top_players": top_players}}

        return {
            "year":                year,
            "league_key":          league_key,
            "top_players":         top_players,
            "first_overall_pick":  first_pick,
            "paste_into_config":   f"    {year}: " + json.dumps(config_block[int(year)], indent=8),
            "instructions":        "Copy into SEASON_HISTORY_MANUAL in config.py, then set punishment.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/seed")
def seed_all_managers(year: str = Query(..., description="Season year e.g. '2024'")):
    """Admin — seed PLAYER_HISTORY_MANUAL config block for a season."""
    try:
        from services.fantasy.team_service import build_season_seed
        import json

        seed_data = build_season_seed(int(year))
        lines     = []
        for manager_id, seasons in seed_data.items():
            for yr, data in seasons.items():
                lines.append(f"    # {manager_id} {yr}")
                lines.append(f"    {json.dumps({yr: data}, indent=8)}")

        return {
            "year":             year,
            "managers_seeded":  list(seed_data.keys()),
            "data":             seed_data,
            "instructions":     "Merge each manager's data into PLAYER_HISTORY_MANUAL in config.py.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Shared helpers (data/, JSON I/O)
# ===========================================================================

def _get_data_path(filename: str) -> str:
    import os
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "fantasy", filename,
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
    """Return dict sorted by year key descending."""
    return dict(sorted(d.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else -1, reverse=True))


# ---------------------------------------------------------------------------
# YFPY shape helpers  (fixes for transactions + drafts)
# ---------------------------------------------------------------------------

def _extract_player_from_yfpy(pw: dict) -> dict:
    """
    Extract player info from a YFPY player entry.

    Handles both wrapped {"player": {...}} and flat {name, transaction_data, ...}
    shapes.  Key fixes vs old inline _extract_player:
      - name is always {"full": "..."} in YFPY — never a plain string at top level
      - transaction_data is always a LIST — take [0]
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

    Fixes the bug where _convert_to_dict collapses a list into
    {"0": pick, "1": pick, ...} and the old fallback grabbed only [0].
    """
    if isinstance(draft_raw, list):
        return draft_raw

    converted = convert_fn(draft_raw)

    if isinstance(converted, list):
        return converted

    if not isinstance(converted, dict):
        return []

    # Explicit named keys
    for key in ("draft_results", "picks", "draft_result"):
        val = converted.get(key)
        if isinstance(val, list) and val:
            return val

    # Numbered-key dict {"0": ..., "1": ...} — sort and unpack
    keys = list(converted.keys())
    if keys and all(str(k).isdigit() for k in keys):
        return [converted[k] for k in sorted(keys, key=lambda x: int(x))]

    # Last resort — any values that look like picks
    return [v for v in converted.values()
            if isinstance(v, dict) and ("player_key" in v or "team_key" in v)]


# ===========================================================================
# Data generation — managers.json
# ===========================================================================

@router.get("/data/managers")
def generate_managers_data(
    year: str = Query(..., description="Season year e.g. '2025', or 'all'"),
):
    """
    Generates the managers.json block for a given season (or all seasons).

    Usage:
        GET /league/data/managers?year=2025
        GET /league/data/managers?year=all
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict, _safe_get,
        )
        from services.fantasy.team_service import _extract_teams_list
        from services.yahoo_service import get_query
        from config import get_manager_identity
        import json, os

        seasons_data = get_all_seasons(force_refresh=True)
        all_seasons  = seasons_data.get("seasons", [])
        target_years = [str(s["year"]) for s in all_seasons] if year == "all" else [year]
        result       = {}

        for yr in target_years:
            try:
                league_key     = get_league_key_for_season(yr)
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
                    identity     = get_manager_identity(team_key=team_key, manager_guid=guid)
                    display_name = identity["display_name"] if identity else nickname or "Unknown"
                    manager_id   = identity["manager_id"]   if identity else None

                    logos    = t.get("team_logos", {})
                    if isinstance(logos, list): logos = logos[0] if logos else {}
                    logo_obj = logos.get("team_logo", {}) if isinstance(logos, dict) else {}
                    if isinstance(logo_obj, list): logo_obj = logo_obj[0] if logo_obj else {}
                    team_logo = logo_obj.get("url") if isinstance(logo_obj, dict) else None

                    managers.append({
                        "manager_id":   manager_id,
                        "display_name": display_name,
                        "team_key":     team_key,
                        "team_id":      team_id,
                        "team_name":    t.get("name"),
                        "guid":         guid,
                        "nickname":     nickname,
                        "is_comanager": is_comanager,
                        "logo_url":     team_logo,
                        "team_url":     t.get("url"),
                    })

                managers.sort(key=lambda m: int(m["team_id"]) if m["team_id"].isdigit() else 0)

                result[yr] = {
                    "year":        int(yr),
                    "league_key":  league_key,
                    "league_id":   _safe_get(meta, "league_id") or league_key.split(".l.")[-1],
                    "league_name": _safe_get(meta, "name") or "BlackGold",
                    "url":         _safe_get(meta, "url"),
                    "logo_url":    _safe_get(meta, "logo_url"),
                    "num_teams":   _safe_get(meta, "num_teams"),
                    "season":      _safe_get(meta, "season"),
                    "is_finished": bool(int(_safe_get(meta, "is_finished") or 0)),
                    "managers":    managers,
                }
            except Exception as e:
                result[yr] = {"year": int(yr), "error": str(e)}

        # Auto-merge into managers.json
        data_path = _get_data_path("managers.json")
        existing  = {}
        if os.path.exists(data_path):
            with open(data_path) as f:
                existing = {k: v for k, v in json.load(f).items() if str(k).isdigit()}

        merged = {**existing, **{k: v for k, v in result.items() if "error" not in v}}
        errors = {k: v for k, v in result.items() if "error" in v}
        sorted_merged = _year_sort(merged)
        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        with open(data_path, "w") as f:
            json.dump(sorted_merged, f, indent=2)

        return {
            "status":        "success",
            "years_updated": [k for k in result if "error" not in result[k]],
            "years_failed":  errors,
            "total_seasons": len(sorted_merged),
            "file_written":  data_path,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/managers/build-all")
def build_all_managers(
    skip_existing: bool = Query(default=True),
    force_clean:   bool = Query(default=False),
):
    """
    Enriches managers.json for ALL seasons.
    Use skip_existing=true (default) to safely re-run without overwriting good data.
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict, _safe_get,
        )
        from services.fantasy.team_service import _extract_teams_list
        from services.yahoo_service import get_query
        from config import get_manager_identity
        import json, os

        data_path = _get_data_path("managers.json")
        existing  = {}
        if not force_clean and os.path.exists(data_path):
            raw      = json.load(open(data_path))
            existing = {k: v for k, v in raw.items() if str(k).isdigit()}

        seasons_data = get_all_seasons()
        all_years    = [str(s["year"]) for s in seasons_data.get("seasons", [])]
        results      = {"success": [], "skipped": [], "failed": {}}

        for yr in sorted(all_years):
            if skip_existing and yr in existing and existing[yr].get("url") is not None:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key     = get_league_key_for_season(yr)
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
                    identity     = get_manager_identity(team_key=team_key, manager_guid=guid)
                    display_name = identity["display_name"] if identity else nickname or "Unknown"
                    manager_id   = identity["manager_id"]   if identity else None

                    logos    = t.get("team_logos", {})
                    if isinstance(logos, list): logos = logos[0] if logos else {}
                    logo_obj = logos.get("team_logo", {}) if isinstance(logos, dict) else {}
                    if isinstance(logo_obj, list): logo_obj = logo_obj[0] if logo_obj else {}
                    team_logo = logo_obj.get("url") if isinstance(logo_obj, dict) else None

                    managers.append({
                        "manager_id":   manager_id,
                        "display_name": display_name,
                        "team_key":     team_key,
                        "team_id":      team_id,
                        "team_name":    t.get("name"),
                        "guid":         guid,
                        "nickname":     nickname,
                        "is_comanager": is_comanager,
                        "logo_url":     team_logo,
                        "team_url":     t.get("url"),
                    })

                managers.sort(key=lambda m: int(m["team_id"]) if m["team_id"].isdigit() else 0)

                existing[yr] = {
                    "year":        int(yr),
                    "league_key":  league_key,
                    "league_id":   _safe_get(meta, "league_id") or league_key.split(".l.")[-1],
                    "league_name": _safe_get(meta, "name") or "BlackGold",
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
        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        with open(data_path, "w") as f:
            json.dump(sorted_data, f, indent=2)

        return {
            "status":          "complete",
            "seasons_updated": results["success"],
            "seasons_skipped": results["skipped"],
            "seasons_failed":  results["failed"],
            "total_seasons":   len(sorted_data),
            "file_written":    data_path,
            "next_step":       "GET /league/data/managers/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/managers/status")
def managers_json_status():
    """Shows which years are in managers.json and enrichment state."""
    try:
        path = _get_data_path("managers.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}

        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season   = data[yr]
            managers = season.get("managers", [])
            summary.append({
                "year":              int(yr),
                "num_managers":      len(managers),
                "enriched_managers": sum(1 for m in managers if m.get("team_name") is not None),
                "league_enriched":   season.get("url") is not None,
                "needs_api_call":    season.get("url") is None,
                "league_url":        season.get("url"),
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
def download_managers_json():
    """Returns current managers.json for local save."""
    try:
        data = _load_json(_get_data_path("managers.json"))
        if not data:
            raise HTTPException(status_code=404, detail="managers.json not found. Run /league/data/managers?year=2025 first.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Data generation — results.json
# ===========================================================================

def _build_results_for_season(yr: str, query, league_key: str) -> dict:
    """
    Fetch standings + scoreboard for one season.
    Returns dict keyed by manager_id.
    """
    from services.fantasy.league_service import _convert_to_dict
    from services.fantasy.team_service import (
        _extract_teams_list, _extract_team_standings,
        _extract_outcome_totals, _extract_logo_url,
    )
    from config import get_manager_identity

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

    season_data  = {}
    team_key_map = {}

    for t in teams_list:
        if not isinstance(t, dict):
            continue
        team_key = t.get("team_key", "")
        ts  = _extract_team_standings(t)
        ot  = _extract_outcome_totals(ts)
        identity   = get_manager_identity(team_key=team_key)
        manager_id = identity["manager_id"] if identity else None
        if not manager_id:
            continue

        team_key_map[manager_id] = team_key
        wins   = int(ot.get("wins")   or 0)
        losses = int(ot.get("losses") or 0)
        ties   = int(ot.get("ties")   or 0)
        games  = wins + losses + ties
        pf     = float(ts.get("points_for")    or 0)
        pa     = float(ts.get("points_against") or 0)

        season_data[manager_id] = {
            "team_name": t.get("name"),
            "logo_url":  _extract_logo_url(t),
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

    # Scoreboard loop — projected + playoff splits
    try:
        settings_dict = _convert_to_dict(query.get_league_settings())
        playoff_start = int(settings_dict.get("playoff_start_week") or 15)
        end_week      = int(settings_dict.get("end_week") or 17)
    except Exception:
        playoff_start, end_week = 15, 17

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
                    identity = get_manager_identity(team_key=tk)
                    if not identity:
                        continue
                    mid = identity["manager_id"]
                    if mid not in season_data:
                        continue

                    opp_tk   = next((k for k in tkeys if k != tk), None)
                    my_pts   = team_pts.get(tk, 0)
                    opp_pts  = team_pts.get(opp_tk, 0)
                    my_proj  = team_proj.get(tk, 0)
                    opp_proj = team_proj.get(opp_tk, 0)

                    seed_val = season_data[mid]["_rs"].get("seed")
                    try:
                        is_true_playoff = is_playoff_week and int(seed_val or 99) <= 4
                    except (TypeError, ValueError):
                        is_true_playoff = False

                    if is_true_playoff:
                        b = season_data[mid]["_pl"]
                        b["pf"]      = round(b["pf"]      + my_pts,  2)
                        b["pa"]      = round(b["pa"]      + opp_pts, 2)
                        b["proj_pf"] = round(b["proj_pf"] + my_proj, 2)
                        b["proj_pa"] = round(b["proj_pa"] + opp_proj,2)
                        b["games"] += 1
                        if is_tied:            b["ties"]   += 1
                        elif winner_key == tk: b["wins"]   += 1
                        else:                  b["losses"] += 1
                    elif not is_playoff_week:
                        b = season_data[mid]["_rs"]
                        b["proj_pf"] = round(b["proj_pf"] + my_proj, 2)
                        b["proj_pa"] = round(b["proj_pa"] + opp_proj,2)
        except Exception:
            continue

    # Cross-manager rank maps
    def _cross_rank(field, bucket):
        vals = sorted(
            [(mid, d[bucket][field]) for mid, d in season_data.items()],
            key=lambda x: x[1], reverse=True,
        )
        return {mid: i + 1 for i, (mid, _) in enumerate(vals)}

    rs_proj_pf_rank = _cross_rank("proj_pf", "_rs")
    rs_proj_pa_rank = _cross_rank("proj_pa", "_rs")
    pl_pf_rank      = _cross_rank("pf",      "_pl")
    pl_pa_rank      = _cross_rank("pa",      "_pl")
    pl_proj_pf_rank = _cross_rank("proj_pf", "_pl")
    pl_proj_pa_rank = _cross_rank("proj_pa", "_pl")

    for mid, d in season_data.items():
        rs = d["_rs"]
        pl = d["_pl"]
        g_rs, g_pl = rs["games"], pl["games"]

        try:
            r = int(rs["rank"]) if rs["rank"] is not None else None
            s = int(rs["seed"]) if rs["seed"] is not None else None
        except (TypeError, ValueError):
            r = s = None

        if r in (1, 2, 3, 4, 9, 10): finish = r
        elif s and 5 <= s <= 8:       finish = s
        else:                         finish = r

        d["regular_season"] = {
            "wins": rs["wins"], "losses": rs["losses"], "ties": rs["ties"], "games": g_rs,
            "win_pct": round(rs["wins"] / g_rs, 4) if g_rs else None,
            "rank": rs["rank"], "playoff_seed": rs["seed"],
            "points_for":                    round(rs["pf"], 2),
            "points_for_rank":               pf_rank_map.get(team_key_map.get(mid)),
            "avg_points_for":                round(rs["pf"] / g_rs, 2) if g_rs else None,
            "points_against":                round(rs["pa"], 2),
            "points_against_rank":           pa_rank_map.get(team_key_map.get(mid)),
            "avg_points_against":            round(rs["pa"] / g_rs, 2) if g_rs else None,
            "projected_points_for":          round(rs["proj_pf"], 2) if rs["proj_pf"] else None,
            "projected_points_for_rank":     rs_proj_pf_rank.get(mid),
            "avg_projected_points_for":      round(rs["proj_pf"] / g_rs, 2) if g_rs and rs["proj_pf"] else None,
            "projected_points_against":      round(rs["proj_pa"], 2) if rs["proj_pa"] else None,
            "projected_points_against_rank": rs_proj_pa_rank.get(mid),
            "avg_projected_points_against":  round(rs["proj_pa"] / g_rs, 2) if g_rs and rs["proj_pa"] else None,
        }

        try:
            seed_int = int(d["_rs"].get("seed") or 99)
        except (TypeError, ValueError):
            seed_int = 99
        is_playoff_team = seed_int <= 4

        if is_playoff_team and g_pl > 0:
            d["playoffs"] = {
                "made_playoffs": True, "finish": finish,
                "wins": pl["wins"], "losses": pl["losses"], "ties": pl["ties"], "games": g_pl,
                "win_pct": round(pl["wins"] / g_pl, 4) if g_pl else None,
                "points_for":                    round(pl["pf"], 2),
                "points_for_rank":               pl_pf_rank.get(mid),
                "avg_points_for":                round(pl["pf"] / g_pl, 2),
                "points_against":                round(pl["pa"], 2),
                "points_against_rank":           pl_pa_rank.get(mid),
                "avg_points_against":            round(pl["pa"] / g_pl, 2),
                "projected_points_for":          round(pl["proj_pf"], 2) if pl["proj_pf"] else None,
                "projected_points_for_rank":     pl_proj_pf_rank.get(mid),
                "avg_projected_points_for":      round(pl["proj_pf"] / g_pl, 2) if pl["proj_pf"] else None,
                "projected_points_against":      round(pl["proj_pa"], 2) if pl["proj_pa"] else None,
                "projected_points_against_rank": pl_proj_pa_rank.get(mid),
                "avg_projected_points_against":  round(pl["proj_pa"] / g_pl, 2) if pl["proj_pa"] else None,
            }
        else:
            d["playoffs"] = {"made_playoffs": False}

        del d["_rs"]
        del d["_pl"]

    return season_data


@router.get("/data/results/build-all")
def build_results(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None),
    force_clean: bool  = Query(default=False),
):
    """
    Generates results.json — regular season + playoff W-L-T, points, ranks.

    Usage:
        GET /league/data/results/build-all
        GET /league/data/results/build-all?year=2025
        GET /league/data/results/build-all?force_clean=true
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict, _safe_get,
        )
        from services.yahoo_service import get_query

        path     = _get_data_path("results.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])
        target_years = [year] if year else all_years
        results      = {"success": [], "skipped": [], "failed": {}}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key  = get_league_key_for_season(yr)
                query       = get_query(league_key)
                meta        = _convert_to_dict(query.get_league_metadata())
                is_finished = bool(int(_safe_get(meta, "is_finished") or 0))
                season_data = _build_results_for_season(yr, query, league_key)
                existing[yr] = {"is_finished": is_finished, "managers": season_data}
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
            "next_step":       "GET /league/data/results/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/results/status")
def results_status():
    """Shows which years are in results.json and enrichment state."""
    try:
        path = _get_data_path("results.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}

        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season   = data[yr]
            mgr_data = season.get("managers", season)
            managers = [k for k in mgr_data if k != "is_finished"]
            enriched = sum(
                1 for m in mgr_data.values()
                if isinstance(m, dict) and m.get("regular_season", {}).get("points_for")
            )
            summary.append({
                "year":          int(yr),
                "is_finished":   season.get("is_finished"),
                "num_managers":  len(managers),
                "enriched":      enriched,
                "needs_refresh": enriched < len(managers),
            })

        return {
            "total_seasons":   len(data),
            "fully_enriched":  sum(1 for s in summary if not s["needs_refresh"]),
            "needs_enrichment":[s["year"] for s in summary if s["needs_refresh"]],
            "seasons":         summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/results/download")
def download_results():
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

def _build_week_map(query, yr: str) -> list:
    """Build week→date-range map for a season using game weeks API."""
    from services.fantasy.league_service import _convert_to_dict
    try:
        league_key = query.league_key if hasattr(query, "league_key") else ""
        game_id    = str(league_key).split(".")[0] if league_key else None
        if not game_id:
            return []
        data  = _convert_to_dict(query.get_game_weeks_by_game_id(game_id))
        weeks = data if isinstance(data, list) else data.get("game_weeks", [])
        result = []
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
    """Map a YYYY-MM-DD date string to its season week number."""
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


@router.get("/data/transactions/build-all")
def build_transactions(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None, description="Single year e.g. '2025', or omit for all"),
    force_clean: bool  = Query(default=False),
):
    """
    Generates transactions.json — trades and waiver/FA moves per season.
    Keyed by year: {"2025": {"trades": [...], "moves": [...]}}

    Usage:
        GET /league/data/transactions/build-all
        GET /league/data/transactions/build-all?year=2025
        GET /league/data/transactions/build-all?force_clean=true
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict,
        )
        from services.yahoo_service import get_query
        from config import get_manager_identity
        import datetime

        path     = _get_data_path("transactions.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])
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
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)
                week_map   = _build_week_map(query, yr)

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

                    # ----------------------------------------------------------
                    # Normalize players_raw to a flat list.
                    # YFPY can return:
                    #   list → [{"player": {...}}, ...]  OR  [{flat player}, ...]
                    #   dict → {"0": {...}, "1": ...}    (numbered keys)
                    # ----------------------------------------------------------
                    players_raw = tx.get("players", [])
                    if isinstance(players_raw, dict):
                        if all(str(k).isdigit() for k in players_raw.keys()):
                            players_raw = [players_raw[k]
                                           for k in sorted(players_raw, key=lambda x: int(x))]
                        else:
                            players_raw = list(players_raw.values())

                    # Normalise ttype — YFPY uses several spellings
                    ttype_norm  = ttype.lower().replace(" ", "_")
                    is_trade    = ttype_norm == "trade"
                    is_move     = ttype_norm in (
                        "add", "drop", "add/drop", "waiver", "free_agent",
                    )

                    if is_trade:
                        trader_tk = str(tx.get("trader_team_key") or "")
                        tradee_tk = str(tx.get("tradee_team_key") or "")
                        ti_a = get_manager_identity(team_key=trader_tk)
                        ti_b = get_manager_identity(team_key=tradee_tk)
                        mgr_a = ti_a["manager_id"] if ti_a else trader_tk
                        mgr_b = ti_b["manager_id"] if ti_b else tradee_tk

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
                            "manager_a":  mgr_a,
                            "manager_b":  mgr_b,
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

                        # Resolve manager: prefer destination of first add
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

                        identity = get_manager_identity(team_key=team_key) if team_key else None
                        manager  = identity["manager_id"] if identity else team_key

                        if added or dropped:
                            moves.append({
                                "week":     _date_to_week(date_str, week_map),
                                "date":     date_str,
                                "manager":  manager,
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
            "next_step":       "GET /league/data/transactions/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/transactions/status")
def transactions_status():
    """Shows which years are in transactions.json."""
    try:
        path = _get_data_path("transactions.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season = data[yr]
            summary.append({
                "year":     int(yr),
                "trades":   len(season.get("trades", [])),
                "moves":    len(season.get("moves", [])),
                "has_data": bool(season.get("trades") or season.get("moves")),
            })
        return {"total_seasons": len(data), "seasons": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/transactions/download")
def download_transactions():
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
def debug_transactions_raw(year: str = Query(default="2025")):
    """Returns raw YFPY transaction response before parsing. Use to diagnose issues."""
    try:
        from services.fantasy.league_service import get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query

        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)
        raw        = query.get_league_transactions()
        converted  = _convert_to_dict(raw)

        tx_list = converted if isinstance(converted, list) else converted.get("transactions", [])
        sample  = tx_list[:2] if tx_list else []

        return {
            "raw_type":       str(type(raw)),
            "converted_type": str(type(converted)),
            "total_count":    len(tx_list) if hasattr(tx_list, "__len__") else "N/A",
            "sample_items":   sample,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Data generation — drafts.json
# ===========================================================================

@router.get("/data/drafts/build-all")
def build_drafts(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None, description="Single year e.g. '2025', or omit for all"),
    force_clean: bool  = Query(default=False),
):
    """
    Generates drafts.json — full draft board per season.

    Snake drafts: cost = null
    Auction drafts: cost = dollars spent (2023+)
    Keyed by year: {"2025": {"draft_type": "auction", "picks": [...]}}

    Usage:
        GET /league/data/drafts/build-all
        GET /league/data/drafts/build-all?year=2025
        GET /league/data/drafts/build-all?force_clean=true
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict, _safe_get,
        )
        from services.yahoo_service import get_query
        from config import get_manager_identity

        path     = _get_data_path("drafts.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])
        target_years = [year] if year else all_years
        results      = {"success": [], "skipped": [], "failed": {}}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                # Draft type
                try:
                    settings_dict = _convert_to_dict(query.get_league_settings())
                    is_auction    = bool(int(settings_dict.get("is_auction_draft") or 0))
                    draft_type    = "auction" if is_auction else "snake"
                    num_teams     = int(settings_dict.get("num_teams") or 10)
                except Exception:
                    draft_type, is_auction, num_teams = "unknown", False, 10

                # Get picks — _unwrap_picks_raw handles all YFPY return shapes
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

                    identity     = get_manager_identity(team_key=team_key)
                    manager_id   = identity["manager_id"]   if identity else None
                    display_name = identity["display_name"] if identity else team_key or "Unknown"

                    try:
                        pick_int = int(pick_num) if pick_num is not None else None
                    except (TypeError, ValueError):
                        pick_int = None

                    # Derive round from overall_pick when API omits the field
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
                        "manager_id":   manager_id,
                        "display_name": display_name,
                        "player_key":   player_key or None,
                        "player_name":  None,  # not in draft API — enrich via player_info.json
                        "position":     None,  # not in draft API — enrich via player_info.json
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
            "next_step":       "GET /league/data/drafts/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/drafts/debug")
def debug_draft_raw(year: str = Query(default="2025")):
    """Returns raw YFPY draft response before parsing. Use to diagnose pick extraction issues."""
    try:
        from services.fantasy.league_service import get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query

        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)
        raw        = query.get_league_draft_results()
        converted  = _convert_to_dict(raw)
        picks_raw  = _unwrap_picks_raw(raw, _convert_to_dict)

        return {
            "raw_type":          str(type(raw)),
            "converted_type":    str(type(converted)),
            "raw_is_list":       isinstance(raw, list),
            "raw_len":           len(raw) if hasattr(raw, "__len__") else None,
            "unwrapped_len":     len(picks_raw),
            "first_raw":         raw[0] if isinstance(raw, list) and raw else str(raw)[:300],
            "first_converted":   picks_raw[0] if picks_raw else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/drafts/status")
def drafts_status():
    """Shows which years are in drafts.json and pick enrichment state."""
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
                "needs_refresh":    with_names < len(picks) // 2 if picks else True,
            })

        return {
            "total_seasons":  len(data),
            "auction_seasons":[s["year"] for s in summary if s["draft_type"] == "auction"],
            "snake_seasons":  [s["year"] for s in summary if s["draft_type"] == "snake"],
            "seasons":        summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/drafts/download")
def download_drafts():
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


# ===========================================================================
# Data generation — punishment.json
# ===========================================================================

@router.get("/data/punishment/build")
def build_punishment():
    """
    Seeds punishment.json from SEASON_HISTORY_MANUAL in config.py.
    Loser is NOT stored here — derive at runtime from results.json (rank == 10).
    Run once to seed; update manually or via commissioner UI after that.
    """
    try:
        from config import get_all_manual_history

        path     = _get_data_path("punishment.json")
        existing = {k: v for k, v in _load_json(path).items() if str(k).isdigit()}
        manual   = get_all_manual_history()

        for yr, data in manual.items():
            yr_str     = str(yr)
            punishment = data.get("punishment")
            if yr_str not in existing:
                existing[yr_str] = {"year": yr, "punishment": punishment}
            elif punishment and not existing[yr_str].get("punishment"):
                existing[yr_str]["punishment"] = punishment

        sorted_data = _year_sort(existing)
        _write_json(path, sorted_data)

        return {
            "status":        "complete",
            "total_seasons": len(sorted_data),
            "populated":     sum(1 for v in sorted_data.values() if v.get("punishment")),
            "missing":       [k for k, v in sorted_data.items() if not v.get("punishment")],
            "file_written":  path,
            "next_step":     "GET /league/data/punishment/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/punishment/update")
def update_punishment(
    year:       int = Query(..., description="Season year e.g. 2026"),
    punishment: str = Query(..., description="Punishment text for the loser"),
    user: dict = Depends(require_permission("edit_settings")),
):
    """
    Commissioner/app owner — add or update punishment for a season.
    Requires commissioner or app_owner role.
    """
    try:
        import datetime

        path     = _get_data_path("punishment.json")
        existing = {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        existing[str(year)] = {
            "year":       year,
            "punishment": punishment,
            "updated_by": user.get("display_name"),
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }

        sorted_data = _year_sort(existing)
        _write_json(path, sorted_data)

        return {
            "status":     "updated",
            "year":       year,
            "punishment": punishment,
            "updated_by": user.get("display_name"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/punishment/status")
def punishment_status():
    """Shows which years have punishment entries."""
    try:
        path = _get_data_path("punishment.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = [
            {"year": int(yr), "has_punishment": bool(v.get("punishment")), "punishment": v.get("punishment")}
            for yr, v in sorted(data.items(), reverse=True)
        ]
        return {
            "total_seasons": len(data),
            "populated":     sum(1 for s in summary if s["has_punishment"]),
            "missing":       [s["year"] for s in summary if not s["has_punishment"]],
            "seasons":       summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/punishment/download")
def download_punishment():
    """Returns current punishment.json for local save."""
    try:
        data = _load_json(_get_data_path("punishment.json"))
        if not data:
            raise HTTPException(status_code=404, detail="punishment.json not found. Run /league/data/punishment/build first.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))