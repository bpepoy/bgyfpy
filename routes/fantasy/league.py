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
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
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

    CONFIRMED field locations from live API extract (all at top level on player object):
      full_name, player_key, player_id, display_position, editorial_team_abbr
      transaction_data: type, source_type, source_team_key, destination_team_key,
                        destination_team_name, destination_type (all at top level on td)

    Handles both:
      - {"player": {...}} wrapped shape (add/drop, trade)
      - flat {player_key, name, ...} shape
    """
    def _unwrap_yfpy(obj: dict) -> dict:
        if not isinstance(obj, dict): return {}
        base = dict(obj.get("_extracted_data", {})) if isinstance(obj.get("_extracted_data"), dict) else {}
        for k, v in obj.items():
            if k not in ("_extracted_data", "_index", "_keys"):
                base[k] = v
        return base

    # Unwrap outer wrapper then inner player
    pw_flat = _unwrap_yfpy(pw) if isinstance(pw, dict) else {}
    p_raw   = pw_flat.get("player", pw_flat)
    p       = _unwrap_yfpy(p_raw) if isinstance(p_raw, dict) else pw_flat

    # Name — full_name confirmed at top level; name dict as fallback
    name = p.get("full_name") or p.get("name", "")
    if isinstance(name, dict):
        name = _unwrap_yfpy(name).get("full") or ""

    # transaction_data — confirmed as dict at top level with all fields
    td_raw = p.get("transaction_data")
    if isinstance(td_raw, list):
        td = _unwrap_yfpy(td_raw[0]) if td_raw else {}
    elif isinstance(td_raw, dict):
        td = _unwrap_yfpy(td_raw)
    else:
        td = {}

    return {
        "name":       name or "Unknown",
        "position":   p.get("display_position") or p.get("primary_position"),
        "nfl_team":   p.get("editorial_team_abbr"),
        "player_key": p.get("player_key"),
        "player_id":  p.get("player_id"),
        "td":         td,
    }


def _unwrap_picks_raw(draft_raw, convert_fn) -> list:
    """
    Safely extract a flat list of pick dicts from a YFPY draft response.

    YFPY enriches each draft_result object with _extracted_data, _index, _keys
    alongside the real fields (pick, round, cost, team_key, player_key) at the
    top level.  We try every known shape in order and return the first non-empty result.

    Known shapes from live API:
      A) YFPY object → __dict__ has "draft_results" key → list of enriched pick dicts
      B) convert_fn(raw) → {"draft_results": [list]}   → named key extraction
      C) convert_fn(raw) → {"0": pick, "1": pick, ...} → numbered-key dict
      D) raw is already a list of pick dicts
      E) YFPY object is directly iterable, yielding pick objects
    """
    def _is_pick(d: dict) -> bool:
        """Check whether a dict looks like a draft pick (has the core fields)."""
        return isinstance(d, dict) and (
            "player_key" in d or "team_key" in d or
            ("_extracted_data" in d and isinstance(d["_extracted_data"], dict) and
             ("player_key" in d["_extracted_data"] or "team_key" in d["_extracted_data"]))
        )

    def _flatten_pick(d: dict) -> dict:
        """
        Normalize an enriched YFPY pick dict.
        Fields live at the top level AND in _extracted_data — top level takes precedence.
        """
        if not isinstance(d, dict):
            return {}
        # Merge _extracted_data first, then override with top-level fields
        base = dict(d.get("_extracted_data", {})) if isinstance(d.get("_extracted_data"), dict) else {}
        for k, v in d.items():
            if k not in ("_extracted_data", "_index", "_keys"):
                base[k] = v
        return base

    # Shape D — raw is already a flat list
    if isinstance(draft_raw, list) and draft_raw:
        return [_flatten_pick(i) if isinstance(i, dict) else i for i in draft_raw]

    # Shape A — YFPY object with __dict__
    if hasattr(draft_raw, "__dict__"):
        raw_dict = draft_raw.__dict__
        for key in ("draft_results", "picks", "draft_result"):
            val = raw_dict.get(key)
            if isinstance(val, list) and val:
                return [_flatten_pick(i) if isinstance(i, dict) else i for i in val]
            if isinstance(val, dict):
                inner = list(val.values())
                if inner and any(_is_pick(x) for x in inner):
                    return [_flatten_pick(i) if isinstance(i, dict) else i for i in inner]

    # Shape E — iterable YFPY object
    if not isinstance(draft_raw, (list, dict)) and hasattr(draft_raw, "__iter__"):
        try:
            items = [convert_fn(i) if not isinstance(i, dict) else i for i in draft_raw]
            if items and any(_is_pick(x) for x in items):
                return [_flatten_pick(i) for i in items]
        except Exception:
            pass

    # Convert to dict for shapes B and C
    try:
        converted = convert_fn(draft_raw)
    except Exception:
        return []

    if isinstance(converted, list) and converted:
        return [_flatten_pick(i) if isinstance(i, dict) else i for i in converted]

    if not isinstance(converted, dict):
        return []

    # Shape B — named key
    for key in ("draft_results", "picks", "draft_result"):
        val = converted.get(key)
        if isinstance(val, list) and val:
            return [_flatten_pick(i) if isinstance(i, dict) else i for i in val]
        if isinstance(val, dict):
            inner = list(val.values())
            if inner and any(_is_pick(x) for x in inner):
                return [_flatten_pick(i) if isinstance(i, dict) else i for i in inner]

    # Shape C — numbered-key dict {"0": pick, "1": pick, ...}
    keys = list(converted.keys())
    if keys and all(str(k).isdigit() for k in keys):
        items = [converted[k] for k in sorted(keys, key=lambda x: int(x))]
        return [_flatten_pick(i) if isinstance(i, dict) else i for i in items]

    # Last resort — any top-level values that look like picks
    candidates = [v for v in converted.values() if _is_pick(v)]
    return [_flatten_pick(i) for i in candidates]


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

    CONFIRMED field paths from live API extract:
      standings → teams[N] → {"team": {...}} wrapper
      team.team_key, team.team_id, team.name
      team.team_standings.rank, .playoff_seed, .points_for, .points_against
      team.team_standings.outcome_totals.{wins, losses, ties}
      team.managers → {"manager": {...}} or list of {"manager":{...}}
      team.managers.manager.guid (stable cross-season identifier)
    """
    from services.fantasy.league_service import _convert_to_dict
    from config import get_manager_identity

    def _unwrap(obj):
        if not isinstance(obj, dict): return {}
        base = dict(obj.get("_extracted_data", {})) if isinstance(obj.get("_extracted_data"), dict) else {}
        for k, v in obj.items():
            if k not in ("_extracted_data", "_index", "_keys"): base[k] = v
        return base

    def _extract_logo(team: dict) -> str | None:
        logos = team.get("team_logos", {})
        if isinstance(logos, list): logos = logos[0] if logos else {}
        logo_obj = logos.get("team_logo", {}) if isinstance(logos, dict) else {}
        if isinstance(logo_obj, list): logo_obj = logo_obj[0] if logo_obj else {}
        logo_obj = _unwrap(logo_obj) if isinstance(logo_obj, dict) else {}
        return logo_obj.get("url")

    # Get standings — confirmed shape: {"teams": [{"team": {...}}, ...]}
    standings_raw = _convert_to_dict(query.get_league_standings())
    if isinstance(standings_raw, dict):
        raw_teams = standings_raw.get("teams", list(standings_raw.values()))
    elif isinstance(standings_raw, list):
        raw_teams = standings_raw
    else:
        raw_teams = []
    if isinstance(raw_teams, dict):
        raw_teams = list(raw_teams.values())

    # Unwrap each team — {"team": {...}} → inner dict
    teams_list = []
    for item in raw_teams:
        t = _unwrap(item)
        inner = t.get("team", t)
        teams_list.append(_unwrap(inner) if isinstance(inner, dict) else t)

    # Build rank maps using confirmed field paths
    def _rank_map(field: str) -> dict:
        vals = sorted(
            [(t.get("team_key", ""), float(t.get("team_standings", {}).get(field) or 0))
             for t in teams_list if isinstance(t, dict)],
            key=lambda x: x[1], reverse=True,
        )
        return {tk: i + 1 for i, (tk, _) in enumerate(vals) if tk}

    pf_rank_map = _rank_map("points_for")
    pa_rank_map = _rank_map("points_against")

    season_data  = {}
    team_key_map = {}

    for t in teams_list:
        if not isinstance(t, dict):
            continue
        team_key = t.get("team_key", "")
        if not team_key:
            continue

        # team_standings — confirmed location
        ts = t.get("team_standings", {}) or {}
        ot = ts.get("outcome_totals", {}) or {}

        # Manager identity via team_key
        identity   = get_manager_identity(team_key=team_key)
        manager_id = identity["manager_id"] if identity else None
        if not manager_id:
            continue

        wins   = int(ot.get("wins")   or 0)
        losses = int(ot.get("losses") or 0)
        ties   = int(ot.get("ties")   or 0)
        games  = wins + losses + ties
        pf     = float(ts.get("points_for")    or 0)
        pa     = float(ts.get("points_against") or 0)
        rank   = ts.get("rank")
        seed   = ts.get("playoff_seed")

        team_key_map[manager_id] = team_key
        season_data[manager_id] = {
            "team_key":     team_key,
            "team_id":      team_key.split(".t.")[-1] if ".t." in team_key else None,
            "display_name": identity["display_name"] if identity else manager_id,
            "team_name":    t.get("name"),
            "logo_url":     _extract_logo(t),
            "_rs": {
                "wins": wins, "losses": losses, "ties": ties, "games": games,
                "pf": pf, "pa": pa, "proj_pf": 0.0, "proj_pa": 0.0,
                "rank": rank, "seed": seed,
                "pf_rank": pf_rank_map.get(team_key),
                "pa_rank": pa_rank_map.get(team_key),
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
        raw = _load_json(_get_data_path("results.json"))
        if not raw:
            raise HTTPException(status_code=404, detail="results.json not found.")

        # Detect legacy double-wrapped shape: {"total_seasons": N, "years": [...], "data": {...}}
        # If the file was previously saved by an old download endpoint that wrapped before writing,
        # unwrap it so we return and re-save just the year-keyed data dict.
        if "data" in raw and "total_seasons" in raw and "years" in raw:
            data = raw["data"]
            # Also check if _that_ is double-wrapped (shouldn't be, but be safe)
            if "data" in data and "total_seasons" in data:
                data = data["data"]
        else:
            data = raw

        # Only keep year-keyed entries
        data = {k: v for k, v in data.items() if str(k).isdigit()}

        return {
            "total_seasons": len(data),
            "years":         sorted(data.keys(), reverse=True),
            "data":          data,
        }
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



# ============================================================
# TRANSACTIONS
# ============================================================
@router.get("/data/transactions/build-all")
def build_transactions(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None, description="Single year e.g. '2025'"),
    year_from: int     = Query(default=None, description="Start of year range e.g. 2007"),
    year_to: int       = Query(default=None, description="End of year range e.g. 2010"),
    force_clean: bool  = Query(default=False),
):
    """
    Generates transactions.json — adds, drops, trades per season.

    ⚠️  Build in batches of 4-5 years to avoid Render's 30s timeout:
        ?year_from=2007&year_to=2010
        ?year_from=2011&year_to=2014
        ?year_from=2015&year_to=2018
        ?year_from=2019&year_to=2022
        ?year_from=2023&year_to=2025

    CONFIRMED from API extract + debug:
      - query.get_league_transactions() returns a list of Transaction dicts
      - type, status, timestamp, faab_bid, trader/tradee_team_key at top level
      - players field shapes by type:
          add/drop → list of {"player": {...}}
          trade    → list of {"player": {...}}
          add      → dict  {"player": {...}}  (single player)
          drop     → dict  {"player": {...}}  (single player)
          commish  → empty list (skip)
      - After live _convert_to_dict, players may be {"players": [...]}
        (nested one level deeper) — normalization handles this
      - Player fields: player_key, full_name, display_position at top level
      - transaction_data at top level: type, source_type, source_team_key,
        destination_team_key, destination_team_name, destination_type

    Shape:
        {"2025": {"trades": [...], "moves": [...], "total_trades": N, "total_moves": N}}
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

        if year:
            target_years = [year]
        elif year_from or year_to:
            lo = int(year_from) if year_from else 2007
            hi = int(year_to)   if year_to   else 2025
            target_years = [y for y in all_years if lo <= int(y) <= hi]
        else:
            target_years = all_years

        results = {"success": [], "skipped": [], "failed": {}}

        def _ts_to_date(ts):
            if not ts: return None
            try:
                return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
            except Exception:
                return None

        def _to_dict_tx(obj):
            """Convert a YFPY object to dict. Used for player items inside transactions."""
            if isinstance(obj, dict): return obj
            try: return _convert_to_dict(obj)
            except Exception: return {}

        def _norm_players(raw) -> list:
            """
            Normalise the players field to a flat list of player wrapper dicts.

            Handles all confirmed shapes from live YFPY:
              - list of {"player": {...}}          → add/drop, trade
              - dict {"player": {...}}             → single add or drop
              - dict {"players": [...]}            → YFPY wraps list in extra dict
              - list of YFPY Player objects        → convert each individually
              - list containing a list (double-wrapped) → flatten
            """
            if isinstance(raw, list):
                flat = []
                for item in raw:
                    if isinstance(item, list):
                        flat.extend(item)
                    else:
                        # CRITICAL: convert each YFPY Player object individually
                        flat.append(_to_dict_tx(item) if not isinstance(item, dict) else item)
                return flat
            if isinstance(raw, dict):
                if "player" in raw:
                    return [raw]
                if "players" in raw:
                    return _norm_players(raw["players"])
                keys = list(raw.keys())
                if keys and all(str(k).isdigit() for k in keys):
                    return [_to_dict_tx(raw[k]) for k in sorted(keys, key=lambda x: int(x))]
                return [_to_dict_tx(v) for v in raw.values()]
            # YFPY Players collection object — convert it
            if not isinstance(raw, (list, dict)):
                converted = _to_dict_tx(raw)
                if isinstance(converted, list):
                    return _norm_players(converted)
                if isinstance(converted, dict):
                    return _norm_players(converted)
            return []

        def _extract_player(pw) -> dict:
            """
            Extract player info from a {"player": {...}} wrapper or flat player dict.

            CONFIRMED from debug: after live _convert_to_dict on Transaction objects,
            inner player dict has player_key + transaction_data but NOT full_name.
            We store player_key as the join key; name enriched at endpoint from player_info.json.

            transaction_data confirmed present with: type, source_type,
            source_team_key (empty str for adds), destination_team_key (empty str for drops).
            """
            if not isinstance(pw, dict):
                pw = _to_dict_tx(pw)

            # Unwrap {"player": {...}} wrapper
            if "player" in pw:
                p = pw["player"]
                if not isinstance(p, dict):
                    p = _to_dict_tx(p)
            else:
                p = pw

            if not isinstance(p, dict):
                return {}

            # transaction_data is confirmed at top level of inner player dict
            td_raw = p.get("transaction_data") or {}
            if isinstance(td_raw, dict):
                td = td_raw
            else:
                td = _to_dict_tx(td_raw) if td_raw else {}
            if not isinstance(td, dict):
                td = {}

            # Name — may be null for live Transaction players; use player_key for join
            name = p.get("full_name") or ""
            if not name:
                name_raw = p.get("name") or {}
                if isinstance(name_raw, dict):
                    name = (name_raw.get("_extracted_data") or {}).get("full") or name_raw.get("full") or ""
                elif not isinstance(name_raw, dict):
                    name = _to_dict_tx(name_raw).get("full") or ""

            return {
                "player_key": p.get("player_key"),
                "name":       name or None,   # null is fine — join from player_info.json
                "position":   p.get("display_position") or p.get("primary_position"),
                "nfl_team":   p.get("editorial_team_abbr"),
                "td":         td,
            }

        def _week_from_date(date_str: str, week_map: list) -> int | None:
            if not date_str or not week_map: return None
            for entry in week_map:
                if entry.get("week_start", "") <= date_str <= entry.get("week_end", ""):
                    return entry.get("week")
            return None

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                # Build week map from settings
                week_map = []
                try:
                    settings = _convert_to_dict(query.get_league_settings())
                    end_week = int(settings.get("end_week") or 17)
                    for wk in range(1, end_week + 1):
                        try:
                            sb  = _convert_to_dict(query.get_league_scoreboard_by_week(wk))
                            matchups = sb.get("matchups", []) if isinstance(sb, dict) else []
                            if matchups:
                                m = matchups[0]
                                m = m.get("matchup", m) if isinstance(m, dict) else m
                                ws = m.get("week_start")
                                we = m.get("week_end")
                                if ws and we:
                                    week_map.append({"week": wk, "week_start": ws, "week_end": we})
                        except Exception:
                            continue
                except Exception:
                    pass

                # Fetch all transactions
                tx_raw  = _convert_to_dict(query.get_league_transactions())
                if isinstance(tx_raw, list):
                    tx_list = tx_raw
                elif isinstance(tx_raw, dict):
                    tx_list = tx_raw.get("transactions", [])
                    if not tx_list:
                        keys = list(tx_raw.keys())
                        if keys and all(str(k).isdigit() for k in keys):
                            tx_list = [tx_raw[k] for k in sorted(keys, key=lambda x: int(x))]
                        else:
                            for v in tx_raw.values():
                                if isinstance(v, list) and v:
                                    tx_list = v
                                    break
                else:
                    tx_list = []

                # Load player_info for name/position enrichment (may be {} if not built yet)
                _pi      = _load_json(_get_data_path("player_info.json"))
                _pi_yr   = _pi.get(str(yr), {})
                _players = _pi_yr.get("players", {}) if isinstance(_pi_yr, dict) else {}

                def _enrich(player_key: str) -> dict:
                    """Return {name, position, nfl_team} from player_info if available."""
                    if not player_key or not _players:
                        return {"name": None, "position": None, "nfl_team": None}
                    pi = _players.get(str(player_key), {})
                    return {
                        "name":     pi.get("name"),
                        "position": pi.get("position"),
                        "nfl_team": pi.get("nfl_team"),
                    }

                trades      = []
                moves       = []
                item_errors = []

                for item in tx_list:
                    try:
                        # CRITICAL: item is a YFPY Transaction object, not a dict.
                        # Must convert individually — _convert_to_dict on the outer
                        # list does NOT convert the Transaction objects inside it.
                        tx = _to_dict_tx(item)
                        ed     = tx.get("_extracted_data") or {}
                        ttype  = tx.get("type")  or (ed.get("type")  if isinstance(ed, dict) else None) or ""
                        status = tx.get("status") or (ed.get("status") if isinstance(ed, dict) else None) or ""

                        if status != "successful":
                            continue

                        ttype_norm = ttype.lower().replace(" ", "_")
                        is_trade   = ttype_norm == "trade"
                        is_move    = ttype_norm in ("add", "drop", "add/drop", "waiver", "free_agent")
                        if not is_trade and not is_move:
                            continue  # skip commish, unknown types

                        ts       = tx.get("timestamp") or (ed.get("timestamp") if isinstance(ed, dict) else None)
                        date_str = _ts_to_date(ts)
                        week_num = _week_from_date(date_str, week_map)
                        faab     = tx.get("faab_bid") or (ed.get("faab_bid") if isinstance(ed, dict) else None)
                        try:
                            faab_int = int(faab) if faab is not None else None
                        except (TypeError, ValueError):
                            faab_int = None

                        # Normalise players to flat list
                        players_raw  = tx.get("players") or (ed.get("players") if isinstance(ed, dict) else None) or []
                        players_list = _norm_players(players_raw)

                        if is_trade:
                            trader_tk = str(tx.get("trader_team_key") or (ed.get("trader_team_key") if isinstance(ed, dict) else "") or "")
                            tradee_tk = str(tx.get("tradee_team_key") or (ed.get("tradee_team_key") if isinstance(ed, dict) else "") or "")
                            ti_a      = get_manager_identity(team_key=trader_tk)
                            ti_b      = get_manager_identity(team_key=tradee_tk)
                            mgr_a     = ti_a["manager_id"]   if ti_a else trader_tk
                            name_a    = ti_a["display_name"] if ti_a else trader_tk
                            mgr_b     = ti_b["manager_id"]   if ti_b else tradee_tk
                            name_b    = ti_b["display_name"] if ti_b else tradee_tk

                            a_received, b_received = [], []
                            for pw in players_list:
                                pi      = _extract_player(pw)
                                dest_tk = pi["td"].get("destination_team_key") or ""
                                pk      = pi["player_key"]
                                enrich  = _enrich(pk)
                                entry   = {
                                    "player_key": pk,
                                    "name":       pi["name"] or enrich["name"],
                                    "position":   pi["position"] or enrich["position"],
                                    "nfl_team":   pi["nfl_team"] or enrich["nfl_team"],
                                }
                                if dest_tk == trader_tk:
                                    a_received.append(entry)
                                else:
                                    b_received.append(entry)

                            trades.append({
                                "week":           week_num,
                                "date":           date_str,
                                "manager_a":      mgr_a,
                                "manager_a_name": name_a,
                                "manager_b":      mgr_b,
                                "manager_b_name": name_b,
                                "a_received":     a_received,
                                "b_received":     b_received,
                            })

                        elif is_move:
                            added, dropped = [], []
                            for pw in players_list:
                                pi        = _extract_player(pw)
                                move_type = (pi["td"].get("type") or "").lower()
                                pk        = pi["player_key"]
                                enrich    = _enrich(pk)
                                entry     = {
                                    "player_key": pk,
                                    "name":       pi["name"] or enrich["name"],
                                    "position":   pi["position"] or enrich["position"],
                                    "nfl_team":   pi["nfl_team"] or enrich["nfl_team"],
                                }
                                if move_type == "add":
                                    added.append({**entry,
                                                  "source_type": pi["td"].get("source_type") or "",
                                                  "waiver_bid":  faab_int})
                                elif move_type == "drop":
                                    dropped.append(entry)

                            if not added and not dropped:
                                continue

                            # Manager = destination team of add, or source team of drop
                            team_key = None
                            for pw in players_list:
                                pi = _extract_player(pw)
                                mt = (pi["td"].get("type") or "").lower()
                                if mt == "add":
                                    team_key = pi["td"].get("destination_team_key") or ""
                                    break
                                elif mt == "drop":
                                    team_key = pi["td"].get("source_team_key") or ""
                                    break

                            identity     = get_manager_identity(team_key=team_key) if team_key else None
                            manager_id   = identity["manager_id"]   if identity else team_key
                            display_name = identity["display_name"] if identity else team_key

                            moves.append({
                                "week":         week_num,
                                "date":         date_str,
                                "manager":      manager_id,
                                "display_name": display_name,
                                "added":        added,
                                "dropped":      dropped,
                            })

                    except Exception as e:
                        item_errors.append(str(e)[:120])
                        continue

                existing[yr] = {
                    "total_trades": len(trades),
                    "total_moves":  len(moves),
                    "trades":       sorted(trades, key=lambda x: (x.get("week") or 99, x.get("date") or "")),
                    "moves":        sorted(moves,  key=lambda x: (x.get("week") or 99, x.get("date") or "")),
                    "_build_stats": {
                        "total_items":  len(tx_list),
                        "trades_found": len(trades),
                        "moves_found":  len(moves),
                        "item_errors":  item_errors[:10],
                    },
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
    """Shows trade and move counts per year in transactions.json."""
    try:
        data = _load_json(_get_data_path("transactions.json"))
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            s = data[yr]
            summary.append({
                "year":         int(yr),
                "total_trades": s.get("total_trades", len(s.get("trades", []))),
                "total_moves":  s.get("total_moves",  len(s.get("moves",  []))),
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
            raise HTTPException(status_code=404, detail="transactions.json not found. Run build-all first.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/transactions/debug")
def debug_transactions_raw(year: str = Query(default="2025")):
    """Returns raw transaction response shape for diagnosis."""
    try:
        from services.fantasy.league_service import get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query

        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)
        raw        = query.get_league_transactions()
        converted  = _convert_to_dict(raw)

        if isinstance(converted, list):
            tx_list = converted
        elif isinstance(converted, dict):
            tx_list = converted.get("transactions", [])
            if not tx_list:
                for v in converted.values():
                    if isinstance(v, list) and v:
                        tx_list = v; break
        else:
            tx_list = []

        sample = tx_list[:2] if tx_list else []

        # For each sample show the players field shape
        samples_annotated = []
        for tx in sample:
            players = tx.get("players") or {}
            samples_annotated.append({
                "type":         tx.get("type"),
                "status":       tx.get("status"),
                "players_type": type(players).__name__,
                "players_keys": list(players.keys()) if isinstance(players, dict) else len(players),
                "full":         tx,
            })

        return {
            "total_items":    len(tx_list),
            "converted_type": type(converted).__name__,
            "sample_items":   samples_annotated,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================
# PLAYER INFO
# ============================================================
# PLAYER INFO
# ============================================================
@router.get("/data/player-info/build-all")
def build_player_info(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None, description="Single year e.g. '2025'"),
    year_from: int     = Query(default=None, description="Start of year range e.g. 2007"),
    year_to: int       = Query(default=None, description="End of year range e.g. 2010"),
    force_clean: bool  = Query(default=False),
):
    """
    Generates player_info.json — complete player metadata, one record per player_key.

    This is the SOURCE OF TRUTH for player name, position, NFL team.
    rosters.json and player_stats.json reference player_key only — join here for display.

    ⚠️  Do NOT run without a year filter — 19 seasons will 502 (Render 30s timeout).
    Build in batches of 4-5 years to stay safely under 30 seconds:
        ?year_from=2007&year_to=2010
        ?year_from=2011&year_to=2014
        ?year_from=2015&year_to=2018
        ?year_from=2019&year_to=2022
        ?year_from=2023&year_to=2025

    Or one at a time: ?year=2025

    CONFIRMED from YFPY v17:
      - query.get_league_players() with NO arguments returns all ~1,187 players at once
      - Returns list of Player objects; MUST call _convert_to_dict on EACH item
      - After per-item conversion: clean flat dict, player_key and full_name at top level
      - bye is an integer at top level (not bye_weeks.week)

    Shape: {"2025": {"total_players": N, "players": {"461.p.32723": {full record}}}}
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict,
        )
        from services.yahoo_service import get_query

        path     = _get_data_path("player_info.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])

        if year:
            target_years = [year]
        elif year_from or year_to:
            lo = int(year_from) if year_from else 2007
            hi = int(year_to)   if year_to   else 2025
            target_years = [y for y in all_years if lo <= int(y) <= hi]
        else:
            target_years = all_years

        results = {"success": [], "skipped": [], "failed": {}}

        def _to_dict(obj):
            """Convert a YFPY object or dict to a plain dict."""
            if isinstance(obj, dict):
                return obj
            try:
                return _convert_to_dict(obj)
            except Exception:
                return {}

        def _get_name(p: dict) -> tuple:
            """
            Get (full, first, last) from a player dict.
            After per-item _convert_to_dict, YFPY Player properties like full_name
            may not survive — the reliable source is p['name']['full'].
            Checks all known locations in priority order.
            """
            # 1. Top-level convenience fields (YFPY Player properties, may survive)
            full  = p.get("full_name") or ""
            first = p.get("first_name") or ""
            last  = p.get("last_name") or ""
            if full:
                return full, first, last

            # 2. name sub-dict — always present, most reliable
            name_raw = p.get("name") or {}
            if isinstance(name_raw, dict):
                # Try _extracted_data inside name first
                name_ed = name_raw.get("_extracted_data") or {}
                if isinstance(name_ed, dict) and name_ed.get("full"):
                    return (str(name_ed.get("full", "")),
                            str(name_ed.get("first", "")),
                            str(name_ed.get("last", "")))
                # Then name dict top-level fields
                if name_raw.get("full"):
                    return (str(name_raw.get("full", "")),
                            str(name_raw.get("first", "")),
                            str(name_raw.get("last", "")))

            return "", "", ""

        def _get_bye(p: dict) -> int | None:
            """
            Get bye week integer from a player dict.
            Checks top-level bye, bye_weeks.week, and _extracted_data paths.
            """
            # 1. Top-level bye integer (YFPY Player property)
            bye = p.get("bye")
            if bye is not None:
                try: return int(bye)
                except (TypeError, ValueError): pass

            # 2. bye_weeks sub-dict
            bw = p.get("bye_weeks") or {}
            if isinstance(bw, dict):
                for src in [bw.get("_extracted_data") or {}, bw]:
                    if isinstance(src, dict):
                        wk = src.get("week")
                        if wk is not None:
                            try: return int(wk)
                            except (TypeError, ValueError): pass

            # 3. Player's own _extracted_data
            ed = p.get("_extracted_data") or {}
            if isinstance(ed, dict):
                bw_ed = ed.get("bye_weeks") or {}
                if isinstance(bw_ed, dict):
                    for src in [bw_ed.get("_extracted_data") or {}, bw_ed]:
                        if isinstance(src, dict):
                            wk = src.get("week")
                            if wk is not None:
                                try: return int(wk)
                                except (TypeError, ValueError): pass
            return None

        def _extract_player_info(p: dict) -> dict | None:
            pk = p.get("player_key")
            if not pk:
                return None

            full, first, last = _get_name(p)

            ep_raw   = p.get("eligible_positions") or []
            eligible = []
            for ep in (ep_raw if isinstance(ep_raw, list) else []):
                if isinstance(ep, dict): eligible.append(ep.get("position") or "")
                elif isinstance(ep, str): eligible.append(ep)

            return {
                "player_key":        pk,
                "player_id":         p.get("player_id"),
                "name":              full,
                "first_name":        first,
                "last_name":         last,
                "position":          p.get("display_position") or p.get("primary_position") or "",
                "position_type":     p.get("position_type") or "",
                "eligible_positions":[e for e in eligible if e],
                "nfl_team":          p.get("editorial_team_abbr") or "",
                "nfl_team_full":     p.get("editorial_team_full_name") or "",
                "uniform_number":    p.get("uniform_number"),
                "headshot_url":      p.get("headshot_url") or p.get("image_url") or "",
                "status":            p.get("status") or "",
                "status_full":       p.get("status_full") or "",
                "injury_note":       p.get("injury_note") or "",
                "is_undroppable":    bool(int(p.get("is_undroppable") or 0)),
                "bye_week":          _get_bye(p),
            }

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr].get("players"):
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                raw_list = query.get_league_players()

                # Normalise outer container to a list
                if isinstance(raw_list, list):
                    items = raw_list
                else:
                    converted_outer = _convert_to_dict(raw_list)
                    if isinstance(converted_outer, list):
                        items = converted_outer
                    elif isinstance(converted_outer, dict):
                        items = converted_outer.get("players", [])
                        if not items:
                            for v in converted_outer.values():
                                if isinstance(v, list) and v:
                                    items = v; break
                    else:
                        items = []

                players_dict: dict = {}
                for item in items:
                    # CRITICAL: convert each item individually — _convert_to_dict on the
                    # outer list does NOT convert the individual Player objects inside it
                    p  = _to_dict(item)
                    pi = _extract_player_info(p)
                    if pi and pi.get("player_key"):
                        players_dict[pi["player_key"]] = pi

                existing[yr] = {
                    "year":          int(yr),
                    "total_players": len(players_dict),
                    "players":       players_dict,
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
            "next_step":       "GET /league/data/player-info/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/player-info/status")
