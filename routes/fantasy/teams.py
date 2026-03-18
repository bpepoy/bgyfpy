"""
Teams Router
============
All endpoints use display_name (e.g. "Brian", "Zef") as the manager identifier.
Names are case-insensitive.

Call GET /teams/managers first to see all valid names.

Individual team endpoints:
  GET /teams/{name}/overview          Career summary across all seasons
  GET /teams/{name}/results           Combined record + points (all-time, last 5, per season)
  GET /teams/{name}/matchups          All-time H2H table vs every opponent
  GET /teams/{name}/transactions      Career trades, moves, and FAAB summary

League-wide endpoints:
  GET /teams/managers                 List all managers (use for dropdowns)
  GET /teams/all/records              All teams records for a season
  GET /teams/all/points               Points leaderboard for a season

Head-to-head:
  GET /teams/{name1}/vs/{name2}       H2H between two managers

All year params accept: "current" (default), specific year e.g. "2022", or "all" (H2H only).
"""

from fastapi import APIRouter, HTTPException, Query
from services.fantasy.team_service import (
    get_all_managers,
    get_team_overview,
    get_team_results,
    get_team_matchups,
    get_team_transactions,
    get_team_players,
    get_all_teams_records,
    get_all_teams_points,
    get_h2h_matchups,
    build_season_seed,
)

router = APIRouter(prefix="/teams", tags=["Teams"])


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

@router.get("/managers")
def list_managers():
    """
    List all managers from config.py with their display_name, seasons played,
    and whether they are active in the current season.

    Use this to get valid display_name values for all other /teams endpoints.

    Example:
        GET /teams/managers
    """
    try:
        return get_all_managers()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# League-wide comparison  (must be defined before /{name} routes)
# ---------------------------------------------------------------------------

@router.get("/all/records")
def all_teams_records(
    year: str = Query(default="current", description="Season year or 'current'"),
):
    """
    W-L-T records for every team in a season, sorted by final rank.

    Returns each team's wins, losses, ties, points for/against,
    rank, playoff seed, and display_name.

    Examples:
        GET /teams/all/records
        GET /teams/all/records?year=2019
    """
    try:
        return get_all_teams_records(year)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all/points")
def all_teams_points(
    year: str = Query(default="current", description="Season year or 'current'"),
):
    """
    Points leaderboard for all teams in a season, sorted by points scored.

    Examples:
        GET /teams/all/points
        GET /teams/all/points?year=2018
    """
    try:
        return get_all_teams_points(year)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Individual team endpoints
# ---------------------------------------------------------------------------

