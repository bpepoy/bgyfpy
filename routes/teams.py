"""
Teams Router
============
All endpoints use display_name (e.g. "Brian", "Zef") as the manager identifier.
Names are case-insensitive.

Call GET /teams/managers first to see all valid names.

Individual team endpoints:
  GET /teams/{name}/overview          Career summary across all seasons
  GET /teams/{name}/record            W-L-T per season
  GET /teams/{name}/points            Points for/against per season
  GET /teams/{name}/matchups          Matchups + H2H for a season
  GET /teams/{name}/trades            Trades for a season

League-wide endpoints:
  GET /teams/managers                 List all managers (use for dropdowns)
  GET /teams/all/records              All teams records for a season
  GET /teams/all/points               Points leaderboard for a season

Head-to-head:
  GET /teams/{name1}/vs/{name2}       H2H between two managers

All year params accept: "current" (default), specific year e.g. "2022", or "all" (H2H only).
"""

from fastapi import APIRouter, HTTPException, Query
from services.team_service import (
    get_all_managers,
    get_team_overview,
    get_team_record,
    get_team_points,
    get_team_matchups,
    get_team_trades,
    get_all_teams_records,
    get_all_teams_points,
    get_h2h_matchups,
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


@router.get("/{name}/record")
def team_record(name: str):
    """
    Season-by-season W-L-T record for a manager.

    Returns each season's rank, playoff seed, wins, losses, ties,
    win percentage, points for/against, clinched status, and streak.

    Args:
        name: Manager display name — case-insensitive

    Examples:
        GET /teams/brian/record
        GET /teams/frank/record
    """
    try:
        return get_team_record(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/points")
def team_points(name: str):
    """
    Season-by-season points breakdown for a manager.

    Returns points for, points against, differential, points rank
    (1 = top scorer in league), and overall finish rank per season.

    Args:
        name: Manager display name — case-insensitive

    Examples:
        GET /teams/brian/points
        GET /teams/joey/points
    """
    try:
        return get_team_points(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/matchups")
def team_matchups(
    name: str,
    year: str = Query(default="current", description="Season year or 'current'"),
):
    """
    All matchups for a manager in a given season, plus H2H summary vs each opponent.

    Returns week-by-week results (W/L/T, scores, margin) and a per-opponent
    win/loss/tie summary.

    Args:
        name: Manager display name — case-insensitive
        year: Season year (e.g. "2024") or "current" (default)

    Examples:
        GET /teams/brian/matchups
        GET /teams/brian/matchups?year=2022
    """
    try:
        return get_team_matchups(name, year)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/trades")
def team_trades(
    name: str,
    year: str = Query(default="current", description="Season year or 'current'"),
):
    """
    All trades a manager made in a given season.

    Returns each trade with date, opponent name, players received, and players sent.

    Args:
        name: Manager display name — case-insensitive
        year: Season year (e.g. "2024") or "current" (default)

    Examples:
        GET /teams/brian/trades
        GET /teams/brian/trades?year=2021
    """
    try:
        return get_team_trades(name, year)
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