def player_info_status():
    try:
        data = _load_json(_get_data_path("player_info.json"))
        if not data:
            return {"status": "file_not_found", "years": []}
        return {
            "total_seasons": len(data),
            "seasons": [
                {"year": int(yr), "total_players": data[yr].get("total_players", 0)}
                for yr in sorted(data.keys(), reverse=True)
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/player-info/download")
def download_player_info():
    try:
        data = _load_json(_get_data_path("player_info.json"))
        if not data:
            raise HTTPException(status_code=404, detail="player_info.json not found. Run build-all first.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ROSTERS
# ============================================================
@router.get("/data/rosters/build-all")
def build_rosters(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None),
    week: int          = Query(default=None, description="Single week, omit for all"),
    force_clean: bool  = Query(default=False),
):
    """
    Generates rosters.json — weekly roster slot data per team per season.

    LEAN SCHEMA: Only player_key + slot data. Join with player_info.json for
    name/position/nfl_team. This keeps the file ~67% smaller.

    ⚠️  MUST BUILD ONE WEEK AT A TIME to avoid 502 timeout.
    10 teams × 1 week = 10 API calls (~2s). All weeks at once = 200 calls (40s+).
    Render's request timeout is 30s — building all weeks in one call will 502.

    Recommended build pattern:
        GET /league/data/rosters/build-all?year=2025&week=1
        GET /league/data/rosters/build-all?year=2025&week=2
        ... through week=17 (or 18-20 for playoff weeks)
        Each call adds that week to the file without overwriting previous weeks.

    CONFIRMED from YFPY v17:
      - Use get_team_roster_player_info_by_week(team_id, week) → List[Player]
      - Must call _convert_to_dict on each Player item individually
      - selected_position at top level after conversion (roster slot: QB/WR/BN/IR)
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict,
        )
        from services.yahoo_service import get_query
        from config import get_manager_identity
        import time

        path     = _get_data_path("rosters.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])
        target_years = [year] if year else all_years
        results      = {"success": [], "skipped": [], "failed": {}}

        def _to_dict(obj):
            if isinstance(obj, dict): return obj
            try: return _convert_to_dict(obj)
            except Exception: return {}

        def _extract_slot(p: dict) -> dict | None:
            pk = p.get("player_key")
            if not pk: return None
            sp_raw = p.get("selected_position")
            if isinstance(sp_raw, dict):
                sp = sp_raw.get("position") or p.get("selected_position_value") or ""
            else:
                sp = str(sp_raw or p.get("selected_position_value") or "")
            return {
                "player_key":        pk,
                "selected_position": sp,
                "is_starting":       sp not in ("BN", "IR", "IR+", ""),
                "is_on_bench":       sp == "BN",
                "is_on_ir":          sp in ("IR", "IR+"),
            }

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr] and not week:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                settings     = _convert_to_dict(query.get_league_settings())
                start_week   = int(settings.get("start_week") or 1)
                end_week     = int(settings.get("end_week")   or 17)

                # Collect team_id list
                # Primary: get_league_teams() API call
                # Fallback: extract from matchups.json (works for pre-2015 seasons
                # where Yahoo's /teams endpoint returns "No valid server" 500 error)
                team_info: list[dict] = []
                try:
                    teams_raw = _convert_to_dict(query.get_league_teams())
                    if isinstance(teams_raw, list): teams_list = teams_raw
                    elif isinstance(teams_raw, dict):
                        teams_list = teams_raw.get("teams", list(teams_raw.values()))
                    else: teams_list = []

                    for t in teams_list:
                        t = _to_dict(t) if not isinstance(t, dict) else t
                        tk = t.get("team_key") or (_to_dict(t.get("_extracted_data") or {})).get("team_key")
                        if not tk: continue
                        tid      = str(tk).split(".t.")[-1] if ".t." in str(tk) else None
                        identity = get_manager_identity(team_key=tk)
                        team_info.append({
                            "team_key":     str(tk),
                            "team_id":      tid,
                            "manager_id":   identity["manager_id"]   if identity else str(tk),
                            "display_name": identity["display_name"] if identity else str(tk),
                        })
                except Exception:
                    pass

                # Fallback: extract team_id + manager_id from matchups.json
                # matchups[year][weeks][N][matchups][M][teams][T] has team_key and team_id
                if not team_info:
                    matchups_data = _load_json(_get_data_path("matchups.json"))
                    yr_matchups   = matchups_data.get(str(yr), {})
                    seen_tids: set = set()
                    for wk_entry in yr_matchups.get("weeks", []):
                        for m in wk_entry.get("matchups", []):
                            for t in m.get("teams", []):
                                tk  = t.get("team_key") or ""
                                tid = t.get("team_id") or (
                                    str(tk).split(".t.")[-1] if ".t." in str(tk) else None
                                )
                                mid = t.get("manager_id") or ""
                                if tid and tid not in seen_tids and mid:
                                    seen_tids.add(tid)
                                    identity = get_manager_identity(manager_id=mid)
                                    team_info.append({
                                        "team_key":     tk,
                                        "team_id":      tid,
                                        "manager_id":   mid,
                                        "display_name": t.get("display_name") or mid.title(),
                                    })
                        if len(team_info) >= 10:
                            break  # all teams found, stop scanning weeks

                season_rosters = existing.get(yr, {}) if (not force_clean and week) else {}
                target_weeks   = [week] if week else list(range(start_week, end_week + 1))

                for wk in target_weeks:
                    week_key  = f"week_{wk}"
                    week_data: dict = {}

                    for ti in team_info:
                        try:
                            raw = query.get_team_roster_player_info_by_week(ti["team_id"], wk)
                            if isinstance(raw, list):
                                player_list = [_to_dict(item) for item in raw]
                            else:
                                converted = _convert_to_dict(raw)
                                if isinstance(converted, list):
                                    player_list = [_to_dict(item) for item in converted]
                                elif isinstance(converted, dict):
                                    inner = converted.get("players", [])
                                    player_list = [_to_dict(item) for item in (inner if isinstance(inner, list) else list(inner.values()) if isinstance(inner, dict) else [])]
                                else:
                                    player_list = []

                            slots = [_extract_slot(p) for p in player_list if isinstance(p, dict)]
                            slots = [s for s in slots if s]

                            week_data[ti["manager_id"]] = {
                                "team_key":     ti["team_key"],
                                "display_name": ti["display_name"],
                                "player_count": len(slots),
                                "starters":     sum(1 for s in slots if s["is_starting"]),
                                "bench":        sum(1 for s in slots if s["is_on_bench"]),
                                "ir":           sum(1 for s in slots if s["is_on_ir"]),
                                "players":      slots,
                            }
                            time.sleep(0.2)
                        except Exception as e:
                            week_data[ti["manager_id"]] = {
                                "team_key": ti["team_key"], "error": str(e)[:150], "players": []
                            }

                    season_rosters[week_key] = week_data

                existing[yr] = season_rosters
                results["success"].append(int(yr))

            except Exception as e:
                results["failed"][yr] = str(e)

        sorted_data = _year_sort(existing)
        _write_json(path, sorted_data)
        return {
            "status": "complete", "seasons_updated": results["success"],
            "seasons_skipped": results["skipped"], "seasons_failed": results["failed"],
            "total_seasons": len(sorted_data), "file_written": path,
            "note": "⚠️  Build ONE WEEK AT A TIME to avoid 502: ?year=2025&week=1, then &week=2, etc.",
            "next_step": "GET /league/data/rosters/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/rosters/status")
def rosters_status():
    try:
        data = _load_json(_get_data_path("rosters.json"))
        if not data: return {"status": "file_not_found", "years": []}
        return {"total_seasons": len(data), "seasons": [
            {"year": int(yr), "weeks_built": len(data[yr]),
             "teams_per_week": len(next(iter(data[yr].values()), {}))}
            for yr in sorted(data.keys(), reverse=True)
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/rosters/download")
def download_rosters():
    try:
        data = _load_json(_get_data_path("rosters.json"))
        if not data:
            raise HTTPException(status_code=404, detail="rosters.json not found. Run build-all first.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# PLAYER STATS
# ============================================================
@router.get("/data/player-stats/build-all")
def build_player_stats(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None),
    week: int          = Query(default=None, description="Single week, omit for all"),
    force_clean: bool  = Query(default=False),
):
    """
    Generates player_stats.json — weekly fantasy points and raw stat lines.

    LEAN SCHEMA: Only player_key + points + stats dict. Join with player_info.json
    for name/position/nfl_team. Skips zero-stat players to keep files compact.

    CONFIRMED from YFPY v17:
      - Use get_team_roster_player_stats_by_week(team_id, week) → List[Player]
        Gets all 10 teams' rostered players' stats: 10 calls/week, not 1,400+
      - Must call _convert_to_dict on each Player item individually
      - player_points.total = fantasy points for the week
      - player_stats.stats = list of {"stat": {"stat_id": N, "value": V}}

    Shape per player entry:
        {"fantasy_points": 25.8, "stats": {"2": 19, "4": 152, "10": 2}}
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict,
        )
        from services.yahoo_service import get_query
        import time

        path     = _get_data_path("player_stats.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])
        target_years = [year] if year else all_years
        results      = {"success": [], "skipped": [], "failed": {}}

        def _to_dict(obj):
            if isinstance(obj, dict): return obj
            try: return _convert_to_dict(obj)
            except Exception: return {}

        def _extract_stats(p: dict) -> dict:
            """Extract lean stats entry: just points + raw stat_id→value dict."""
            pts_raw        = p.get("player_points") or {}
            fantasy_points = float(pts_raw.get("total") or 0) if isinstance(pts_raw, dict) else float(p.get("player_points_value") or 0)

            stats_raw = p.get("player_stats") or {}
            stat_list = stats_raw.get("stats", []) if isinstance(stats_raw, dict) else (stats_raw if isinstance(stats_raw, list) else [])

            stats_out: dict = {}
            for entry in stat_list:
                if not isinstance(entry, dict): continue
                stat = entry.get("stat", entry)
                if not isinstance(stat, dict): continue
                sid = stat.get("stat_id")
                val = stat.get("value")
                if sid is not None and val not in (None, "", "-"):
                    try:
                        fval = float(val)
                        if fval != 0:
                            stats_out[str(sid)] = fval
                    except (TypeError, ValueError):
                        pass

            return {"fantasy_points": fantasy_points, "stats": stats_out}

        for yr in target_years:
            yr_stats = existing.get(yr, {})
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                settings   = _convert_to_dict(query.get_league_settings())
                start_week = int(settings.get("start_week") or 1)
                end_week   = int(settings.get("end_week")   or 17)

                # Collect numeric team IDs
                # Primary: get_league_teams() API call
                # Fallback: extract from matchups.json for pre-2015 seasons
                team_ids: list[str] = []
                try:
                    teams_raw  = _convert_to_dict(query.get_league_teams())
                    teams_list = teams_raw if isinstance(teams_raw, list) else (
                        teams_raw.get("teams", list(teams_raw.values())) if isinstance(teams_raw, dict) else []
                    )
                    for t in teams_list:
                        t  = _to_dict(t) if not isinstance(t, dict) else t
                        tk = t.get("team_key") or (_to_dict(t.get("_extracted_data") or {})).get("team_key")
                        if tk and ".t." in str(tk):
                            team_ids.append(str(tk).split(".t.")[-1])
                except Exception:
                    pass

                if not team_ids:
                    matchups_data = _load_json(_get_data_path("matchups.json"))
                    yr_matchups   = matchups_data.get(str(yr), {})
                    seen: set = set()
                    for wk_entry in yr_matchups.get("weeks", []):
                        for m in wk_entry.get("matchups", []):
                            for t in m.get("teams", []):
                                tk  = t.get("team_key") or ""
                                tid = t.get("team_id") or (
                                    str(tk).split(".t.")[-1] if ".t." in str(tk) else None
                                )
                                if tid and tid not in seen:
                                    seen.add(tid)
                                    team_ids.append(tid)
                        if len(team_ids) >= 10:
                            break

                target_weeks = [week] if week else list(range(start_week, end_week + 1))

                for wk in target_weeks:
                    week_key = f"week_{wk}"
                    if skip_existing and not force_clean and week_key in yr_stats and yr_stats[week_key]:
                        continue

                    week_stats: dict = {}
                    for tid in team_ids:
                        try:
                            raw = query.get_team_roster_player_stats_by_week(tid, wk)
                            if isinstance(raw, list):
                                player_list = [_to_dict(item) for item in raw]
                            else:
                                converted = _convert_to_dict(raw)
                                if isinstance(converted, list):
                                    player_list = [_to_dict(item) for item in converted]
                                elif isinstance(converted, dict):
                                    inner = converted.get("players", [])
                                    player_list = [_to_dict(item) for item in (inner if isinstance(inner, list) else list(inner.values()) if isinstance(inner, dict) else [])]
                                else:
                                    player_list = []

                            for p in player_list:
                                if not isinstance(p, dict): continue
                                pk = p.get("player_key")
                                if not pk: continue
                                stats = _extract_stats(p)
                                if stats["fantasy_points"] > 0 or stats["stats"]:
                                    week_stats[pk] = stats

                            time.sleep(0.2)
                        except Exception:
                            continue

                    yr_stats[week_key] = week_stats

                existing[yr] = yr_stats
                results["success"].append(int(yr))

            except Exception as e:
                results["failed"][yr] = str(e)

        sorted_data = _year_sort(existing)
        _write_json(path, sorted_data)
        return {
            "status": "complete", "seasons_updated": results["success"],
            "seasons_skipped": results["skipped"], "seasons_failed": results["failed"],
            "total_seasons": len(sorted_data), "file_written": path,
            "note": "Join with player_info.json on player_key for name/position/nfl_team",
            "next_step": "GET /league/data/player-stats/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data/player-stats/status")
def player_stats_status():
    """Shows which years and weeks are in player_stats.json."""
    try:
        data = _load_json(_get_data_path("player_stats.json"))
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            weeks = data[yr]
            total_player_weeks = sum(len(w) for w in weeks.values())
            summary.append({
                "year":               int(yr),
                "weeks_built":        len(weeks),
                "total_player_weeks": total_player_weeks,
            })
        return {"total_seasons": len(data), "seasons": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/player-stats/download")
def download_player_stats(year: str = Query(default=None, description="Limit to one year — files can be large")):
    """Returns current player_stats.json for local save. Use ?year= to limit size."""
    try:
        data = _load_json(_get_data_path("player_stats.json"))
        if not data:
            raise HTTPException(status_code=404, detail="player_stats.json not found. Run build-all first.")
        if year:
            if year not in data:
                raise HTTPException(status_code=404, detail=f"Year {year} not found.")
            return {"year": int(year), "data": {year: data[year]}}
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Data generation — rules.json
# ===========================================================================

@router.get("/data/rules/build-all")
def build_rules(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None),
    year_from: int     = Query(default=None),
    year_to: int       = Query(default=None),
    force_clean: bool  = Query(default=False),
):
    """
    Generates rules.json — league settings and scoring rules per season.

    Combines two sections from get_league_settings():
      stat_categories  — stat_id, name, abbr, position_type, enabled
      stat_modifiers   — stat_id, value (points per unit of that stat)

    Joined on stat_id so each entry has both name AND point value:
        {"stat_id": 4, "name": "Passing Yards", "abbr": "Pass Yds",
         "points_per_unit": 0.04, "enabled": true}

    Also captures: draft_type, roster_positions, playoff settings, FAAB budget.

    Shape: {"2025": {"year": N, "draft_type": "auction", "stat_categories": [...], ...}}

    Usage:
        GET /league/data/rules/build-all?year=2025
        GET /league/data/rules/build-all?year_from=2007&year_to=2010
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict,
        )
        from services.yahoo_service import get_query

        path     = _get_data_path("rules.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])

        if year:
            target_years = [year]
        elif year_from or year_to:
            lo = int(year_from) if year_from else 2007
            hi = int(year_to)   if year_to   else 2025
            target_years = [y for y in all_years if lo <= int(y) <= hi]
        else:
            target_years = all_years

        results = {"success": [], "skipped": [], "failed": {}}

        def _to_dict(obj):
            if isinstance(obj, dict): return obj
            try: return _convert_to_dict(obj)
            except Exception: return {}

        def _norm_list(raw) -> list:
            """Normalise a YFPY list/dict/object to a flat list."""
            if isinstance(raw, list): return raw
            if isinstance(raw, dict):
                if all(str(k).isdigit() for k in raw.keys()):
                    return [raw[k] for k in sorted(raw, key=lambda x: int(x))]
                return list(raw.values())
            return []

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)
                s          = _to_dict(_convert_to_dict(query.get_league_settings()))

                # ── stat_categories ──────────────────────────────────────────
                sc_raw = s.get("stat_categories") or {}
                if isinstance(sc_raw, dict):
                    sc_raw = sc_raw.get("stats", []) or _norm_list(sc_raw)
                sc_list = _norm_list(sc_raw)

                stat_map: dict = {}   # stat_id → category entry
                for sc in sc_list:
                    sc = _to_dict(sc)
                    stat = sc.get("stat", sc)
                    stat = _to_dict(stat)
                    sid = stat.get("stat_id")
                    if sid is None: continue
                    stat_map[str(sid)] = {
                        "stat_id":      sid,
                        "name":         stat.get("name") or stat.get("display_name") or "",
                        "abbr":         stat.get("abbr") or stat.get("abbreviation") or "",
                        "sort_order":   int(stat.get("sort_order") or 1),
                        "position_type":stat.get("position_type") or "",
                        "enabled":      bool(int(stat.get("enabled") or 0)),
                        "is_only_display_stat": bool(int(stat.get("is_only_display_stat") or 0)),
                        "points_per_unit": None,  # filled in from stat_modifiers below
                    }

                # ── stat_modifiers (POINT VALUES) ─────────────────────────────
                sm_raw = s.get("stat_modifiers") or {}
                if isinstance(sm_raw, dict):
                    sm_raw = sm_raw.get("stats", []) or _norm_list(sm_raw)
                sm_list = _norm_list(sm_raw)

                for sm in sm_list:
                    sm = _to_dict(sm)
                    stat = sm.get("stat", sm)
                    stat = _to_dict(stat)
                    sid = stat.get("stat_id")
                    val = stat.get("value")
                    if sid is None or val is None: continue
                    try:
                        fval = float(val)
                    except (TypeError, ValueError):
                        continue
                    key = str(sid)
                    if key in stat_map:
                        stat_map[key]["points_per_unit"] = fval
                    else:
                        # modifier for a stat not in stat_categories
                        stat_map[key] = {
                            "stat_id":         sid,
                            "name":            "",
                            "abbr":            "",
                            "sort_order":      99,
                            "position_type":   "",
                            "enabled":         True,
                            "is_only_display_stat": False,
                            "points_per_unit": fval,
                        }

                # Sorted stat list — scoring stats first, then display-only
                stat_categories = sorted(
                    stat_map.values(),
                    key=lambda x: (
                        0 if x["points_per_unit"] is not None else 1,
                        x["sort_order"],
                    ),
                )

                # ── roster_positions ──────────────────────────────────────────
                rp_raw  = s.get("roster_positions") or {}
                if isinstance(rp_raw, dict):
                    rp_raw = rp_raw.get("roster_positions", []) or _norm_list(rp_raw)
                rp_list = _norm_list(rp_raw)

                roster_positions = []
                for rp in rp_list:
                    rp = _to_dict(rp)
                    pos = rp.get("roster_position", rp)
                    pos = _to_dict(pos)
                    abbr = pos.get("position") or pos.get("abbreviation")
                    if abbr:
                        roster_positions.append({
                            "position":    abbr,
                            "count":       int(pos.get("count") or pos.get("position_count") or 1),
                            "is_starting": bool(int(pos.get("is_starting_position") or 0)),
                        })

                existing[yr] = {
                    "year":               int(yr),
                    "league_key":         league_key,
                    "draft_type":         "auction" if bool(int(s.get("is_auction_draft") or 0)) else "snake",
                    "num_teams":          int(s.get("num_teams") or s.get("max_teams") or 10),
                    "playoff_teams":      int(s.get("num_playoff_teams") or 4),
                    "playoff_start_week": int(s.get("playoff_start_week") or 15),
                    "end_week":           int(s.get("end_week") or 17),
                    "uses_faab":          bool(int(s.get("uses_faab") or 0)),
                    "faab_budget":        int(s.get("faab_budget") or 100) if bool(int(s.get("uses_faab") or 0)) else None,
                    "waiver_type":        s.get("waiver_type"),
                    "trade_deadline":     s.get("trade_end_date"),
                    "scoring_type":       s.get("scoring_type") or "head",
                    "roster_positions":   roster_positions,
                    "stat_categories":    stat_categories,
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
            "next_step":       "GET /league/data/rules/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/rules/status")
def rules_status():
    """Shows which years are in rules.json and whether stat_modifiers are populated."""
    try:
        data = _load_json(_get_data_path("rules.json"))
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            s           = data[yr]
            cats        = s.get("stat_categories", [])
            with_points = sum(1 for c in cats if c.get("points_per_unit") is not None)
            summary.append({
                "year":               int(yr),
                "draft_type":         s.get("draft_type"),
                "stat_count":         len(cats),
                "scoring_stats":      with_points,
                "uses_faab":          s.get("uses_faab"),
                "modifiers_populated":with_points > 0,
            })
        return {"total_seasons": len(data), "seasons": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/rules/download")
def download_rules():
    """Returns current rules.json for local save."""
    try:
        data = _load_json(_get_data_path("rules.json"))
        if not data:
            raise HTTPException(status_code=404, detail="rules.json not found. Run build-all first.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Debug — roster / player API shapes
# ===========================================================================

@router.get("/data/debug/api-shapes")
def debug_api_shapes(year: str = Query(default="2025")):
    """
    Comprehensive debug endpoint — tests every API call used by rosters,
    player_info, and player_stats builds and shows exactly what YFPY returns.

    Run this before rebuilding those files to diagnose empty results.

    Usage: GET /league/data/debug/api-shapes?year=2025
    """
    try:
        from services.fantasy.league_service import get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query

        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)
        report     = {"year": year, "league_key": league_key, "tests": {}}

        def _safe(label: str, fn):
            """Run fn(), capture result shape and any error."""
            try:
                raw       = fn()
                converted = _convert_to_dict(raw)
                is_list   = isinstance(converted, list)
                is_dict   = isinstance(converted, dict)
                top_keys  = list(converted.keys())[:8] if is_dict else []
                length    = len(converted) if hasattr(converted, "__len__") else None
                preview   = str(converted)[:400]
                report["tests"][label] = {
                    "status":    "ok",
                    "raw_type":  type(raw).__name__,
                    "conv_type": type(converted).__name__,
                    "is_list":   is_list,
                    "length":    length,
                    "top_keys":  top_keys,
                    "preview":   preview,
                }
                return converted
            except Exception as e:
                report["tests"][label] = {"status": "error", "error": str(e)[:200]}
                return None

        # 1 — get_league_teams: needed to find team_keys for roster calls
        teams_raw = _safe("get_league_teams", lambda: query.get_league_teams())

        # Extract first team_key to use for roster test
        first_team_key = None
        first_team_id  = None
        if teams_raw:
            if isinstance(teams_raw, list) and teams_raw:
                t = teams_raw[0]
                t = t.get("team", t) if isinstance(t, dict) else {}
                first_team_key = t.get("team_key") or (t.get("_extracted_data") or {}).get("team_key")
            elif isinstance(teams_raw, dict):
                for v in teams_raw.values():
                    if isinstance(v, dict):
                        t = v.get("team", v)
                        first_team_key = (t or {}).get("team_key") or (
                            (t or {}).get("_extracted_data") or {}
                        ).get("team_key")
                        if first_team_key:
                            break

        if first_team_key and ".t." in str(first_team_key):
            first_team_id = str(first_team_key).split(".t.")[-1]

        report["tests"]["_extracted_team_key"] = first_team_key
        report["tests"]["_extracted_team_id"]  = first_team_id

        # 2 — get_team_roster_by_week with team_id (numeric)
        if first_team_id:
            roster_by_id = _safe(
                f"get_team_roster_by_week(team_id={first_team_id}, week=1)",
                lambda: query.get_team_roster_by_week(first_team_id, 1),
            )
        else:
            report["tests"]["get_team_roster_by_week"] = {"status": "skipped", "reason": "no team_id found"}

        # 3 — get_team_roster_by_week with full team_key (to compare)
        if first_team_key:
            _safe(
                f"get_team_roster_by_week(team_key={first_team_key}, week=1)",
                lambda: query.get_team_roster_by_week(first_team_key, 1),
            )

        # 4 — get_league_players page 0
        _safe("get_league_players(start=0, count=25)",
              lambda: query.get_league_players(player_count=25, player_start=0))

        # 5 — try alternate player list method names
        for method_name in ["get_league_players_available", "get_league_free_agents"]:
            method = getattr(query, method_name, None)
            if method:
                _safe(f"{method_name}(start=0, count=25)",
                      lambda m=method: m(player_count=25, player_start=0))
            else:
                report["tests"][method_name] = {"status": "method_not_found"}

        # 6 — get a specific player's stats for week 1 (use first rostered player)
        first_player_key = None
        if first_team_id:
            try:
                roster_conv = _convert_to_dict(query.get_team_roster_by_week(first_team_id, 1))
                if isinstance(roster_conv, list) and roster_conv:
                    p0 = roster_conv[0]
                    p0 = p0.get("player", p0) if isinstance(p0, dict) else {}
                    first_player_key = p0.get("player_key") or (
                        p0.get("_extracted_data") or {}
                    ).get("player_key")
                elif isinstance(roster_conv, dict):
                    players = roster_conv.get("players", [])
                    if isinstance(players, list) and players:
                        p0 = players[0]
                        p0 = p0.get("player", p0) if isinstance(p0, dict) else {}
                        first_player_key = p0.get("player_key") or (
                            p0.get("_extracted_data") or {}
                        ).get("player_key")
            except Exception as e:
                report["tests"]["_roster_player_key_extraction"] = {"error": str(e)[:120]}

        report["tests"]["_extracted_player_key"] = first_player_key

        if first_player_key:
            _safe(
                f"get_player_stats_by_week(player_key={first_player_key}, week=1)",
                lambda: query.get_player_stats_by_week(first_player_key, 1),
            )
            _safe(
                f"get_player(player_key={first_player_key})",
                lambda: query.get_player(first_player_key),
            )
        else:
            report["tests"]["get_player_stats_by_week"] = {
                "status": "skipped", "reason": "could not extract player_key from roster"
            }

        # 7 — list all available methods on the query object
        all_methods = [m for m in dir(query) if not m.startswith("_") and "player" in m.lower()]
        report["available_player_methods"] = all_methods
        roster_methods = [m for m in dir(query) if not m.startswith("_") and "roster" in m.lower()]
        report["available_roster_methods"] = roster_methods

        return report

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/debug/player-info-raw")
def debug_player_info_raw(
    year: str = Query(default="2025"),
    count: int = Query(default=3),
):
    """
    Discovers the correct YFPY v17 method and signature for fetching players.
    Tries every known variant and shows the raw response shape.

    Usage: GET /league/data/debug/player-info-raw?year=2025
    """
    try:
        from services.fantasy.league_service import get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query
        import inspect

        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)

        # 1. Show all player-related methods and their signatures
        player_methods = {}
        for m in sorted(dir(query)):
            if m.startswith("_"): continue
            if any(word in m.lower() for word in ["player", "roster", "free", "waiver"]):
                try:
                    sig = str(inspect.signature(getattr(query, m)))
                    player_methods[m] = sig
                except Exception:
                    player_methods[m] = "(signature unavailable)"

        result = {"year": year, "player_and_roster_methods": player_methods, "attempts": {}}

        # 2. Try every plausible call variant for get_league_players
        attempts = [
            ("get_league_players()",
             lambda: query.get_league_players()),
            ("get_league_players(0, 25)",
             lambda: query.get_league_players(0, 25)),
            ("get_league_players(25, 0)",
             lambda: query.get_league_players(25, 0)),
            ("get_league_free_agents()",
             lambda: query.get_league_free_agents() if hasattr(query, "get_league_free_agents") else None),
        ]

        for label, fn in attempts:
            try:
                raw  = fn()
                if raw is None:
                    result["attempts"][label] = "method does not exist"
                    continue
                conv = _convert_to_dict(raw)

                # Summarise shape
                if isinstance(conv, list):
                    shape = f"list[{len(conv)}]"
                    sample = conv[0] if conv else None
                elif isinstance(conv, dict):
                    shape = f"dict — keys: {list(conv.keys())[:8]}"
                    # Find first list value as likely players list
                    sample = None
                    for v in conv.values():
                        if isinstance(v, list) and v:
                            sample = v[0]; break
                    if not sample: sample = conv
                else:
                    shape = str(type(conv))
                    sample = None

                # Inspect sample
                sample_summary = {}
                if isinstance(sample, dict):
                    sample_summary["top_keys_no_underscore"] = [k for k in sample.keys() if not k.startswith("_")][:15]
                    ed = sample.get("_extracted_data", {})
                    sample_summary["_extracted_data_keys"] = list(ed.keys()) if isinstance(ed, dict) else None
                    # Key field values
                    for f in ["player_key", "player_id", "full_name", "name", "display_position", "editorial_team_abbr"]:
                        v = sample.get(f)
                        if v is not None:
                            sample_summary[f"top.{f}"] = repr(v)[:60]
                    if isinstance(ed, dict):
                        for f in ["player_key", "player_id", "name", "display_position"]:
                            v = ed.get(f)
                            if v is not None:
                                sample_summary[f"ed.{f}"] = repr(v)[:60]

                result["attempts"][label] = {
                    "status":         "ok",
                    "raw_type":       type(raw).__name__,
                    "converted_shape":shape,
                    "sample_summary": sample_summary,
                    "sample_full":    sample,
                }
            except Exception as e:
                result["attempts"][label] = {"status": "error", "error": str(e)[:200]}

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/debug/player-stats-raw")
def debug_player_stats_raw(
    year: str       = Query(default="2025"),
    player_key: str = Query(default="461.p.32723", description="Player key to test with"),
    week: int       = Query(default=1),
):
    """
    Discovers the correct YFPY v17 method and signature for fetching player stats.
    Shows raw response shape including where fantasy points and stat lines are nested.

    Usage: GET /league/data/debug/player-stats-raw?year=2025&player_key=461.p.32723&week=1
    """
    try:
        from services.fantasy.league_service import get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query
        import inspect

        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)

        # 1. All stat-related method signatures
        stat_methods = {}
        for m in sorted(dir(query)):
            if m.startswith("_"): continue
            if any(word in m.lower() for word in ["stat", "point", "score", "player"]):
                try:
                    sig = str(inspect.signature(getattr(query, m)))
                    stat_methods[m] = sig
                except Exception:
                    stat_methods[m] = "(signature unavailable)"

        result = {
            "year": year, "player_key": player_key, "week": week,
            "stat_methods": stat_methods,
            "attempts": {},
        }

        # 2. Try every plausible call for player stats
        attempts = [
            ("get_player_stats_by_week(player_key, week)",
             lambda: query.get_player_stats_by_week(player_key, week)),
            ("get_player_stats_by_week(player_key, str(week))",
             lambda: query.get_player_stats_by_week(player_key, str(week))),
            ("get_player(player_key)",
             lambda: query.get_player(player_key) if hasattr(query, "get_player") else None),
            ("get_player_ownership(player_key)",
             lambda: query.get_player_ownership(player_key) if hasattr(query, "get_player_ownership") else None),
        ]

        for label, fn in attempts:
            try:
                raw = fn()
                if raw is None:
                    result["attempts"][label] = "method does not exist"
                    continue
                conv = _convert_to_dict(raw)

                # Find where stats/points are nested
                stats_path  = None
                points_path = None

                def _search(obj, path=""):
                    nonlocal stats_path, points_path
                    if not isinstance(obj, dict): return
                    if "stats" in obj and stats_path is None:
                        stats_path = path + ".stats"
                    if "player_points" in obj and points_path is None:
                        points_path = path + ".player_points"
                    if "player_stats" in obj and stats_path is None:
                        stats_path = path + ".player_stats"
                    for k, v in obj.items():
                        if isinstance(v, (dict, list)):
                            _search(v if isinstance(v, dict) else (v[0] if v else {}),
                                    path + f".{k}")

                _search(conv if isinstance(conv, dict) else {})

                top_keys = list(conv.keys())[:15] if isinstance(conv, dict) else str(type(conv))
                ed       = conv.get("_extracted_data", {}) if isinstance(conv, dict) else {}

                result["attempts"][label] = {
                    "status":        "ok",
                    "raw_type":      type(raw).__name__,
                    "conv_type":     type(conv).__name__,
                    "top_keys":      top_keys,
                    "ed_keys":       list(ed.keys()) if isinstance(ed, dict) else None,
                    "stats_at":      stats_path,
                    "points_at":     points_path,
                    "full_response": conv,
                }
            except Exception as e:
                result["attempts"][label] = {"status": "error", "error": str(e)[:200]}

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Data generation — drafts.json
# ===========================================================================

@router.get("/data/drafts/build-all")
def build_drafts(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None, description="Single year e.g. '2025'"),
    year_from: int     = Query(default=None, description="Start of year range e.g. 2007"),
    year_to: int       = Query(default=None, description="End of year range e.g. 2010"),
    force_clean: bool  = Query(default=False),
):
    """
    Generates drafts.json — full draft board per season.

    ⚠️  Build in batches of 4-5 years to avoid Render's 30s timeout:
        ?year_from=2007&year_to=2010
        ?year_from=2011&year_to=2014  etc.

    CONFIRMED field locations (top level after per-item _convert_to_dict):
      pick, round, cost, team_key, player_key
    Player names enriched from player_info.json — run /drafts/enrich after building.

    Snake drafts: cost = null. Auction drafts (2023+): cost = dollars bid.

    Shape: {"2025": {"draft_type": "auction", "total_picks": 160, "picks": [...]}}
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict,
        )
        from services.yahoo_service import get_query
        from config import get_manager_identity

        path     = _get_data_path("drafts.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])

        if year:
            target_years = [year]
        elif year_from or year_to:
            lo = int(year_from) if year_from else 2007
            hi = int(year_to)   if year_to   else 2025
            target_years = [y for y in all_years if lo <= int(y) <= hi]
        else:
            target_years = all_years

        results = {"success": [], "skipped": [], "failed": {}}

        def _to_dict(obj):
            """Convert a YFPY DraftResult object or dict to a plain dict."""
            if isinstance(obj, dict): return obj
            try: return _convert_to_dict(obj)
            except Exception: return {}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                # Draft type from settings
                try:
                    settings  = _to_dict(_convert_to_dict(query.get_league_settings()))
                    is_auction = bool(int(settings.get("is_auction_draft") or 0))
                    draft_type = "auction" if is_auction else "snake"
                    num_teams  = int(settings.get("num_teams") or 10)
                except Exception:
                    draft_type, is_auction, num_teams = "unknown", False, 10

                # Get raw picks — may be a list of DraftResult objects OR dicts
                raw = query.get_league_draft_results()

                # Normalise to a flat list regardless of YFPY return shape
                if isinstance(raw, list):
                    picks_raw = raw
                else:
                    converted = _convert_to_dict(raw)
                    if isinstance(converted, list):
                        picks_raw = converted
                    elif isinstance(converted, dict):
                        # Named key, numbered key, or values
                        picks_raw = (
                            converted.get("draft_results") or
                            converted.get("picks") or
                            ([converted[k] for k in sorted(converted, key=lambda x: int(x))]
                             if all(str(k).isdigit() for k in converted) else None) or
                            [v for v in converted.values()
                             if isinstance(v, dict) and ("player_key" in v or "team_key" in v)]
                        )
                        if not isinstance(picks_raw, list):
                            picks_raw = []
                    else:
                        picks_raw = []

                # Load player_info for enrichment — keyed by string year "2025"
                player_info_data = _load_json(_get_data_path("player_info.json"))
                season_pi        = player_info_data.get(str(yr), {})
                player_lookup    = season_pi.get("players", {})

                picks = []
                for item in picks_raw:
                    # CRITICAL: convert each item individually — same fix as player_info
                    # _convert_to_dict on the outer list leaves DraftResult objects unconverted
                    p = _to_dict(item)

                    # Also handle {"draft_result": {...}} wrapper
                    if "draft_result" in p:
                        p = _to_dict(p["draft_result"])

                    team_key   = str(p.get("team_key")   or "")
                    player_key = str(p.get("player_key") or "")
                    if not team_key and not player_key:
                        continue

                    identity     = get_manager_identity(team_key=team_key)
                    manager_id   = identity["manager_id"]   if identity else None
                    display_name = identity["display_name"] if identity else team_key or "Unknown"

                    pick_num  = p.get("pick")
                    round_num = p.get("round")
                    cost      = p.get("cost")

                    try: pick_int  = int(pick_num)  if pick_num  is not None else None
                    except (TypeError, ValueError): pick_int = None

                    try:
                        round_int = int(round_num) if round_num is not None else None
                        if round_int is None and pick_int is not None:
                            round_int = ((pick_int - 1) // num_teams) + 1
                    except (TypeError, ValueError): round_int = None

                    try: cost_int = int(cost) if cost is not None else None
                    except (TypeError, ValueError): cost_int = None

                    # Enrich from player_info.json if available
                    pi           = player_lookup.get(player_key, {})
                    player_name  = pi.get("name")
                    position     = pi.get("position")
                    nfl_team     = pi.get("nfl_team")

                    picks.append({
                        "overall_pick": pick_int,
                        "round":        round_int,
                        "manager_id":   manager_id,
                        "display_name": display_name,
                        "team_key":     team_key,
                        "player_key":   player_key or None,
                        "player_name":  player_name,   # from player_info.json
                        "position":     position,       # from player_info.json
                        "nfl_team":     nfl_team,       # from player_info.json
                        "cost":         cost_int,       # null for snake drafts
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
            "note":            "player_name/position enriched from player_info.json if available",
            "next_step":       "GET /league/data/drafts/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/drafts/status")
def drafts_status():
    """Shows which years are in drafts.json and enrichment state."""
    try:
        data = _load_json(_get_data_path("drafts.json"))
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season     = data[yr]
            picks      = season.get("picks", [])
            with_names = sum(1 for p in picks if p.get("player_name"))
            summary.append({
                "year":             int(yr),
                "draft_type":       season.get("draft_type"),
                "total_picks":      len(picks),
                "picks_with_names": with_names,
                "enriched":         with_names == len(picks) and bool(picks),
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
            raise HTTPException(status_code=404, detail="drafts.json not found. Run build-all first.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/drafts/enrich")
def enrich_drafts(year: str = Query(default=None)):
    """
    Enriches drafts.json with player_name, position, nfl_team from player_info.json.

    Run this AFTER building both player_info.json and drafts.json in the same
    deploy session (before the next deploy wipes the files).

    Usage:
        GET /league/data/drafts/enrich             ← all years
        GET /league/data/drafts/enrich?year=2025   ← one year
    """
    try:
        import os
        drafts_path = _get_data_path("drafts.json")
        pi_path     = _get_data_path("player_info.json")

        if not os.path.exists(pi_path):
            raise HTTPException(
                status_code=400,
                detail="player_info.json not found. Run /league/data/player-info/build-all first."
            )
        if not os.path.exists(drafts_path):
            raise HTTPException(
                status_code=400,
                detail="drafts.json not found. Run /league/data/drafts/build-all first."
            )

        drafts_data = _load_json(drafts_path)
        pi_data     = _load_json(pi_path)

        target_years = [str(year)] if year else list(drafts_data.keys())
        enriched     = []
        skipped      = []
        total_picks_enriched = 0

        for yr in target_years:
            if yr not in drafts_data:
                skipped.append(yr)
                continue

            player_lookup = (pi_data.get(str(yr), {}) or {}).get("players", {})
            if not player_lookup:
                skipped.append(yr)
                continue

            picks = drafts_data[yr].get("picks", [])
            yr_enriched = 0
            for pick in picks:
                pk = pick.get("player_key")
                if not pk:
                    continue
                pi = player_lookup.get(pk, {})
                if pi:
                    pick["player_name"] = pi.get("name")
                    pick["position"]    = pi.get("position")
                    pick["nfl_team"]    = pi.get("nfl_team")
                    yr_enriched += 1

            total_picks_enriched += yr_enriched
            enriched.append({"year": int(yr), "picks_enriched": yr_enriched, "total_picks": len(picks)})

        _write_json(drafts_path, drafts_data)

        return {
            "status":              "complete",
            "years_enriched":      enriched,
            "years_skipped":       skipped,
            "total_picks_enriched":total_picks_enriched,
            "file_written":        drafts_path,
            "next_step":           "GET /league/data/drafts/download to save locally",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



def debug_draft_raw(year: str = Query(default="2025")):
    """Raw YFPY draft response — shows exact shape for diagnosing pick extraction."""
    try:
        from services.fantasy.league_service import get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query

        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)
        raw        = query.get_league_draft_results()
        converted  = _convert_to_dict(raw)

        # Show the shape of the first raw item vs first converted item
        first_raw  = raw[0] if isinstance(raw, list) and raw else None
        first_conv = None
        if isinstance(converted, list) and converted:
            item = converted[0]
            first_conv = _convert_to_dict(item) if not isinstance(item, dict) else item

        return {
            "raw_type":       type(raw).__name__,
            "raw_is_list":    isinstance(raw, list),
            "raw_len":        len(raw) if hasattr(raw, "__len__") else None,
            "conv_type":      type(converted).__name__,
            "conv_is_list":   isinstance(converted, list),
            "conv_len":       len(converted) if hasattr(converted, "__len__") else None,
            "first_raw_type": type(first_raw).__name__ if first_raw else None,
            "first_raw":      str(first_raw)[:300] if first_raw else None,
            "first_converted":first_conv,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Debug — draft enrichment + transaction player extraction
# ===========================================================================

@router.get("/data/debug/draft-enrichment")
def debug_draft_enrichment(year: str = Query(default="2025")):
    """
    Diagnoses why draft picks show null player_name/position/nfl_team.

    Shows:
    - Whether player_info.json exists and its exact structure
    - Whether the year key matches
    - Whether specific player_keys from the draft are found
    - The first 3 picks with their lookup results
    """
    try:
        from services.fantasy.league_service import get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query
        import os

        pi_path = _get_data_path("player_info.json")
        result  = {
            "year":               year,
            "player_info_path":   pi_path,
            "player_info_exists": os.path.exists(pi_path),
        }

        pi_data = _load_json(pi_path)
        result["player_info_top_keys"]   = list(pi_data.keys())[:10]
        result["year_key_str_exists"]    = str(year) in pi_data
        result["year_key_int_exists"]    = int(year) in pi_data if year.isdigit() else False

        season_pi = pi_data.get(str(year), pi_data.get(int(year) if year.isdigit() else year, {}))
        result["season_pi_keys"]         = list(season_pi.keys()) if isinstance(season_pi, dict) else type(season_pi).__name__
        result["total_players_field"]    = season_pi.get("total_players") if isinstance(season_pi, dict) else None

        players = season_pi.get("players", {}) if isinstance(season_pi, dict) else {}
        result["players_type"]           = type(players).__name__
        result["players_count"]          = len(players) if isinstance(players, dict) else 0
        result["sample_player_keys"]     = list(players.keys())[:5] if isinstance(players, dict) else []

        # Now get the actual draft picks and look them up
        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)
        raw        = query.get_league_draft_results()

        if isinstance(raw, list):
            picks_raw = raw
        else:
            converted = _convert_to_dict(raw)
            picks_raw = converted if isinstance(converted, list) else []

        def _to_dict(obj):
            if isinstance(obj, dict): return obj
            try: return _convert_to_dict(obj)
            except Exception: return {}

        pick_lookups = []
        for item in picks_raw[:5]:
            p  = _to_dict(item)
            if "draft_result" in p:
                p = _to_dict(p["draft_result"])
            pk   = str(p.get("player_key") or "")
            pi   = players.get(pk, {}) if isinstance(players, dict) else {}
            pick_lookups.append({
                "overall_pick": p.get("pick"),
                "player_key":   pk,
                "found_in_player_info": bool(pi),
                "player_name":  pi.get("name") if pi else None,
                "position":     pi.get("position") if pi else None,
                "raw_pick_type": type(item).__name__,
                "converted_keys": list(p.keys()) if p else [],
            })

        result["pick_lookups"] = pick_lookups
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/debug/transaction-player")
def debug_transaction_player(year: str = Query(default="2025")):
    """
    Diagnoses why transactions show 0 trades/moves.

    Shows exactly what each transaction item looks like after _convert_to_dict,
    what _norm_players produces, and what _extract_player returns — all on
    the first 3 live transactions.
    """
    try:
        from services.fantasy.league_service import get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query

        league_key = get_league_key_for_season(year)
        query      = get_query(league_key)

        raw       = query.get_league_transactions()
        converted = _convert_to_dict(raw)

        tx_list = converted if isinstance(converted, list) else []
        result  = {
            "year":            year,
            "raw_type":        type(raw).__name__,
            "converted_type":  type(converted).__name__,
            "total_items":     len(tx_list),
        }

        def _to_dict(obj):
            if isinstance(obj, dict): return obj
            try: return _convert_to_dict(obj)
            except Exception: return {}

        tx_details = []
        for item in tx_list[:3]:
            item_dict = _to_dict(item)
            ed        = item_dict.get("_extracted_data") or {}

            ttype  = item_dict.get("type")  or (ed.get("type")  if isinstance(ed, dict) else None) or ""
            status = item_dict.get("status") or (ed.get("status") if isinstance(ed, dict) else None) or ""

            # Raw players field
            players_raw  = item_dict.get("players")
            players_type = type(players_raw).__name__
            players_len  = len(players_raw) if hasattr(players_raw, "__len__") else "N/A"

            # What do individual player items look like before conversion?
            first_player_raw_type = None
            first_player_converted = None
            if isinstance(players_raw, list) and players_raw:
                fp = players_raw[0]
                first_player_raw_type = type(fp).__name__
                fp_dict = _to_dict(fp)
                first_player_converted = {
                    "keys_no_underscore": [k for k in fp_dict.keys() if not k.startswith("_")][:10],
                    "has_player_wrapper": "player" in fp_dict,
                    "player_key":         fp_dict.get("player_key"),
                    "full_name":          fp_dict.get("full_name"),
                }
                # Also check inside "player" wrapper
                if "player" in fp_dict:
                    inner = _to_dict(fp_dict["player"])
                    first_player_converted["inner_player_key"]  = inner.get("player_key")
                    first_player_converted["inner_full_name"]    = inner.get("full_name")
                    first_player_converted["inner_transaction_data"] = inner.get("transaction_data")

            elif isinstance(players_raw, dict):
                first_player_raw_type = "dict"
                fp_dict = _to_dict(players_raw.get("player", players_raw))
                first_player_converted = {
                    "keys": [k for k in fp_dict.keys() if not k.startswith("_")][:10],
                    "player_key": fp_dict.get("player_key"),
                }

            tx_details.append({
                "item_type":               type(item).__name__,
                "item_dict_keys":          [k for k in item_dict.keys() if not k.startswith("_")][:15],
                "type":                    ttype,
                "status":                  status,
                "status_check_passes":     status == "successful",
                "ttype_norm":              ttype.lower().replace(" ", "_"),
                "is_move":                 ttype.lower().replace(" ", "_") in ("add","drop","add/drop","waiver","free_agent"),
                "is_trade":                ttype.lower() == "trade",
                "players_field_type":      players_type,
                "players_field_len":       players_len,
                "first_player_raw_type":   first_player_raw_type,
                "first_player_converted":  first_player_converted,
            })

        result["transaction_details"] = tx_details
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# Data generation — matchups.json
# ===========================================================================

@router.get("/data/matchups/build-all")
def build_matchups(
    skip_existing: bool = Query(default=True),
    year: str          = Query(default=None),
    year_from: int     = Query(default=None),
    year_to: int       = Query(default=None),
    force_clean: bool  = Query(default=False),
):
    """
    Generates matchups.json — weekly scoreboard data per season.

    Fetches every week's scoreboard via get_league_scoreboard_by_week().
    Captures: week, dates, is_playoffs, is_consolation, is_tied,
              winner_team_key, and per-team points + projected points.

    Shape:
        {"2025": {"weeks": [
            {"week": 1, "week_start": "2025-09-04", "week_end": "2025-09-08",
             "matchups": [
               {"week": 1, "is_playoffs": false, "is_consolation": false,
                "is_tied": false, "winner_manager": "brian",
                "winner_display_name": "Brian",
                "teams": [
                  {"manager_id": "brian", "display_name": "Brian",
                   "team_key": "...", "team_name": "...",
                   "points": 125.4, "projected": 118.2, "is_winner": true},
                  ...
                ]}
             ]}
        ]}}

    Build one year at a time to avoid timeouts:
        GET /league/data/matchups/build-all?year=2025
        GET /league/data/matchups/build-all?year_from=2007&year_to=2010
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict,
        )
        from services.yahoo_service import get_query
        from config import get_manager_identity

        path     = _get_data_path("matchups.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])

        if year:
            target_years = [year]
        elif year_from or year_to:
            lo = int(year_from) if year_from else 2007
            hi = int(year_to)   if year_to   else 2025
            target_years = [y for y in all_years if lo <= int(y) <= hi]
        else:
            target_years = all_years

        results = {"success": [], "skipped": [], "failed": {}}

        def _to_dict(obj):
            if isinstance(obj, dict): return obj
            try: return _convert_to_dict(obj)
            except Exception: return {}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                settings_raw  = _to_dict(_convert_to_dict(query.get_league_settings()))
                start_week    = int(settings_raw.get("start_week")        or 1)
                end_week      = int(settings_raw.get("end_week")          or 17)
                playoff_start = int(settings_raw.get("playoff_start_week") or 15)

                season_weeks = []

                for wk in range(start_week, end_week + 1):
                    try:
                        sb_raw   = _to_dict(_convert_to_dict(query.get_league_scoreboard_by_week(wk)))
                        matchups_raw = sb_raw.get("matchups", []) if isinstance(sb_raw, dict) else \
                                       (sb_raw if isinstance(sb_raw, list) else [])

                        week_matchups = []
                        week_start    = None
                        week_end      = None

                        for m_wrap in matchups_raw:
                            m = m_wrap.get("matchup", m_wrap) if isinstance(m_wrap, dict) else {}
                            m = _to_dict(m)

                            # Confirmed fields from API extract
                            week_num      = m.get("week") or wk
                            week_start    = m.get("week_start")  or week_start
                            week_end      = m.get("week_end")    or week_end
                            is_playoffs   = bool(int(m.get("is_playoffs")   or 0))
                            is_consolation= bool(int(m.get("is_consolation") or 0))
                            is_tied       = bool(int(m.get("is_tied")       or 0))
                            winner_tk     = m.get("winner_team_key") or ""

                            teams_raw = m.get("teams", [])
                            if isinstance(teams_raw, dict):
                                teams_raw = list(teams_raw.values())

                            teams_out             = []
                            winner_manager        = None
                            winner_display_name   = None
                            loser_manager         = None
                            loser_display_name    = None

                            for tw in teams_raw:
                                tm = tw.get("team", tw) if isinstance(tw, dict) else {}
                                tm = _to_dict(tm)

                                tk   = tm.get("team_key", "")
                                name = tm.get("name", "")

                                pts_raw  = tm.get("team_points") or {}
                                proj_raw = tm.get("team_projected_points") or {}
                                pts  = float(pts_raw.get("total")  or tm.get("points")    or 0) if isinstance(pts_raw, dict)  else float(pts_raw or 0)
                                proj = float(proj_raw.get("total") or tm.get("projected") or 0) if isinstance(proj_raw, dict) else float(proj_raw or 0)

                                identity   = get_manager_identity(team_key=tk)
                                manager_id = identity["manager_id"]   if identity else tk
                                disp_name  = identity["display_name"] if identity else tk
                                is_winner  = (tk == winner_tk) and not is_tied

                                if is_winner:
                                    winner_manager      = manager_id
                                    winner_display_name = disp_name
                                elif not is_tied:
                                    loser_manager       = manager_id
                                    loser_display_name  = disp_name

                                teams_out.append({
                                    "manager_id":   manager_id,
                                    "display_name": disp_name,
                                    "team_key":     tk,
                                    "team_id":      tk.split(".t.")[-1] if ".t." in tk else None,
                                    "team_name":    name,
                                    "points":       round(pts,  2),
                                    "projected":    round(proj, 2),
                                    "is_winner":    is_winner,
                                })

                            week_matchups.append({
                                "week":                wk,
                                "week_start":          week_start,
                                "week_end":            week_end,
                                "is_playoffs":         is_playoffs,
                                "is_consolation":      is_consolation,
                                "is_tied":             is_tied,
                                "winner_manager":      winner_manager,
                                "winner_display_name": winner_display_name,
                                "loser_manager":       loser_manager,
                                "loser_display_name":  loser_display_name,
                                "teams":               teams_out,
                            })

                        season_weeks.append({
                            "week":       wk,
                            "week_start": week_start,
                            "week_end":   week_end,
                            "matchups":   week_matchups,
                        })

                    except Exception:
                        continue  # skip individual week errors

                existing[yr] = {
                    "year":          int(yr),
                    "total_weeks":   len(season_weeks),
                    "playoff_start": playoff_start,
                    "weeks":         season_weeks,
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
            "note":            "Each season makes end_week API calls (~17). Build one year at a time.",
            "next_step":       "GET /league/data/matchups/download to save locally",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/matchups/status")
def matchups_status():
    """Shows which years and weeks are in matchups.json."""
    try:
        data = _load_json(_get_data_path("matchups.json"))
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            s = data[yr]
            summary.append({
                "year":         int(yr),
                "total_weeks":  s.get("total_weeks", len(s.get("weeks", []))),
                "playoff_start":s.get("playoff_start"),
            })
        return {"total_seasons": len(data), "seasons": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/matchups/download")
def download_matchups():
    """Returns current matchups.json for local save."""
    try:
        data = _load_json(_get_data_path("matchups.json"))
        if not data:
            raise HTTPException(status_code=404, detail="matchups.json not found. Run build-all first.")
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
    """Commissioner/app owner — add or update punishment for a season."""
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
        data = _load_json(_get_data_path("punishment.json"))
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