@router.get("/{name}/overview")
def team_overview(name: str):
    """
    Career summary for a manager across ALL seasons they've played.

    Returns:
      - Seasons played, championships, last-place finishes, playoff appearances
      - Career totals: wins, losses, ties, points for/against
      - Season-by-season history

    Args:
        name: Manager display name (e.g. "Brian", "Zef") — case-insensitive

    Examples:
        GET /teams/brian/overview
        GET /teams/Zef/overview
    """
    try:
        return get_team_overview(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/results")
def team_results(name: str):
    """
    Combined record + points summary for a manager across all BlackGold seasons.

    Returns two summary blocks (all-time and last 5 seasons) each containing:
      - record, win_pct, avg_finish
      - avg_points_per_game, avg_points_against_per_game, avg_points_rank

    Plus a per-season table with: year, team_name, effective_finish, record,
    win_pct, points_for, avg_points_per_game, avg_points_against_per_game, points_rank.

    Args:
        name: Manager display name — case-insensitive

    Examples:
        GET /teams/brian/results
        GET /teams/zef/results
    """
    try:
        return get_team_results(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/matchups")
def team_matchups(name: str):
    """
    All-time H2H matchup table vs every opponent across all BlackGold seasons.

    For each opponent returns:
      - Overall W-L-T record and games played
      - Average points for/against per game and point differential
      - Last 5 results as a list e.g. ["W","L","W","W","L"]

    Args:
        name: Manager display name — case-insensitive

    Examples:
        GET /teams/brian/matchups
        GET /teams/zef/matchups
    """
    try:
        return get_team_matchups(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/transactions")
def team_transactions(name: str):
    """
    Career transaction summary across all BlackGold seasons.

    Returns all-time and last-5 summaries for trades, moves, and FAAB spending,
    plus a per-season table with year, team_name, trades, moves, faab_spent.

    FAAB stats only appear for seasons where FAAB was active.

    Args:
        name: Manager display name — case-insensitive

    Examples:
        GET /teams/brian/transactions
        GET /teams/joey/transactions
    """
    try:
        return get_team_transactions(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Head-to-head
# ---------------------------------------------------------------------------

@router.get("/{name1}/vs/{name2}")
def h2h_matchups(
    name1: str,
    name2: str,
    year: str = Query(
        default="current",
        description="Season year, 'current', or 'all' for all-time H2H",
    ),
):
    """
    Head-to-head matchup record between two managers.

    Use year='all' for the all-time record across every shared season.
    Use a specific year (e.g. '2022') or 'current' for a single season.

    Returns a summary (wins/losses/ties) and full matchup list with
    scores, margins, and playoff flags.

    Args:
        name1: First manager's display name — case-insensitive
        name2: Second manager's display name — case-insensitive
        year: "current" (default), specific year, or "all"

    Examples:
        GET /teams/brian/vs/zef
        GET /teams/brian/vs/zef?year=2020
        GET /teams/brian/vs/zef?year=all
    """
    try:
        return get_h2h_matchups(name1, name2, year)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/{name}/players")
def team_players(name: str):
    """
    Per-season player roster for a manager, ordered by total points.

    For each season returns:
      - Player name, position, total points
      - Weeks on roster vs weeks as starter
      - How they were acquired (draft, trade, waiver) — from seeded config data

    Data comes from PLAYER_HISTORY_MANUAL in config.py (seeded after each season
    via GET /league/seed?year=YYYY). Falls back to live API fetch for current/
    unseeded seasons (no acquisition data in live mode).

    Args:
        name: Manager display name — case-insensitive

    Examples:
        GET /teams/brian/players
        GET /teams/zef/players
    """
    try:
        return get_team_players(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Debug endpoints
# ---------------------------------------------------------------------------

@router.get("/debug/{name}/matchups-raw")
def debug_matchups_raw(
    name: str,
    year: str = Query(default="current", description="Season year or 'current'"),
):
    """
    Debug: shows raw YFPY matchup response structure for a manager in a season.
    Use this to diagnose why /matchups returns empty opponents.
    """
    try:
        from services.fantasy.team_service import (
            _get_manager_data, _get_team_key, _team_id_from_key,
            _get_all_team_map, _resolve_year, _convert_to_dict
        )
        from services.fantasy.league_service import get_league_key_for_season
        from services.yahoo_service import get_query

        year = _resolve_year(year)
        league_key = get_league_key_for_season(year)
        manager_data = _get_manager_data(name)
        team_key = _get_team_key(name, league_key)
        team_id = _team_id_from_key(team_key) if team_key else None

        if not team_key:
            return {"error": f"Manager {name} not found in {year}"}

        query = get_query(league_key)
        raw = query.get_team_matchups(team_id)
        raw_dict = _convert_to_dict(raw)

        # Show the top-level structure without full depth
        def _summarize(obj, depth=0):
            if depth > 3:
                return f"<{type(obj).__name__}>"
            if isinstance(obj, dict):
                return {k: _summarize(v, depth+1) for k, v in list(obj.items())[:5]}
            if isinstance(obj, list):
                summary = [_summarize(obj[0], depth+1)] if obj else []
                return {"_list_len": len(obj), "_first_item": summary[0] if summary else None}
            return obj

        return {
            "year": year,
            "league_key": league_key,
            "team_key": team_key,
            "team_id_passed_to_yfpy": team_id,
            "raw_type": type(raw).__name__,
            "raw_dict_type": type(raw_dict).__name__,
            "top_level_keys": list(raw_dict.keys()) if isinstance(raw_dict, dict) else f"list of {len(raw_dict)}",
            "structure_preview": _summarize(raw_dict),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/{name}/transactions-raw")
def debug_transactions_raw(
    name: str,
    year: str = Query(default="current", description="Season year or 'current'"),
):
    """
    Debug: shows raw YFPY team standings data to inspect FAAB fields.
    Use this to diagnose why /transactions shows no FAAB seasons.
    """
    try:
        from services.fantasy.team_service import (
            _get_manager_data, _get_team_key, _resolve_year,
            _extract_teams_list, _find_team_in_standings, _convert_to_dict
        )
        from services.fantasy.league_service import get_league_key_for_season
        from services.yahoo_service import get_query

        year = _resolve_year(year)
        league_key = get_league_key_for_season(year)
        team_key = _get_team_key(name, league_key)

        if not team_key:
            return {"error": f"Manager {name} not found in {year}"}

        query = get_query(league_key)

        # Check league settings for uses_faab flag
        settings_raw = query.get_league_settings()
        settings_dict = _convert_to_dict(settings_raw)
        uses_faab = settings_dict.get("uses_faab")
        waiver_type = settings_dict.get("waiver_type")

        # Check team object for FAAB fields
        standings_raw = query.get_league_standings()
        standings_dict = _convert_to_dict(standings_raw)
        teams_list = _extract_teams_list(standings_dict)
        t = _find_team_in_standings(teams_list, team_key)

        # Show all keys on the team object
        team_keys = list(t.keys()) if t else []
        faab_fields = {k: t.get(k) for k in team_keys if "faab" in k.lower() or "auction" in k.lower() or "budget" in k.lower() or "waiver" in k.lower()}

        return {
            "year": year,
            "league_key": league_key,
            "team_key": team_key,
            "league_uses_faab": uses_faab,
            "league_waiver_type": waiver_type,
            "team_all_keys": team_keys,
            "team_faab_related_fields": faab_fields,
            "number_of_moves": t.get("number_of_moves") if t else None,
            "number_of_trades": t.get("number_of_trades") if t else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))