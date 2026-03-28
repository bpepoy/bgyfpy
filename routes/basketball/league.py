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

# Known NBA Yahoo game_ids by display year (the season end year — e.g. 2025 = 2024-25 season)
# game_id is the prefix of the league_key: "466.l.38685"
# Update this dict each new season by checking the current league URL on Yahoo.
# NOTE: Yahoo's API returns season = start year (e.g. 2024 for the 2024-25 season),
#       but we key this dict by the end/display year for human readability.
NBA_GAME_IDS = {
    2025: 466,   # 2024-25 season — current
    2024: 454,   # 2023-24 season  (league_key confirmed: 454.l.2122 — diff league_id)
    # NOTE: Real Bros may have used a different league_id in earlier seasons.
    # Add confirmed keys here as they are discovered via /explore/discover-seasons.
    # Earlier seasons with league_id 38685:
    # 2024: 428 — this returned "Yahoo Public 38685", confirmed as Real Bros
}

# ---------------------------------------------------------------------------
# Manager identity — imported from config/basketball.py
# ---------------------------------------------------------------------------
# get_nba_manager_identity() and NBA_MANAGER_IDENTITY_MAP live in
# config/basketball.py — that file is the single source of truth.
# Edit manager GUIDs and team_keys there, not here.
# ---------------------------------------------------------------------------
try:
    from config.basketball import get_nba_manager_identity as _get_nba_manager_identity
except ImportError:
    import warnings
    warnings.warn(
        "Could not import get_nba_manager_identity from config.basketball. "
        "Manager IDs will fall back to team_key until the import is resolved.",
        stacklevel=2,
    )
    def _get_nba_manager_identity(guid: str | None = None, team_key: str | None = None) -> dict | None:
        return None


# NBA stat categories used in head-to-head scoring
# Stat IDs match Yahoo Fantasy API stat_categories ids
NBA_STAT_CATEGORIES = [
    {"id": "5",  "abbr": "FG%",  "name": "Field Goal Pct",   "lower_is_better": False},
    {"id": "8",  "abbr": "FT%",  "name": "Free Throw Pct",   "lower_is_better": False},
    {"id": "10", "abbr": "3PTM", "name": "3-Pointers Made",  "lower_is_better": False},
    {"id": "12", "abbr": "PTS",  "name": "Points",           "lower_is_better": False},
    {"id": "15", "abbr": "REB",  "name": "Rebounds",         "lower_is_better": False},
    {"id": "16", "abbr": "AST",  "name": "Assists",          "lower_is_better": False},
    {"id": "17", "abbr": "ST",   "name": "Steals",           "lower_is_better": False},
    {"id": "18", "abbr": "BLK",  "name": "Blocks",           "lower_is_better": False},
    {"id": "19", "abbr": "TO",   "name": "Turnovers",        "lower_is_better": True},
]
NBA_STAT_ABBRS = [s["abbr"] for s in NBA_STAT_CATEGORIES]


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


def _get_first_team_key(query, league_key: str) -> str | None:
    """
    Retrieve the team_key of the first team in the league.

    Tries multiple extraction paths because YFPY wraps teams differently
    depending on which endpoint and version is used:
      - list of {"team": {...}} wrappers
      - list of flat team dicts
      - dict with "teams" key
      - numbered dict {"0": team, "1": team, ...}

    Falls back to constructing t.1 from the league_key if all else fails,
    since t.1 always exists in a 12-team league.
    """
    from services.fantasy.league_service import _convert_to_dict
    try:
        raw        = query.get_league_teams()
        teams_dict = _convert_to_dict(raw)

        # Unwrap outer container
        if isinstance(teams_dict, dict):
            candidates = teams_dict.get("teams") or list(teams_dict.values())
        elif isinstance(teams_dict, list):
            candidates = teams_dict
        else:
            candidates = []

        # Numbered dict {"0": team, ...} — flatten values
        if isinstance(candidates, dict):
            candidates = list(candidates.values())

        for item in candidates:
            if not isinstance(item, dict):
                continue
            # Try both wrapped {"team": {...}} and flat
            team = item.get("team", item)
            if isinstance(team, dict):
                tk = team.get("team_key") or team.get("key")
                if tk and ".t." in str(tk):
                    return str(tk)
            # Numbered inner dict
            if isinstance(item, dict) and not item.get("team"):
                for v in item.values():
                    if isinstance(v, dict):
                        tk = v.get("team_key") or v.get("key")
                        if tk and ".t." in str(tk):
                            return str(tk)
    except Exception:
        pass

    # Hard fallback — construct t.1 from league_key (e.g. "466.l.38685" → "466.l.38685.t.1")
    if league_key and ".l." in league_key:
        return f"{league_key}.t.1"
    return None


def _team_id_from_key(team_key: str) -> str:
    """
    Extract the numeric team_id from a full team_key.
    "466.l.38685.t.5" → "5"
    If already numeric, return as-is.
    """
    if team_key and ".t." in team_key:
        return team_key.split(".t.")[-1]
    return team_key



