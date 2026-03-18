"""
Explore Router — Full YFPY Method Coverage
===========================================
One endpoint per YFPY method. Use these to understand exactly what data
each call returns before deciding what goes into each JSON file.

All endpoints accept optional query params:
  - year:    season year (default: current)
  - team_id: numeric team ID (default: "1")
  - week:    week number (default: 1)
  - player_id: Yahoo player ID (default: "8793" = Ja'Marr Chase)
  - game_id:   Yahoo game ID (default: current NFL game_id)

Base URL: /explore/...
"""

from fastapi import APIRouter, HTTPException, Query
from services.yahoo_service import get_query
from services.fantasy.league_service import (
    get_league_key_for_season,
    get_current_season,
    _convert_to_dict,
)
from config import get_known_league_key

router = APIRouter(prefix="/explore", tags=["Explore"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_query_and_key(year: str):
    if year == "current":
        year = str(get_current_season())
    league_key = get_league_key_for_season(year)
    return get_query(league_key), league_key, year


def _safe(label: str, fn):
    """Run fn(), return result or error dict."""
    try:
        raw = fn()
        return _convert_to_dict(raw)
    except Exception as e:
        return {"error": str(e), "method": label}


# ---------------------------------------------------------------------------
# INDEX — lists all explore endpoints
# ---------------------------------------------------------------------------

@router.get("/")
def explore_index():
    """Lists every available explore endpoint with a short description."""
    return {
        "user": {
            "/explore/user/current":           "get_current_user — your Yahoo account info",
            "/explore/user/games":             "get_user_games — all Yahoo games you've played",
            "/explore/user/leagues":           "get_user_leagues_by_game_key — leagues in a game",
            "/explore/user/teams":             "get_user_teams — your teams in a game",
        },
        "game": {
            "/explore/game/all-keys":          "get_all_yahoo_fantasy_game_keys — every Yahoo game ever",
            "/explore/game/current-info":      "get_current_game_info — current NFL game info",
            "/explore/game/current-metadata":  "get_current_game_metadata — current NFL metadata",
            "/explore/game/info/{game_id}":    "get_game_info_by_game_id — info for any game",
            "/explore/game/metadata/{game_id}":"get_game_metadata_by_game_id",
            "/explore/game/key-by-season":     "get_game_key_by_season — game key for a year",
            "/explore/game/position-types/{game_id}": "get_game_position_types_by_game_id",
            "/explore/game/roster-positions/{game_id}": "get_game_roster_positions_by_game_id",
            "/explore/game/stat-categories/{game_id}":  "get_game_stat_categories_by_game_id",
            "/explore/game/weeks/{game_id}":   "get_game_weeks_by_game_id — week schedule",
        },
        "league": {
            "/explore/league/info":            "get_league_info — combined league info",
            "/explore/league/key":             "get_league_key — league key string",
            "/explore/league/metadata":        "get_league_metadata — season, dates, status",
            "/explore/league/settings":        "get_league_settings — scoring, roster, draft rules",
            "/explore/league/standings":       "get_league_standings — W-L-T, points, rank",
            "/explore/league/teams":           "get_league_teams — all teams + manager info",
            "/explore/league/draft-results":   "get_league_draft_results — full draft board",
            "/explore/league/transactions":    "get_league_transactions — adds, drops, trades",
            "/explore/league/players":         "get_league_players — rostered players",
            "/explore/league/matchups/{week}": "get_league_matchups_by_week",
            "/explore/league/scoreboard/{week}":"get_league_scoreboard_by_week",
        },
        "team": {
            "/explore/team/info/{team_id}":           "get_team_info",
            "/explore/team/metadata/{team_id}":       "get_team_metadata",
            "/explore/team/standings/{team_id}":      "get_team_standings — team rank/record",
            "/explore/team/stats/{team_id}":          "get_team_stats — season stats",
            "/explore/team/stats-by-week/{team_id}":  "get_team_stats_by_week",
            "/explore/team/matchups/{team_id}":       "get_team_matchups — all matchups",
            "/explore/team/draft-results/{team_id}":  "get_team_draft_results",
            "/explore/team/roster/{team_id}":         "get_team_roster_by_week",
            "/explore/team/roster-player-info-week/{team_id}":  "get_team_roster_player_info_by_week",
            "/explore/team/roster-player-info-date/{team_id}":  "get_team_roster_player_info_by_date",
            "/explore/team/roster-player-stats/{team_id}":      "get_team_roster_player_stats — season",
            "/explore/team/roster-player-stats-week/{team_id}": "get_team_roster_player_stats_by_week",
        },
        "player": {
            "/explore/player/stats-by-week/{player_id}":   "get_player_stats_by_week",
            "/explore/player/stats-by-date/{player_id}":   "get_player_stats_by_date",
            "/explore/player/stats-for-season/{player_id}":"get_player_stats_for_season",
            "/explore/player/ownership/{player_id}":        "get_player_ownership",
            "/explore/player/percent-owned/{player_id}":    "get_player_percent_owned_by_week",
            "/explore/player/draft-analysis/{player_id}":   "get_player_draft_analysis",
        },
        "params": {
            "year":      "Season year, default 'current'",
            "team_id":   "Numeric team ID, default '6' (Brian)",
            "week":      "Week number, default 1",
            "player_id": "Yahoo player ID, default '33403' (CMC)",
            "game_id":   "Yahoo game ID, default '461' (NFL 2025)",
        }
    }


# ---------------------------------------------------------------------------
# USER endpoints
# ---------------------------------------------------------------------------

@router.get("/user/current")
def user_current():
    """get_current_user — your Yahoo account info, GUID, profile."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_current_user", query.get_current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/games")
def user_games():
    """get_user_games — every Yahoo Fantasy game you've ever participated in."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_user_games", query.get_user_games)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/leagues")
def user_leagues(
    game_key: str = Query(default="461", description="Yahoo game key e.g. '461' for NFL 2025, '466' for NBA 2025"),
):
    """get_user_leagues_by_game_key — your leagues in a specific game."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_user_leagues_by_game_key",
                     lambda: query.get_user_leagues_by_game_key(game_key))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/teams")
def user_teams():
    """get_user_teams — your teams across all current leagues."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_user_teams", query.get_user_teams)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GAME endpoints
# ---------------------------------------------------------------------------

@router.get("/game/all-keys")
def game_all_keys():
    """get_all_yahoo_fantasy_game_keys — complete list of every Yahoo Fantasy game ever."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_all_yahoo_fantasy_game_keys",
                     query.get_all_yahoo_fantasy_game_keys)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/current-info")
def game_current_info(year: str = Query(default="current")):
    """get_current_game_info — info about the current game (NFL season)."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return _safe("get_current_game_info", query.get_current_game_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/current-metadata")
