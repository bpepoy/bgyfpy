"""
Teams Router
============
Handles all team-specific endpoints for the BlackGold fantasy app.

Endpoints covered:
  /teams/{guid}/overview        – Career summary across all seasons
  /teams/{guid}/record          – W-L-T per season
  /teams/{guid}/points          – Points for/against per season
  /teams/{guid}/matchups        – Matchup list + H2H summary for a season
  /teams/{guid}/trades          – All trades in a season

  /teams/all/records            – All teams' records for a season
  /teams/all/points             – All teams' points leaderboard
  /teams/{guid1}/vs/{guid2}     – H2H between two managers (single season or all-time)

All endpoints that accept a `year` query parameter also accept "current" or "all" where noted.
"""

from fastapi import APIRouter, HTTPException, Query
from services.team_service import (
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
# Individual team endpoints  (/teams/{guid}/...)
# ---------------------------------------------------------------------------

@router.get("/{guid}/overview")
def team_overview(guid: str):
    """
    Career summary for a manager across ALL seasons.

    Returns:
      - Seasons played, championships, last-place finishes, playoff appearances
      - Career totals: wins, losses, ties, points for/against
      - Season-by-season history list

    Args:
        guid: Manager's Yahoo GUID (from standings data)

    Example:
        GET /teams/5652MIZAVSIETJMML3FZ22DB2I/overview
    """
    try:
        return get_team_overview(guid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{guid}/record")
def team_record(guid: str):
    """
    Season-by-season W-L-T record for a manager.

    Returns each season's:
      - Wins, losses, ties, win percentage
      - Final rank and playoff seed
      - Points for/against
      - Clinched playoffs flag
      - End-of-season streak, number of moves/trades

    Args:
        guid: Manager's Yahoo GUID

    Example:
        GET /teams/5652MIZAVSIETJMML3FZ22DB2I/record
    """
    try:
        return get_team_record(guid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{guid}/points")
def team_points(guid: str):
    """
    Season-by-season points breakdown for a manager.

    Returns each season's:
      - Points for, points against, differential
      - Points rank (1 = top scorer in league that season)
      - Overall finish rank

    Args:
        guid: Manager's Yahoo GUID

    Example:
        GET /teams/5652MIZAVSIETJMML3FZ22DB2I/points
    """
    try:
        return get_team_points(guid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{guid}/matchups")
def team_matchups(
    guid: str,
    year: str = Query(default="current", description="Season year or 'current'"),
):
    """
    All matchups for a manager in a given season, plus H2H summary vs each opponent.

    Returns:
      - Week-by-week matchup results (W/L/T, scores, margin)
      - H2H summary against each opponent (wins/losses/ties)

    Args:
        guid: Manager's Yahoo GUID
        year: Season year (e.g. "2024") or "current" (default)

    Examples:
        GET /teams/5652MIZAVSIETJMML3FZ22DB2I/matchups
        GET /teams/5652MIZAVSIETJMML3FZ22DB2I/matchups?year=2022
    """
    try:
        return get_team_matchups(guid, year)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{guid}/trades")
def team_trades(
    guid: str,
    year: str = Query(default="current", description="Season year or 'current'"),
):
    """
    All trades involving a manager in a given season.

    Returns each trade with:
      - Trade date, opponent name
      - Players received (name, position)
      - Players sent (name, position)

    Args:
        guid: Manager's Yahoo GUID
        year: Season year (e.g. "2024") or "current" (default)

    Examples:
        GET /teams/5652MIZAVSIETJMML3FZ22DB2I/trades
        GET /teams/5652MIZAVSIETJMML3FZ22DB2I/trades?year=2021
    """
    try:
        return get_team_trades(guid, year)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# All-teams comparison endpoints  (/teams/all/...)
# ---------------------------------------------------------------------------

@router.get("/all/records")
def all_teams_records(
    year: str = Query(default="current", description="Season year or 'current'"),
):
    """
    W-L-T records for every team in a season, sorted by final rank.

    Returns each team's:
      - Wins, losses, ties, win percentage
      - Points for/against
      - Rank, playoff seed, clinched status
      - Manager display name and GUID

    Args:
        year: Season year (e.g. "2024") or "current" (default)

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
    Points leaderboard for all teams in a season, sorted by points scored (high to low).

    Returns each team's:
      - Points for/against, differential
      - Points rank (1 = highest scorer)
      - Overall finish rank

    Args:
        year: Season year (e.g. "2024") or "current" (default)

    Examples:
        GET /teams/all/points
        GET /teams/all/points?year=2018
    """
    try:
        return get_all_teams_points(year)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# H2H between two managers  (/teams/{guid1}/vs/{guid2})
# ---------------------------------------------------------------------------

@router.get("/{guid1}/vs/{guid2}")
def h2h_matchups(
    guid1: str,
    guid2: str,
    year: str = Query(
        default="current",
        description="Season year, 'current', or 'all' for all-time H2H",
    ),
):
    """
    Head-to-head matchup record between two managers.

    Pass year='all' to get the all-time H2H across every season both managers shared.
    Pass a specific year (e.g. '2022') or 'current' for a single season.

    Returns:
      - Summary: team1 wins, team2 wins, ties
      - Full list of matchups with week, scores, margin, playoff flag

    Args:
        guid1: First manager's Yahoo GUID
        guid2: Second manager's Yahoo GUID
        year: "current" (default), specific year, or "all"

    Examples:
        GET /teams/GUID1/vs/GUID2
        GET /teams/GUID1/vs/GUID2?year=2020
        GET /teams/GUID1/vs/GUID2?year=all
    """
    try:
        return get_h2h_matchups(guid1, guid2, year)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))