def _get_all_nba_season_keys() -> dict:
    """
    Returns a dict of {display_year_str: league_key} for all known NBA seasons.

    Resolution order:
      1. data/basketball/season_keys.json — written by /explore/discover-seasons
      2. NBA_GAME_IDS fallback — constructs keys as "{game_id}.l.{NBA_LEAGUE_ID}"

    Running /explore/discover-seasons is optional — it just confirms which keys
    are valid and saves them for faster lookups. All build-all endpoints work
    without it as long as NBA_GAME_IDS contains the relevant seasons.
    """
    import os

    cache_path = _get_data_path("season_keys.json")
    if os.path.exists(cache_path):
        cached = _load_json(cache_path)
        if cached:
            return cached

    # Fallback: construct keys from NBA_GAME_IDS so build-all works without
    # ever needing to run discover-seasons
    return {
        str(yr): f"{game_id}.l.{NBA_LEAGUE_ID}"
        for yr, game_id in NBA_GAME_IDS.items()
    }


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
    Validates which Real Bros NBA season keys are confirmed accessible, and saves
    results to data/basketball/season_keys.json.

    This endpoint is OPTIONAL — all build-all endpoints work without it by falling
    back to NBA_GAME_IDS. Run discover-seasons only when:
      - Bootstrapping a fresh deployment (confirms which keys are valid)
      - Adding a new season (update NBA_GAME_IDS first, then re-run)
      - Diagnosing why a season key isn't working

    Verification: a season is confirmed only if the API returns league_id == NBA_LEAGUE_ID.

    Usage:
        GET /basketball/league/explore/discover-seasons
        GET /basketball/league/explore/discover-seasons?save=false  (dry run)
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        found   = {}
        details = []

        for display_year, game_id in sorted(NBA_GAME_IDS.items(), reverse=True):
            league_key = f"{game_id}.l.{NBA_LEAGUE_ID}"
            try:
                query = get_query(league_key)
                meta  = _convert_to_dict(query.get_league_metadata())

                returned_lid = str(meta.get("league_id") or "")
                league_name  = meta.get("name") or ""
                api_season   = meta.get("season")      # start year from Yahoo
                num_teams    = meta.get("num_teams")
                is_finished  = meta.get("is_finished")
                renew        = meta.get("renew")
                renewed      = meta.get("renewed")

                # Strict match: returned league_id must equal our known league_id
                if returned_lid == NBA_LEAGUE_ID:
                    found[str(display_year)] = league_key
                    details.append({
                        "display_year": display_year,
                        "league_key":   league_key,
                        "status":       "✅ confirmed",
                        "league_name":  league_name,
                        "api_season":   api_season,
                        "num_teams":    num_teams,
                        "is_finished":  is_finished,
                        "renew":        renew,
                        "renewed":      renewed,
                    })
                else:
                    # API responded but it's a different league sharing the same league_id slot
                    details.append({
                        "display_year":       display_year,
                        "league_key":         league_key,
                        "status":             "⚠️ different league — league_id mismatch",
                        "returned_league_id": returned_lid,
                        "returned_name":      league_name,
                        "note": (
                            "Yahoo reused this league_id for a different league under "
                            f"game_id {game_id}. Not our league."
                        ),
                    })

            except Exception as e:
                err_str = str(e)
                # Distinguish "league doesn't exist" (404/access denied) from real errors
                is_not_found = any(x in err_str for x in ("404", "access", "denied", "URL", "retrieve"))
                details.append({
                    "display_year": display_year,
                    "league_key":   league_key,
                    "status":       "⛔ not found" if is_not_found else f"❌ error: {err_str[:100]}",
                })

        if save and found:
            _write_json(_get_data_path("season_keys.json"), found)

        return {
            "league_id":          NBA_LEAGUE_ID,
            "seasons_found":      len(found),
            "season_keys":        found,
            "game_ids_tested":    dict(sorted(NBA_GAME_IDS.items(), reverse=True)),
            "details":            details,
            "saved":              save and bool(found),
            "note": (
                "Only seasons where the API returned league_id == '38685' are saved. "
                "If a known season is missing, add its game_id to NBA_GAME_IDS in basketball/league.py "
                "and re-run this endpoint."
            ),
            "next_step": "Run GET /basketball/league/explore/season/{year} to inspect any confirmed season.",
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


@router.get("/explore/scoreboard-week")
def explore_nba_scoreboard_week(
    year: str = Query(default="2025"),
    week: int = Query(default=1, description="Week number to inspect"),
):
    """
    Returns the full scoreboard for one week — shows per-team category stat totals
    and how Yahoo structures category-scoring matchups.

    This is the primary source for:
      - Per-matchup category winners (FG%, PTS, REB, AST, ST, BLK, TO, 3PTM, FT%)
      - Weekly team stat totals per category
      - is_playoffs / is_consolation flags per matchup

    Usage:
        GET /basketball/league/explore/scoreboard-week?year=2025&week=1
        GET /basketball/league/explore/scoreboard-week?year=2025&week=21
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        league_key = _league_key_for_season(year)
        query      = get_query(league_key)
        sb         = _convert_to_dict(query.get_league_scoreboard_by_week(week))

        # Surface the first matchup and its two teams fully for inspection
        matchups = sb.get("matchups", []) if isinstance(sb, dict) else (sb if isinstance(sb, list) else [])
        first_m  = matchups[0] if matchups else {}
        matchup  = first_m.get("matchup", first_m) if isinstance(first_m, dict) else {}
        teams_m  = matchup.get("teams", [])
        if isinstance(teams_m, dict):
            teams_m = list(teams_m.values())

        return {
            "year":              year,
            "week":              week,
            "league_key":        league_key,
            "num_matchups":      len(matchups),
            "raw_scoreboard":    sb,
            "first_matchup":     matchup,
            "first_matchup_team_0": teams_m[0] if len(teams_m) > 0 else None,
            "first_matchup_team_1": teams_m[1] if len(teams_m) > 1 else None,
            "note": (
                "Look at first_matchup_team_0/1 → team_stats → stats for category values. "
                "stat_winners shows which team won each category for this matchup."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/team-matchups")
def explore_nba_team_matchups(
    year: str      = Query(default="2025"),
    team_key: str  = Query(default=None, description="e.g. 466.l.38685.t.5 — omit to use first team"),
):
    """
    Returns all matchups for a single team across the full season.
    Shows week-by-week results including category breakdowns per matchup.

    This is the source for:
      - Full season schedule (opponent, week, result)
      - Whether each week was regular season, playoffs, or consolation
      - Per-week category win/loss detail at the matchup level

    Usage:
        GET /basketball/league/explore/team-matchups?year=2025
        GET /basketball/league/explore/team-matchups?year=2025&team_key=466.l.38685.t.5
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        from services.fantasy.team_service import _extract_teams_list

        league_key = _league_key_for_season(year)
        query      = get_query(league_key)

        if not team_key:
            team_key = _get_first_team_key(query, league_key)

        team_id      = _team_id_from_key(team_key)
        matchups_raw = _convert_to_dict(query.get_team_matchups(team_id))

        return {
            "year":        year,
            "team_key":    team_key,
            "team_id":     team_id,
            "league_key":  league_key,
            "raw":         matchups_raw,
            "note": (
                "Each matchup entry shows week, opponent, is_playoffs, is_consolation, "
                "winner_team_key, and team stat totals for both sides. "
                "stat_winners per matchup shows which team won each category."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/team-stats-week")
def explore_nba_team_stats_week(
    year: str     = Query(default="2025"),
    week: int     = Query(default=1),
    team_key: str = Query(default=None, description="e.g. 466.l.38685.t.5 — omit to use first team"),
):
    """
    Returns a team's category stat totals for one week.
    This is the per-team, per-week data that drives category W-L-T in results.json.

    Shows the raw stat values (FG%, PTS, REB, AST, ST, BLK, TO, 3PTM, FT%) that
    are compared head-to-head to determine category winners.

    Usage:
        GET /basketball/league/explore/team-stats-week?year=2025&week=5
        GET /basketball/league/explore/team-stats-week?year=2025&week=5&team_key=466.l.38685.t.5
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        from services.fantasy.team_service import _extract_teams_list

        league_key = _league_key_for_season(year)
        query      = get_query(league_key)

        if not team_key:
            team_key = _get_first_team_key(query, league_key)

        # YFPY get_team_stats_by_week expects the short numeric team_id, not the full key
        team_id = _team_id_from_key(team_key)

        results = {
            "year": year, "week": week,
            "team_key": team_key, "team_id": team_id, "league_key": league_key,
        }

        # Path A — get_team_stats_by_week (may return raw category values)
        try:
            stats_raw = _convert_to_dict(query.get_team_stats_by_week(team_id, week))
            results["stats_by_week_raw"]       = stats_raw
            results["stats_by_week_extracted"] = _extract_team_category_stats(
                stats_raw if isinstance(stats_raw, dict) else {}
            )
        except Exception as e:
            results["stats_by_week_error"] = str(e)[:200]

        # Path B — get_team_matchups (alternative; includes per-week category breakdown)
        try:
            matchups_raw  = _convert_to_dict(query.get_team_matchups(team_id))
            matchups_list = matchups_raw if isinstance(matchups_raw, list) else \
                            matchups_raw.get("matchups", []) if isinstance(matchups_raw, dict) else []
            # Find the matchup for the requested week
            week_matchup = None
            for m in matchups_list:
                mw = m.get("matchup", m) if isinstance(m, dict) else {}
                if int(mw.get("week") or 0) == week:
                    week_matchup = mw
                    break
            results["team_matchups_week_entry"] = week_matchup
            results["team_matchups_total"]      = len(matchups_list)
            results["team_matchups_sample"]     = matchups_list[:1] if matchups_list else []
        except Exception as e:
            results["team_matchups_error"] = str(e)[:200]

        results["note"] = (
            "YFPY passes team_id (numeric) not full team_key to stat endpoints. "
            "stats_by_week_raw → look for stat values nested under team_stats or stats. "
            "team_matchups_week_entry → alternative source; may include stat_winners per category. "
            "If both are empty, raw category values may only be available via individual player stats."
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/team-roster-week")
def explore_nba_team_roster_week(
    year: str     = Query(default="2025"),
    week: int     = Query(default=1),
    team_key: str = Query(default=None, description="e.g. 466.l.38685.t.5 — omit to use first team"),
):
    """
    Returns a team's roster for one week — which players were on the roster,
    their positions, and whether they were started or on the bench.

    This is the source for rosters.json (weekly lineup by player_key + slot).

    Usage:
        GET /basketball/league/explore/team-roster-week?year=2025&week=1
        GET /basketball/league/explore/team-roster-week?year=2025&week=10&team_key=466.l.38685.t.5
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        from services.fantasy.team_service import _extract_teams_list

        league_key = _league_key_for_season(year)
        query      = get_query(league_key)

        if not team_key:
            team_key = _get_first_team_key(query, league_key)

        team_id    = _team_id_from_key(team_key)
        roster_raw = _convert_to_dict(query.get_team_roster_by_week(team_id, week))

        return {
            "year":       year,
            "week":       week,
            "team_key":   team_key,
            "team_id":    team_id,
            "league_key": league_key,
            "raw":        roster_raw,
            "note": (
                "Each player entry has: player_key, name, display_position, "
                "selected_position (PG/SG/BN/IL etc.), and is_starting. "
                "Use this to build rosters.json."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/player-stats")
def explore_nba_player_stats(
    year: str        = Query(default="2025"),
    player_key: str  = Query(default=None, description="e.g. 466.p.4725 — omit to use first rostered player"),
    week: int        = Query(default=None, description="Specific week, or omit for season totals"),
):
    """
    Returns stat lines for a single player — either for one week or season totals.
    This is the source for player_stats.json.

    If player_key is omitted, fetches the first player from the first team's roster.

    Usage:
        GET /basketball/league/explore/player-stats?year=2025&player_key=466.p.4725
        GET /basketball/league/explore/player-stats?year=2025&player_key=466.p.4725&week=5
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        from services.fantasy.team_service import _extract_teams_list

        league_key = _league_key_for_season(year)
        query      = get_query(league_key)

        # Discover a player_key if none provided
        if not player_key:
            team_key = _get_first_team_key(query, league_key)
            if team_key:
                try:
                    roster_raw  = _convert_to_dict(query.get_team_roster_by_week(team_key, 1))
                    players_raw = roster_raw if isinstance(roster_raw, list) else \
                                  roster_raw.get("players", []) if isinstance(roster_raw, dict) else []
                    if players_raw:
                        first_p    = players_raw[0]
                        first_p    = first_p.get("player", first_p) if isinstance(first_p, dict) else {}
                        player_key = first_p.get("player_key")
                except Exception:
                    pass

        if not player_key:
            return {"error": "Could not determine a player_key to fetch. Pass ?player_key= explicitly."}

        results = {"year": year, "player_key": player_key, "league_key": league_key}

        # Season totals
        try:
            results["season_stats"] = _convert_to_dict(
                query.get_player_stats_for_a_league(player_key, "season_stats")
            )
        except Exception as e:
            results["season_stats"] = {"error": str(e)[:150]}

        # Week-specific stats
        if week:
            try:
                results[f"week_{week}_stats"] = _convert_to_dict(
                    query.get_player_stats_by_week(player_key, week)
                )
            except Exception as e:
                results[f"week_{week}_stats"] = {"error": str(e)[:150]}

        # Player info
        try:
            results["player_info"] = _convert_to_dict(query.get_player(player_key))
        except Exception as e:
            results["player_info"] = {"error": str(e)[:150]}

        results["note"] = (
            "season_stats → per-category totals for the whole season. "
            "week_N_stats → per-category totals for that scoring week. "
            "Look for stat_id values 5 (FG%), 8 (FT%), 10 (3PTM), 12 (PTS), "
            "15 (REB), 16 (AST), 17 (ST), 18 (BLK), 19 (TO)."
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/league-players")
def explore_nba_league_players(
    year: str = Query(default="2025"),
    count: int = Query(default=25, description="Number of players to fetch (max 25 per API call)"),
    start: int = Query(default=0,  description="Pagination offset"),
):
    """
    Returns the list of available players for the league — name, position, team,
    player_key. Used to build player_info.json.

    Yahoo paginates players in batches of 25. Use start= to page through.

    Usage:
        GET /basketball/league/explore/league-players?year=2025
        GET /basketball/league/explore/league-players?year=2025&start=25
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        league_key = _league_key_for_season(year)
        query      = get_query(league_key)

        results = {}

        # Try several YFPY player-list methods
        for label, fetcher in [
            ("players_raw",       lambda: query.get_league_players(player_count=count, player_start=start)),
            ("players_available", lambda: query.get_league_players_available(player_count=count, player_start=start)),
        ]:
            try:
                results[label] = _convert_to_dict(fetcher())
            except Exception as e:
                results[label] = {"error": str(e)[:150]}

        results["pagination"] = {"start": start, "count": count, "next_start": start + count}
        results["note"] = (
            "player_key is the stable identifier for player_info.json and player_stats.json. "
            "Page through with start=0, 25, 50... to collect all players."
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/matchup-category-detail")
def explore_nba_matchup_category_detail(
    year: str      = Query(default="2025"),
    week: int      = Query(default=1),
    team_key: str  = Query(default=None, description="One team in the matchup — omit to use first team"),
):
    """
    Deep-dives a single matchup to show exactly how Yahoo reports category winners.

    Combines:
      - scoreboard for the week (category totals + stat_winners)
      - team_stats for both teams that week
      - team_matchups for the specified team (full season schedule)

    This is the definitive diagnostic for the categories-all-zeros bug in results.json.

    Usage:
        GET /basketball/league/explore/matchup-category-detail?year=2025&week=5
        GET /basketball/league/explore/matchup-category-detail?year=2025&week=5&team_key=466.l.38685.t.5
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        from services.fantasy.team_service import _extract_teams_list

        league_key = _league_key_for_season(year)
        query      = get_query(league_key)

        if not team_key:
            team_key = _get_first_team_key(query, league_key)

        # YFPY stat/matchup endpoints want the numeric id, not the full qualified key
        team_id = _team_id_from_key(team_key)

        result = {
            "year": year, "week": week,
            "team_key": team_key, "team_id": team_id, "league_key": league_key,
        }

        # 1. Scoreboard for this week — shows all matchups + category totals
        try:
            sb = _convert_to_dict(query.get_league_scoreboard_by_week(week))
            matchups = sb.get("matchups", []) if isinstance(sb, dict) else \
                       (sb if isinstance(sb, list) else [])

            # Find the matchup involving our team
            our_matchup = None
            for m in matchups:
                matchup = m.get("matchup", m) if isinstance(m, dict) else {}
                teams_m = matchup.get("teams", [])
                if isinstance(teams_m, dict):
                    teams_m = list(teams_m.values())
                for tw in teams_m:
                    tm = tw.get("team", tw) if isinstance(tw, dict) else {}
                    if tm.get("team_key") == team_key:
                        our_matchup = matchup
                        break
                if our_matchup:
                    break

            result["scoreboard_our_matchup"] = our_matchup
            result["scoreboard_all_matchups_count"] = len(matchups)

            # Show full structure of first matchup team for path diagnosis
            if our_matchup:
                teams_m = our_matchup.get("teams", [])
                if isinstance(teams_m, dict):
                    teams_m = list(teams_m.values())
                if teams_m:
                    tm0 = teams_m[0].get("team", teams_m[0]) if isinstance(teams_m[0], dict) else {}
                    result["team_obj_keys"]         = list(tm0.keys())
                    result["team_stats_value"]      = tm0.get("team_stats")
                    result["team_points_value"]     = tm0.get("team_points")
                    result["stat_winners_value"]    = our_matchup.get("stat_winners")
                    result["extracted_stats_team0"] = _extract_team_category_stats(tm0)

        except Exception as e:
            result["scoreboard_error"] = str(e)

        # 2. Direct team stats for this week (pass numeric team_id)
        try:
            result["team_stats_direct"] = _convert_to_dict(
                query.get_team_stats_by_week(team_id, week)
            )
        except Exception as e:
            result["team_stats_direct_error"] = str(e)

        # 3. Team matchups — pass numeric team_id; may include per-category breakdown
        try:
            tm_raw = _convert_to_dict(query.get_team_matchups(team_id))
            matchups_list = tm_raw if isinstance(tm_raw, list) else \
                            tm_raw.get("matchups", []) if isinstance(tm_raw, dict) else []
            # Find this week's entry
            week_entry = next(
                (m.get("matchup", m) for m in matchups_list
                 if isinstance(m, dict) and int((m.get("matchup", m) or {}).get("week") or 0) == week),
                None
            )
            result["team_matchups_count"]        = len(matchups_list)
            result["team_matchups_this_week"]    = week_entry
            result["team_matchups_week_sample"]  = matchups_list[:1] if matchups_list else []
        except Exception as e:
            result["team_matchups_error"] = str(e)

        result["diagnosis_note"] = (
            "KEY FIELDS TO CHECK:\n"
            "1. team_stats_value — if None/empty, Yahoo puts stats elsewhere on the scoreboard team object\n"
            "2. stat_winners_value — Yahoo may provide pre-computed category winners per matchup\n"
            "3. extracted_stats_team0 — what _extract_team_category_stats() currently pulls (all None = path wrong)\n"
            "4. team_stats_direct — stats from get_team_stats_by_week() directly (may have different shape)\n"
            "If stat_winners_value is populated, we can use it directly instead of computing from raw values."
        )

        return result
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
        # season_keys always populated from NBA_GAME_IDS fallback if cache missing

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

                    logos    = t.get("team_logos", {})
                    if isinstance(logos, list): logos = logos[0] if logos else {}
                    logo_obj = logos.get("team_logo", {}) if isinstance(logos, dict) else {}
                    if isinstance(logo_obj, list): logo_obj = logo_obj[0] if logo_obj else {}
                    team_logo = logo_obj.get("url") if isinstance(logo_obj, dict) else None

                    # Normalize managers list — a team can have 1 primary + N co-managers
                    managers_raw = t.get("managers", {})
                    if isinstance(managers_raw, list):
                        mgr_wrappers = managers_raw
                    elif isinstance(managers_raw, dict):
                        # May be a single {"manager": {...}} or numbered {"0": ..., "1": ...}
                        if "manager" in managers_raw:
                            mgr_wrappers = [managers_raw]
                        else:
                            mgr_wrappers = list(managers_raw.values())
                    else:
                        mgr_wrappers = []

                    for mgr_wrapper in mgr_wrappers:
                        mgr = mgr_wrapper.get("manager", mgr_wrapper) if isinstance(mgr_wrapper, dict) else {}
                        if not mgr:
                            continue

                        guid         = mgr.get("guid")
                        nickname     = mgr.get("nickname")
                        is_comanager = bool(int(mgr.get("is_comanager", 0) or 0))

                        identity     = _get_nba_manager_identity(manager_guid=guid)
                        manager_id   = identity["manager_id"]   if identity else None
                        display_name = identity["display_name"] if identity else nickname or "Unknown"

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

def _empty_cat_accumulators() -> dict:
    """
    Zero-filled per-category accumulator for one team's season bucket.
    Fields: wins/losses/ties, score_for_sum, score_against_sum, score_weeks.
    """
    return {
        abbr: {
            "wins": 0, "losses": 0, "ties": 0,
            "score_for_sum": 0.0,
            "score_against_sum": 0.0,
            "score_weeks": 0,
        }
        for abbr in NBA_STAT_ABBRS
    }


def _extract_team_category_stats(team_obj: dict) -> dict:
    """
    Diagnostic helper used by explore/debug endpoints.
    Extracts {stat_id_str: float} from a team object's team_stats.stats[].
    Reads from _extracted_data.value for correct ratio stat values.
    NOTE: The results build pipeline uses _extract_stats_from_team_matchup instead.
    """
    return _extract_stats_from_team_matchup(team_obj) if team_obj else {}



def _yfpy_stat_value(stat_obj: dict) -> float | None:
    """
    Extract the correct numeric value from a YFPY stat entry.

    YFPY sets top-level 'value' to 0 for ratio stats (FG%, FT%) and
    string fractions ("205/429") for made/attempted composites.
    The _extracted_data copy always has the real computed value.

    Priority: _extracted_data.value → top-level value (if numeric and non-zero)
    Skips stat_ids 9004003 (FGM/A) and 9007006 (FTM/A) — display-only composites.
    """
    if not isinstance(stat_obj, dict):
        return None
    extracted = stat_obj.get("_extracted_data", {})
    # Try _extracted_data first (most reliable)
    val = extracted.get("value") if isinstance(extracted, dict) else None
    if val is None:
        val = stat_obj.get("value")
    # Skip string fractions (FGM/A display stat)
    if isinstance(val, str):
        return None
    try:
        f = float(val)
        return f if f != 0.0 or isinstance(val, (int, float)) else None
    except (TypeError, ValueError):
        return None


def _extract_stats_from_team_matchup(team_obj: dict) -> dict:
    """
    Extract {stat_id_str: float} from a team object inside a get_team_matchups response.

    The team object here (from _extracted_data) has team_stats.stats[] where
    each stat entry has _extracted_data.value = real float/int.

    Skip composite display stats 9004003 (FGM/A) and 9007006 (FTM/A).
    """
    SKIP_STAT_IDS = {"9004003", "9007006"}
    stats_out = {}

    team_stats = team_obj.get("team_stats") or {}
    if isinstance(team_stats, dict):
        stats_raw = team_stats.get("stats", [])
    else:
        return stats_out

    if isinstance(stats_raw, dict):
        stats_raw = list(stats_raw.values())

    for entry in (stats_raw or []):
        stat = entry.get("stat", entry) if isinstance(entry, dict) else {}
        sid  = str(stat.get("stat_id") or "")
        if not sid or sid in SKIP_STAT_IDS:
            continue
        val = _yfpy_stat_value(stat)
        if val is not None:
            stats_out[sid] = val

    return stats_out


def _build_nba_results_for_season(yr: str, query, league_key: str) -> dict:
    """
    Build per-manager results for one NBA season using get_team_matchups().

    Data source
    -----------
    get_team_matchups(team_id) returns all matchups for a team, each containing:
      - stat_winners[]: [{stat_winner: {stat_id, winner_team_key}}] — Yahoo's
        pre-computed per-category winner. Used directly for W-L-T.
      - teams[]: both team objects with team_stats.stats[] — raw category values
        (FG%=0.478, PTS=590 etc.) read from _extracted_data.value.
      - is_playoffs, is_consolation, winner_team_key, is_tied — for bucketing.

    This replaces the old scoreboard loop which only returned category *counts*
    (team_points.total = categories won), not raw stat values.

    Output shape per manager (keyed by manager_id or team_key fallback)
    -------------------------------------------------------------------
    {
      "team_name": str,
      "logo_url":  str | null,
      "regular_season": {
        "wins": int, "losses": int, "ties": int, "games": int, "win_pct": float,
        "rank": int, "playoff_seed": int,
        "categories": {
          "FG%": {
            "wins": int, "losses": int, "ties": int, "games": int, "win_pct": float,
            "avg_score_for": float, "avg_score_against": float,
            "wins_rank": int, "avg_score_for_rank": int, "avg_score_against_rank": int
          }, ...9 categories total
        },
        "category_wins_total": int, "category_losses_total": int, "category_ties_total": int
      },
      "playoffs": {
        "made_playoffs": bool,
        "finish": int | null,
        "wins": int, "losses": int, "ties": int, "games": int, "win_pct": float,
        "categories": { ...same shape... },
        "category_wins_total": int, "category_losses_total": int, "category_ties_total": int
      }
    }
    """
    from services.fantasy.league_service import _convert_to_dict
    from services.fantasy.team_service import (
        _extract_teams_list, _extract_team_standings, _extract_outcome_totals,
    )

    # Stat_id → abbr lookup
    stat_id_to_abbr = {s["id"]: s["abbr"] for s in NBA_STAT_CATEGORIES}

    # ------------------------------------------------------------------
    # Step 1 — Standings: overall W-L-T, rank, seed, identity, logo
    # ------------------------------------------------------------------
    standings_dict = _convert_to_dict(query.get_league_standings())
    teams_list     = _extract_teams_list(standings_dict)

    season_data: dict[str, dict] = {}
    team_key_to_manager: dict[str, str] = {}

    for t in teams_list:
        if not isinstance(t, dict):
            continue
        team_key = t.get("team_key", "")
        ts = _extract_team_standings(t)
        ot = _extract_outcome_totals(ts)

        # Primary manager guid (skip co-managers)
        managers_raw = t.get("managers", {})
        mgr_wrappers = managers_raw if isinstance(managers_raw, list) else \
                       ([managers_raw] if isinstance(managers_raw, dict) and "manager" in managers_raw
                        else list(managers_raw.values()) if isinstance(managers_raw, dict) else [])
        primary_mgr = {}
        for mw in mgr_wrappers:
            m = mw.get("manager", mw) if isinstance(mw, dict) else {}
            if not bool(int(m.get("is_comanager", 0) or 0)):
                primary_mgr = m
                break
        if not primary_mgr and mgr_wrappers:
            first = mgr_wrappers[0]
            primary_mgr = first.get("manager", first) if isinstance(first, dict) else {}

        guid       = primary_mgr.get("guid")
        identity   = _get_nba_manager_identity(manager_guid=guid)
        manager_id = identity["manager_id"] if identity else team_key

        logos    = t.get("team_logos", {})
        if isinstance(logos, list): logos = logos[0] if logos else {}
        logo_obj = logos.get("team_logo", {}) if isinstance(logos, dict) else {}
        if isinstance(logo_obj, list): logo_obj = logo_obj[0] if logo_obj else {}
        team_logo = logo_obj.get("url") if isinstance(logo_obj, dict) else None

        wins   = int(ot.get("wins")   or 0)
        losses = int(ot.get("losses") or 0)
        ties   = int(ot.get("ties")   or 0)
        games  = wins + losses + ties

        try:
            rank = int(ts.get("rank") or 0) or None
            seed = int(ts.get("playoff_seed") or 0) or None
        except (TypeError, ValueError):
            rank = seed = None

        team_key_to_manager[team_key] = manager_id
        season_data[manager_id] = {
            "team_name":  t.get("name"),
            "logo_url":   team_logo,
            "_team_key":  team_key,
            "_team_id":   _team_id_from_key(team_key),
            "_rs": {
                "wins": wins, "losses": losses, "ties": ties, "games": games,
                "rank": rank, "seed": seed,
                "cats": _empty_cat_accumulators(),
            },
            "_pl": {
                "wins": 0, "losses": 0, "ties": 0, "games": 0,
                "cats": _empty_cat_accumulators(),
            },
        }

    # ------------------------------------------------------------------
    # Step 2 — Per-team matchup loop using get_team_matchups(team_id)
    # ------------------------------------------------------------------
    # We call get_team_matchups once per team. Each matchup entry has:
    #   stat_winners[] → Yahoo pre-computed per-category winner
    #   teams[]        → both teams with team_stats for raw values
    # We only process the "my side" of each matchup to avoid double-counting.
    # ------------------------------------------------------------------
    try:
        settings_dict = _convert_to_dict(query.get_league_settings())
        playoff_start = int(settings_dict.get("playoff_start_week") or 20)
    except Exception:
        playoff_start = 20

    for manager_id, d in season_data.items():
        team_id  = d["_team_id"]
        my_tk    = d["_team_key"]
        seed_val = d["_rs"].get("seed")
        try:
            my_seed = int(seed_val or 99)
        except (TypeError, ValueError):
            my_seed = 99

        try:
            matchups_raw  = _convert_to_dict(query.get_team_matchups(team_id))
            matchups_list = matchups_raw if isinstance(matchups_raw, list) else \
                            matchups_raw.get("matchups", []) if isinstance(matchups_raw, dict) else []
        except Exception:
            continue

        for item in matchups_list:
            # Unwrap _extracted_data wrapper on the matchup object
            m_raw  = item if isinstance(item, dict) else {}
            m_data = m_raw.get("_extracted_data", m_raw) if "_extracted_data" in m_raw else m_raw
            # Merge: _extracted_data fields + top-level (top-level wins for non-meta fields)
            matchup = {**m_data}
            for k, v in m_raw.items():
                if k not in ("_extracted_data", "_index", "_keys"):
                    matchup[k] = v

            week           = int(matchup.get("week") or 0)
            is_playoffs    = bool(int(matchup.get("is_playoffs",   0) or 0))
            is_consolation = bool(int(matchup.get("is_consolation",0) or 0))
            is_tied        = bool(int(matchup.get("is_tied",       0) or 0))
            winner_tk      = matchup.get("winner_team_key") or ""

            # Bucket: true playoff = seed ≤6 + is_playoffs + not consolation
            is_true_playoff = is_playoffs and not is_consolation and my_seed <= 6
            bucket = "_pl" if is_true_playoff else "_rs"
            b      = d[bucket]

            # Overall matchup W-L-T — playoffs only (RS comes from standings)
            if is_true_playoff:
                b["games"] += 1
                if is_tied:             b["ties"]   += 1
                elif winner_tk == my_tk: b["wins"]   += 1
                else:                   b["losses"] += 1

            # ----------------------------------------------------------
            # Per-category W-L-T using stat_winners (Yahoo pre-computed)
            # ----------------------------------------------------------
            stat_winners_raw = matchup.get("stat_winners", [])
            if isinstance(stat_winners_raw, dict):
                stat_winners_raw = list(stat_winners_raw.values())

            # Build set of stat_ids this team won
            cat_wins_set  = set()
            cat_has_entry = set()  # all stat_ids with a winner entry

            for sw_item in (stat_winners_raw or []):
                sw = sw_item.get("stat_winner", sw_item) if isinstance(sw_item, dict) else {}
                sid        = str(sw.get("stat_id") or "")
                winner_key = sw.get("winner_team_key") or ""
                abbr       = stat_id_to_abbr.get(sid)
                if not abbr:
                    continue
                cat_has_entry.add(abbr)
                if winner_key == my_tk:
                    cat_wins_set.add(abbr)

            # ----------------------------------------------------------
            # Raw stat values from team_stats for average calculations
            # ----------------------------------------------------------
            teams_in_matchup = matchup.get("teams", [])
            if isinstance(teams_in_matchup, dict):
                teams_in_matchup = list(teams_in_matchup.values())

            my_stats  = {}
            opp_stats = {}
            for tw in teams_in_matchup:
                tm_raw  = tw.get("team", tw) if isinstance(tw, dict) else {}
                # Prefer _extracted_data version (has correct values)
                tm_data = tm_raw.get("_extracted_data", tm_raw) \
                          if "_extracted_data" in tm_raw else tm_raw
                tk = tm_data.get("team_key") or tm_raw.get("team_key", "")
                stats = _extract_stats_from_team_matchup(tm_data)
                if tk == my_tk:
                    my_stats = stats
                else:
                    opp_stats = stats

            # ----------------------------------------------------------
            # Accumulate per-category stats
            # ----------------------------------------------------------
            for cat in NBA_STAT_CATEGORIES:
                abbr = cat["abbr"]
                sid  = cat["id"]

                # W-L-T from stat_winners
                if abbr in cat_has_entry:
                    if abbr in cat_wins_set:
                        b["cats"][abbr]["wins"] += 1
                    elif is_tied:
                        b["cats"][abbr]["ties"] += 1
                    else:
                        # Not in wins set and not tied → loss
                        # Check if this is actually a tie (both teams tied = no winner)
                        # Yahoo omits stat_winner entry when tied on a category
                        b["cats"][abbr]["losses"] += 1
                elif cat_has_entry:
                    # stat_winners had entries for other cats but not this one → tied
                    b["cats"][abbr]["ties"] += 1

                # Averages — only when both teams have the stat value
                my_val  = my_stats.get(sid)
                opp_val = opp_stats.get(sid)
                if my_val is not None and opp_val is not None:
                    b["cats"][abbr]["score_for_sum"]     += my_val
                    b["cats"][abbr]["score_against_sum"] += opp_val
                    b["cats"][abbr]["score_weeks"]       += 1

    # ------------------------------------------------------------------
    # Step 3 — Cross-manager per-category rank maps
    # ------------------------------------------------------------------
    def _avg_for(d: dict, bucket: str, abbr: str) -> float:
        c = d[bucket]["cats"][abbr]
        return round(c["score_for_sum"] / c["score_weeks"], 4) if c["score_weeks"] else 0.0

    def _avg_against(d: dict, bucket: str, abbr: str) -> float:
        c = d[bucket]["cats"][abbr]
        return round(c["score_against_sum"] / c["score_weeks"], 4) if c["score_weeks"] else 0.0

    def _per_cat_ranks(bucket: str) -> dict:
        ranks = {}
        for cat in NBA_STAT_CATEGORIES:
            abbr  = cat["abbr"]
            lower = cat["lower_is_better"]

            wins_sorted = sorted(
                season_data.items(),
                key=lambda kv: (
                    kv[1][bucket]["cats"][abbr]["wins"],
                    -_avg_for(kv[1], bucket, abbr) if lower else _avg_for(kv[1], bucket, abbr),
                ),
                reverse=True,
            )
            wins_rank = {mid: i + 1 for i, (mid, _) in enumerate(wins_sorted)}

            asfr_sorted = sorted(
                season_data.items(),
                key=lambda kv: _avg_for(kv[1], bucket, abbr),
                reverse=not lower,
            )
            asfr_rank = {mid: i + 1 for i, (mid, _) in enumerate(asfr_sorted)}

            asar_sorted = sorted(
                season_data.items(),
                key=lambda kv: _avg_against(kv[1], bucket, abbr),
                reverse=lower,
            )
            asar_rank = {mid: i + 1 for i, (mid, _) in enumerate(asar_sorted)}

            ranks[abbr] = {
                "wins_rank":              wins_rank,
                "avg_score_for_rank":     asfr_rank,
                "avg_score_against_rank": asar_rank,
            }
        return ranks

    rs_cat_ranks = _per_cat_ranks("_rs")
    pl_cat_ranks = _per_cat_ranks("_pl")

    # ------------------------------------------------------------------
    # Step 4 — Assemble final output
    # ------------------------------------------------------------------
    def _cat_block(cats_acc: dict, cat_ranks: dict, mid: str) -> dict:
        out = {}
        for abbr, c in cats_acc.items():
            g   = c["wins"] + c["losses"] + c["ties"]
            w   = c["score_weeks"]
            cr  = cat_ranks.get(abbr, {})
            out[abbr] = {
                "wins":                   c["wins"],
                "losses":                 c["losses"],
                "ties":                   c["ties"],
                "games":                  g,
                "win_pct":                round(c["wins"] / g, 4) if g else None,
                "avg_score_for":          round(c["score_for_sum"]     / w, 4) if w else None,
                "avg_score_against":      round(c["score_against_sum"] / w, 4) if w else None,
                "wins_rank":              cr.get("wins_rank",              {}).get(mid),
                "avg_score_for_rank":     cr.get("avg_score_for_rank",     {}).get(mid),
                "avg_score_against_rank": cr.get("avg_score_against_rank", {}).get(mid),
            }
        return out

    for mid, d in season_data.items():
        rs      = d["_rs"]
        pl      = d["_pl"]
        g_rs    = rs["games"]
        g_pl    = pl["games"]
        rs_cats = rs["cats"]
        pl_cats = pl["cats"]

        d["regular_season"] = {
            "wins":         rs["wins"],
            "losses":       rs["losses"],
            "ties":         rs["ties"],
            "games":        g_rs,
            "win_pct":      round(rs["wins"] / g_rs, 4) if g_rs else None,
            "rank":         rs["rank"],
            "playoff_seed": rs["seed"],
            "categories":              _cat_block(rs_cats, rs_cat_ranks, mid),
            "category_wins_total":     sum(c["wins"]   for c in rs_cats.values()),
            "category_losses_total":   sum(c["losses"] for c in rs_cats.values()),
            "category_ties_total":     sum(c["ties"]   for c in rs_cats.values()),
        }

        seed_int = rs["seed"] or 99
        try:
            seed_int = int(seed_int)
        except (TypeError, ValueError):
            seed_int = 99

        is_playoff_team = seed_int <= 6

        if is_playoff_team and g_pl > 0:
            d["playoffs"] = {
                "made_playoffs": True,
                "finish":  rs["rank"],
                "wins":    pl["wins"],
                "losses":  pl["losses"],
                "ties":    pl["ties"],
                "games":   g_pl,
                "win_pct": round(pl["wins"] / g_pl, 4) if g_pl else None,
                "categories":            _cat_block(pl_cats, pl_cat_ranks, mid),
                "category_wins_total":   sum(c["wins"]   for c in pl_cats.values()),
                "category_losses_total": sum(c["losses"] for c in pl_cats.values()),
                "category_ties_total":   sum(c["ties"]   for c in pl_cats.values()),
            }
        else:
            d["playoffs"] = {"made_playoffs": False}

        del d["_rs"], d["_pl"], d["_team_key"], d["_team_id"]

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

        # season_keys always populated from NBA_GAME_IDS fallback if cache missing

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
                existing[yr] = {
                    "season":      int(yr),
                    "is_finished": is_finished,
                    "managers":    season_data,
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
            "next_step":       "GET /basketball/league/data/results/download to save locally",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/results/status")
def nba_results_status():
    """Shows which years are in results.json and category enrichment state."""
    try:
        path = _get_data_path("results.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}
        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season   = data[yr]
            managers = season.get("managers", {})
            enriched = sum(
                1 for m in managers.values()
                if isinstance(m, dict) and m.get("regular_season", {}).get("categories")
            )
            summary.append({
                "year":          int(yr),
                "is_finished":   season.get("is_finished"),
                "num_managers":  len(managers),
                "cat_enriched":  enriched,
                "needs_refresh": enriched < len(managers),
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

@router.get("/data/results/debug-scoreboard")
def debug_nba_scoreboard(
    year: str = Query(default="2025"),
    week: int = Query(default=1, description="Week number to inspect"),
):
    """
    Returns the raw scoreboard response for one week, showing exactly how
    Yahoo structures the team stats for category leagues.

    Use this to diagnose why category stats are all zeros in results.json.

    Usage:
        GET /basketball/league/data/results/debug-scoreboard?year=2025&week=1
        GET /basketball/league/data/results/debug-scoreboard?year=2025&week=5
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        league_key = _league_key_for_season(year)
        query      = get_query(league_key)
        sb_raw     = query.get_league_scoreboard_by_week(week)
        sb_dict    = _convert_to_dict(sb_raw)

        # Pull first matchup and first team to show the full nested shape
        matchups = sb_dict.get("matchups", []) if isinstance(sb_dict, dict) else \
                   (sb_dict if isinstance(sb_dict, list) else [])

        first_matchup_raw = matchups[0] if matchups else None
        first_matchup     = first_matchup_raw.get("matchup", first_matchup_raw) \
                            if isinstance(first_matchup_raw, dict) else {}

        teams_m = first_matchup.get("teams", [])
        if isinstance(teams_m, dict):
            teams_m = list(teams_m.values())

        first_team_wrapper = teams_m[0] if teams_m else {}
        first_team         = first_team_wrapper.get("team", first_team_wrapper) \
                             if isinstance(first_team_wrapper, dict) else {}

        # Try to extract stats using our current function
        extracted_stats = _extract_team_category_stats(first_team)

        # Show all keys at each nesting level so we can trace the right path
        def _top_keys(obj, depth=2):
            if depth == 0 or not isinstance(obj, dict):
                return str(type(obj).__name__)
            return {k: _top_keys(v, depth - 1) for k, v in list(obj.items())[:10]}

        return {
            "year":              year,
            "week":              week,
            "league_key":        league_key,
            "scoreboard_top_keys":   list(sb_dict.keys()) if isinstance(sb_dict, dict) else str(type(sb_dict)),
            "num_matchups":          len(matchups),
            "first_matchup_keys":    list(first_matchup.keys()),
            "teams_type":            str(type(teams_m)),
            "num_teams_in_matchup":  len(teams_m),
            "first_team_wrapper_keys": list(first_team_wrapper.keys()) if isinstance(first_team_wrapper, dict) else [],
            "first_team_keys":       list(first_team.keys()),
            # The exact nested structure around team_stats
            "team_stats_raw":        first_team.get("team_stats"),
            "team_points_raw":       first_team.get("team_points"),
            # What our extractor currently pulls out (all zeros = path is wrong)
            "extracted_stats_by_stat_id": extracted_stats,
            # Full first team object for manual inspection (truncated)
            "first_team_full": _top_keys(first_team, depth=3),
            "note": (
                "If 'extracted_stats_by_stat_id' is empty or all None, "
                "the 'team_stats_raw' field above shows the actual path. "
                "Look for stat_id values 5,8,10,12,15,16,17,18,19 in there."
            ),
        }
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

        # season_keys always populated from NBA_GAME_IDS fallback if cache missing

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

        # season_keys always populated from NBA_GAME_IDS fallback if cache missing

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