def game_current_metadata(year: str = Query(default="current")):
    """get_current_game_metadata."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return _safe("get_current_game_metadata", query.get_current_game_metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/info/{game_id}")
def game_info_by_id(game_id: str):
    """get_game_info_by_game_id — info for any game by its numeric ID."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_game_info_by_game_id",
                     lambda: query.get_game_info_by_game_id(game_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/metadata/{game_id}")
def game_metadata_by_id(game_id: str):
    """get_game_metadata_by_game_id."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_game_metadata_by_game_id",
                     lambda: query.get_game_metadata_by_game_id(game_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/key-by-season")
def game_key_by_season(year: str = Query(default="current")):
    """get_game_key_by_season — the game key for a specific NFL season year."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return _safe("get_game_key_by_season",
                     lambda: query.get_game_key_by_season(year))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/position-types/{game_id}")
def game_position_types(game_id: str):
    """get_game_position_types_by_game_id — O/D/K position type definitions."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_game_position_types_by_game_id",
                     lambda: query.get_game_position_types_by_game_id(game_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/roster-positions/{game_id}")
def game_roster_positions(game_id: str):
    """get_game_roster_positions_by_game_id — QB/WR/RB/TE/FLEX etc."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_game_roster_positions_by_game_id",
                     lambda: query.get_game_roster_positions_by_game_id(game_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/stat-categories/{game_id}")
def game_stat_categories(game_id: str):
    """get_game_stat_categories_by_game_id — all stat_ids and their display names."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_game_stat_categories_by_game_id",
                     lambda: query.get_game_stat_categories_by_game_id(game_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/game/weeks/{game_id}")
def game_weeks(game_id: str):
    """get_game_weeks_by_game_id — week start/end dates for a season."""
    try:
        query = get_query(get_known_league_key())
        return _safe("get_game_weeks_by_game_id",
                     lambda: query.get_game_weeks_by_game_id(game_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# LEAGUE endpoints
# ---------------------------------------------------------------------------

@router.get("/league/info")
def league_info(year: str = Query(default="current")):
    """get_league_info — combined league info object."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "league_key": league_key,
                "data": _safe("get_league_info", query.get_league_info)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/key")
def league_key_endpoint(year: str = Query(default="current")):
    """get_league_key — returns the league key string."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "league_key": league_key,
                "data": _safe("get_league_key", query.get_league_key)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/metadata")
def league_metadata(year: str = Query(default="current")):
    """get_league_metadata — season, dates, num_teams, status, renew chain."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "league_key": league_key,
                "data": _safe("get_league_metadata", query.get_league_metadata)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/settings")
def league_settings(year: str = Query(default="current")):
    """get_league_settings — scoring rules, roster positions, draft + waiver settings."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "league_key": league_key,
                "data": _safe("get_league_settings", query.get_league_settings)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/standings")
def league_standings(year: str = Query(default="current")):
    """get_league_standings — W-L-T, points for/against, rank, playoff seed."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "league_key": league_key,
                "data": _safe("get_league_standings", query.get_league_standings)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/teams")
def league_teams(year: str = Query(default="current")):
    """get_league_teams — all teams with manager info, logos, FAAB balance."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "league_key": league_key,
                "data": _safe("get_league_teams", query.get_league_teams)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/draft-results")
def league_draft_results(year: str = Query(default="current")):
    """get_league_draft_results — full draft board with pick, round, cost, player."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "league_key": league_key,
                "data": _safe("get_league_draft_results", query.get_league_draft_results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/transactions")
def league_transactions(year: str = Query(default="current")):
    """get_league_transactions — adds, drops, trades, FAAB bids."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "league_key": league_key,
                "data": _safe("get_league_transactions", query.get_league_transactions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/players")
def league_players(year: str = Query(default="current")):
    """get_league_players — all rostered players in the league."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "league_key": league_key,
                "data": _safe("get_league_players", query.get_league_players)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/matchups/{week}")
def league_matchups(
    week: int,
    year: str = Query(default="current"),
):
    """get_league_matchups_by_week — all matchups for a given week."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "week": week, "league_key": league_key,
                "data": _safe("get_league_matchups_by_week",
                              lambda: query.get_league_matchups_by_week(week))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/league/scoreboard/{week}")
def league_scoreboard(
    week: int,
    year: str = Query(default="current"),
):
    """get_league_scoreboard_by_week — scores + win probability for a week."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "week": week, "league_key": league_key,
                "data": _safe("get_league_scoreboard_by_week",
                              lambda: query.get_league_scoreboard_by_week(week))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# TEAM endpoints
# ---------------------------------------------------------------------------

@router.get("/team/info/{team_id}")
def team_info(
    team_id: str,
    year: str = Query(default="current"),
):
    """get_team_info — team name, logo, manager, URL."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "team_id": team_id,
                "data": _safe("get_team_info",
                              lambda: query.get_team_info(team_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/metadata/{team_id}")
def team_metadata(
    team_id: str,
    year: str = Query(default="current"),
):
    """get_team_metadata."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "team_id": team_id,
                "data": _safe("get_team_metadata",
                              lambda: query.get_team_metadata(team_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/standings/{team_id}")
def team_standings(
    team_id: str,
    year: str = Query(default="current"),
):
    """get_team_standings — rank, W-L-T, points for/against, streak."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "team_id": team_id,
                "data": _safe("get_team_standings",
                              lambda: query.get_team_standings(team_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/stats/{team_id}")
def team_stats(
    team_id: str,
    year: str = Query(default="current"),
):
    """get_team_stats — season-level team stats."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "team_id": team_id,
                "data": _safe("get_team_stats",
                              lambda: query.get_team_stats(team_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/stats-by-week/{team_id}")
def team_stats_by_week(
    team_id: str,
    week: int = Query(default=1),
    year: str = Query(default="current"),
):
    """get_team_stats_by_week — passing/rushing/receiving totals for one week."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "week": week, "team_id": team_id,
                "data": _safe("get_team_stats_by_week",
                              lambda: query.get_team_stats_by_week(team_id, week))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/matchups/{team_id}")
def team_matchups(
    team_id: str,
    year: str = Query(default="current"),
):
    """get_team_matchups — all matchups, scores, is_playoffs, winner."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "team_id": team_id,
                "data": _safe("get_team_matchups",
                              lambda: query.get_team_matchups(team_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/draft-results/{team_id}")
def team_draft_results(
    team_id: str,
    year: str = Query(default="current"),
):
    """get_team_draft_results — every pick this team made in the draft."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "team_id": team_id,
                "data": _safe("get_team_draft_results",
                              lambda: query.get_team_draft_results(team_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/roster/{team_id}")
def team_roster(
    team_id: str,
    week: int = Query(default=1),
    year: str = Query(default="current"),
):
    """get_team_roster_by_week — players on roster, selected_position, starting_status."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "week": week, "team_id": team_id,
                "data": _safe("get_team_roster_by_week",
                              lambda: query.get_team_roster_by_week(team_id, week))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/roster-player-info-week/{team_id}")
def team_roster_player_info_week(
    team_id: str,
    week: int = Query(default=1),
    year: str = Query(default="current"),
):
    """get_team_roster_player_info_by_week — player details + ownership by week."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "week": week, "team_id": team_id,
                "data": _safe("get_team_roster_player_info_by_week",
                              lambda: query.get_team_roster_player_info_by_week(team_id, week))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/roster-player-info-date/{team_id}")
def team_roster_player_info_date(
    team_id: str,
    date: str = Query(default="2025-11-10", description="Date in YYYY-MM-DD format"),
    year: str = Query(default="current"),
):
    """get_team_roster_player_info_by_date — player info for a specific date (useful for NBA daily lineups)."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "date": date, "team_id": team_id,
                "data": _safe("get_team_roster_player_info_by_date",
                              lambda: query.get_team_roster_player_info_by_date(team_id, date))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/roster-player-stats/{team_id}")
def team_roster_player_stats(
    team_id: str,
    year: str = Query(default="current"),
):
    """get_team_roster_player_stats — season-long stats for every player on the roster."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "team_id": team_id,
                "data": _safe("get_team_roster_player_stats",
                              lambda: query.get_team_roster_player_stats(team_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team/roster-player-stats-week/{team_id}")
def team_roster_player_stats_week(
    team_id: str,
    week: int = Query(default=1),
    year: str = Query(default="current"),
):
    """get_team_roster_player_stats_by_week — weekly stats for every rostered player."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "week": week, "team_id": team_id,
                "data": _safe("get_team_roster_player_stats_by_week",
                              lambda: query.get_team_roster_player_stats_by_week(team_id, week))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# PLAYER endpoints
# ---------------------------------------------------------------------------

@router.get("/player/stats-by-week/{player_id}")
def player_stats_by_week(
    player_id: str,
    week: int = Query(default=1),
    year: str = Query(default="current"),
):
    """get_player_stats_by_week — stat line for a player in a specific week."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "week": week, "player_id": player_id,
                "data": _safe("get_player_stats_by_week",
                              lambda: query.get_player_stats_by_week(player_id, week))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/player/stats-by-date/{player_id}")
def player_stats_by_date(
    player_id: str,
    date: str = Query(default="2025-11-10", description="YYYY-MM-DD"),
    year: str = Query(default="current"),
):
    """get_player_stats_by_date — useful for NBA daily stats."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "date": date, "player_id": player_id,
                "data": _safe("get_player_stats_by_date",
                              lambda: query.get_player_stats_by_date(player_id, date))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/player/stats-for-season/{player_id}")
def player_stats_for_season(
    player_id: str,
    year: str = Query(default="current"),
):
    """get_player_stats_for_season — full season stat line for a player."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "player_id": player_id,
                "data": _safe("get_player_stats_for_season",
                              lambda: query.get_player_stats_for_season(player_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/player/ownership/{player_id}")
def player_ownership(
    player_id: str,
    year: str = Query(default="current"),
):
    """get_player_ownership — which team owns this player, ownership %."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "player_id": player_id,
                "data": _safe("get_player_ownership",
                              lambda: query.get_player_ownership(player_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/player/percent-owned/{player_id}")
def player_percent_owned(
    player_id: str,
    week: int = Query(default=1),
    year: str = Query(default="current"),
):
    """get_player_percent_owned_by_week — % of leagues that own this player."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "week": week, "player_id": player_id,
                "data": _safe("get_player_percent_owned_by_week",
                              lambda: query.get_player_percent_owned_by_week(player_id, week))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/player/draft-analysis/{player_id}")
def player_draft_analysis(
    player_id: str,
    year: str = Query(default="current"),
):
    """get_player_draft_analysis — ADP, auction value, % drafted."""
    try:
        query, league_key, year = _get_query_and_key(year)
        return {"year": year, "player_id": player_id,
                "data": _safe("get_player_draft_analysis",
                              lambda: query.get_player_draft_analysis(player_id))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# BULK — run all methods at once for a quick full-picture snapshot
# ---------------------------------------------------------------------------

@router.get("/bulk/league-snapshot")
def bulk_league_snapshot(
    year: str = Query(default="current"),
    team_id: str = Query(default="6", description="Numeric team ID"),
    week: int = Query(default=1),
):
    """
    Runs every league-level YFPY call in one shot.
    Useful for seeing the full data picture for a season at a glance.
    WARNING: slow — makes ~10 API calls.
    """
    try:
        query, league_key, year = _get_query_and_key(year)
        return {
            "year":            year,
            "league_key":      league_key,
            "league_metadata": _safe("get_league_metadata",   query.get_league_metadata),
            "league_settings": _safe("get_league_settings",   query.get_league_settings),
            "league_standings":_safe("get_league_standings",  query.get_league_standings),
            "league_teams":    _safe("get_league_teams",       query.get_league_teams),
            "draft_results":   _safe("get_league_draft_results", query.get_league_draft_results),
            "transactions":    _safe("get_league_transactions", query.get_league_transactions),
            "scoreboard":      _safe("get_league_scoreboard_by_week",
                                     lambda: query.get_league_scoreboard_by_week(week)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bulk/team-snapshot/{team_id}")
def bulk_team_snapshot(
    team_id: str,
    year: str = Query(default="current"),
    week: int = Query(default=1),
):
    """
    Runs every team-level YFPY call for one team in one shot.
    WARNING: slow — makes ~8 API calls.
    """
    try:
        query, league_key, year = _get_query_and_key(year)
        return {
            "year":              year,
            "team_id":           team_id,
            "league_key":        league_key,
            "team_info":         _safe("get_team_info",         lambda: query.get_team_info(team_id)),
            "team_standings":    _safe("get_team_standings",    lambda: query.get_team_standings(team_id)),
            "team_stats":        _safe("get_team_stats",        lambda: query.get_team_stats(team_id)),
            "team_stats_week":   _safe("get_team_stats_by_week",lambda: query.get_team_stats_by_week(team_id, week)),
            "team_matchups":     _safe("get_team_matchups",     lambda: query.get_team_matchups(team_id)),
            "team_draft":        _safe("get_team_draft_results",lambda: query.get_team_draft_results(team_id)),
            "roster_week":       _safe("get_team_roster_by_week",lambda: query.get_team_roster_by_week(team_id, week)),
            "roster_stats":      _safe("get_team_roster_player_stats", lambda: query.get_team_roster_player_stats(team_id)),
            "roster_stats_week": _safe("get_team_roster_player_stats_by_week",
                                       lambda: query.get_team_roster_player_stats_by_week(team_id, week)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))