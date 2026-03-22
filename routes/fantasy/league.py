from fastapi import APIRouter, HTTPException, Query, Depends
from routes.auth import require_permission
from services.fantasy.league_service import (
    get_league_settings, 
    get_all_seasons, 
    get_league_key_for_season,
    get_current_season,
    get_league_standings
)

router = APIRouter(prefix="/league", tags=["League"])


@router.get("/seasons")
def get_seasons():
    """
    Get all available seasons for BlackGold league (2007-2025+).
    Follows the renew chain backwards and renewed chain forwards.
    Auto-discovers new seasons (e.g., 2026) without code changes.
    
    Returns all seasons with normalized "BlackGold" name.
    """
    try:
        return get_all_seasons()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seasons/refresh")
def refresh_seasons():
    """
    Force refresh of season cache.
    Useful at start of new season to immediately discover it.
    
    Example: When 2026 season starts, call this to detect it immediately
    instead of waiting for cache to expire.
    """
    try:
        return get_all_seasons(force_refresh=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/season/{year}/settings")
def season_settings(year: str):
    """
    Get league settings for a specific season.
    Returns data with normalized "BlackGold" name.
    
    Args:
        year: Season year (e.g., "2024", "2025") or "current" for latest
    
    Examples:
        /league/season/2024/settings
        /league/season/current/settings
    """
    try:
        # Handle "current" alias
        if year == "current":
            year = str(get_current_season())
        
        # Get the league key for this season
        league_key = get_league_key_for_season(year)
        
        return get_league_settings(league_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Legacy endpoint - kept for backward compatibility
@router.get("/{league_key}/settings")
def league_settings_legacy(league_key: str):
    """
    Legacy endpoint - get league settings by league key.
    For backward compatibility only.
    
    Prefer using /league/season/{year}/settings instead.
    """
    try:
        return get_league_settings(league_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Keep the raw data endpoint for debugging
@router.get("/{league_key}/raw")
def league_raw_data(league_key: str):
    """
    Get ALL raw league data to see what's available from Yahoo API.
    Useful for debugging and exploring available fields.
    
    Args:
        league_key: League ID or full league key
    """
    try:
        from services.yahoo_service import get_query
        
        query = get_query(league_key)
        raw = query.get_league_metadata()
        
        # Convert to dict
        if hasattr(raw, 'to_json'):
            raw_dict = raw.to_json()
        elif hasattr(raw, '__dict__'):
            raw_dict = raw.__dict__
        else:
            raw_dict = raw
        
        # If it's a string, parse it
        if isinstance(raw_dict, str):
            import json
            raw_dict = json.loads(raw_dict)
        
        return {
            "message": "All available fields from Yahoo API",
            "data": raw_dict
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/season/{year}/standings")
def season_standings(year: str):
    """
    Get league standings for a specific season.
    Returns team rankings, records, points for/against.
    
    Args:
        year: Season year (e.g., "2024", "2025") or "current" for latest
    
    Examples:
        /league/season/2024/standings
        /league/season/current/standings
    """
    try:
        from services.fantasy.league_service import get_league_standings
        
        # Handle "current" alias
        if year == "current":
            year = str(get_current_season())
        
        # Get the league key for this season
        league_key = get_league_key_for_season(year)
        
        return get_league_standings(league_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))    
    
@router.get("/season/{year}/standings/raw")
def season_standings_raw(year: str):
    """
    Debug endpoint - see raw standings data from Yahoo API.
    """
    try:
        from services.yahoo_service import get_query
        
        # Handle "current" alias
        if year == "current":
            year = str(get_current_season())
        
        # Get the league key for this season
        league_key = get_league_key_for_season(year)
        
        query = get_query(league_key)
        standings = query.get_league_standings()
        
        # Show what type it is
        result = {
            "type": type(standings).__name__,
            "is_list": isinstance(standings, list),
            "length": len(standings) if isinstance(standings, (list, tuple)) else "N/A",
        }
        
        # Try to convert to see structure
        if isinstance(standings, list) and len(standings) > 0:
            first_item = standings[0]
            
            if hasattr(first_item, 'to_json'):
                result["first_item_json"] = first_item.to_json()
            elif hasattr(first_item, '__dict__'):
                result["first_item_dict"] = first_item.__dict__
            else:
                result["first_item"] = str(first_item)[:500]
        else:
            # Not a list, try to convert the whole thing
            if hasattr(standings, 'to_json'):
                result["full_json"] = standings.to_json()
            elif hasattr(standings, '__dict__'):
                result["full_dict"] = standings.__dict__
            else:
                result["full_str"] = str(standings)[:1000]
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/season/{year}/settings/raw")
def season_settings_raw(year: str):
    """
    Debug endpoint - see ALL raw settings data including scoring rules.
    """
    try:
        from services.yahoo_service import get_query
        
        # Handle "current" alias
        if year == "current":
            year = str(get_current_season())
        
        # Get the league key for this season
        league_key = get_league_key_for_season(year)
        
        query = get_query(league_key)
        
        # Get league settings (includes scoring rules)
        settings = query.get_league_settings()
        
        # Convert to dict
        if hasattr(settings, 'to_json'):
            settings_dict = settings.to_json()
        elif hasattr(settings, '__dict__'):
            settings_dict = settings.__dict__
        else:
            settings_dict = settings
        
        if isinstance(settings_dict, str):
            import json
            settings_dict = json.loads(settings_dict)
        
        return {
            "type": type(settings).__name__,
            "data": settings_dict
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rules")
def get_rules():
    """
    Get all league rules in one endpoint.
    Includes scoring rules, roster settings, league settings, and payment structure.
    
    Returns rules from the current season.
    
    Example: GET /league/rules
    """
    try:
        from services.fantasy.league_service import get_league_rules
        return get_league_rules()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/explore/season/{year}")
def explore_season_data(year: str):
    """
    Debug endpoint - Shows ALL available data for a season.
    Returns everything YFPY can fetch.
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import (
            get_league_key_for_season,
            _convert_to_dict
        )
        
        league_key = get_league_key_for_season(year)
        query = get_query(league_key)
        
        data = {}
        
        # 1. League Metadata
        try:
            metadata = query.get_league_metadata()
            data["league_metadata"] = _convert_to_dict(metadata)
        except Exception as e:
            data["league_metadata"] = {"error": str(e)}
        
        # 2. League Settings
        try:
            settings = query.get_league_settings()
            data["league_settings"] = _convert_to_dict(settings)
        except Exception as e:
            data["league_settings"] = {"error": str(e)}
        
        # 3. League Standings
        try:
            standings = query.get_league_standings()
            data["league_standings"] = _convert_to_dict(standings)
        except Exception as e:
            data["league_standings"] = {"error": str(e)}
        
        # 4. League Scoreboard (weekly matchups)
        try:
            scoreboard = query.get_league_scoreboard_by_week(1)
            data["scoreboard_week_1"] = _convert_to_dict(scoreboard)
        except Exception as e:
            data["scoreboard_week_1"] = {"error": str(e)}
        
        # 5. League Teams
        try:
            teams = query.get_league_teams()
            data["league_teams"] = _convert_to_dict(teams)
        except Exception as e:
            data["league_teams"] = {"error": str(e)}
        
        # 6. League Draft Results
        try:
            draft = query.get_league_draft_results()
            data["draft_results"] = _convert_to_dict(draft)
        except Exception as e:
            data["draft_results"] = {"error": str(e)}
        
        # 7. League Transactions
        try:
            transactions = query.get_league_transactions()
            data["transactions"] = _convert_to_dict(transactions)
        except Exception as e:
            data["transactions"] = {"error": str(e)}
        
        # 8. Team Rosters (for first team)
        try:
            teams_list = query.get_league_teams()
            teams_dict = _convert_to_dict(teams_list)
            if "teams" in teams_dict:
                first_team = teams_dict["teams"][0].get("team", {})
                team_key = first_team.get("team_key")
                if team_key:
                    roster = query.get_team_roster_by_week(team_key, 1)
                    data["sample_team_roster_week_1"] = _convert_to_dict(roster)
        except Exception as e:
            data["sample_team_roster"] = {"error": str(e)}
        
        # 9. Team Stats (for first team)
        try:
            if team_key:
                stats = query.get_team_stats_by_week(team_key, 1)
                data["sample_team_stats_week_1"] = _convert_to_dict(stats)
        except Exception as e:
            data["sample_team_stats"] = {"error": str(e)}
        
        # 10. Matchups
        try:
            if team_key:
                matchups = query.get_team_matchups(team_key)
                data["sample_team_matchups"] = _convert_to_dict(matchups)
        except Exception as e:
            data["sample_team_matchups"] = {"error": str(e)}
        
        return {
            "year": year,
            "league_key": league_key,
            "available_data": data,
            "note": "This shows ALL data Yahoo provides for this season"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/what-yahoo-has")
def explore_what_yahoo_has():
    """
    Shows what data Yahoo API provides across different seasons.
    """
    return {
        "yahoo_api_capabilities": {
            "league_level": {
                "metadata": "League info, season, teams count, etc.",
                "settings": "Scoring, roster, draft, playoff settings",
                "standings": "Final rankings, records, points",
                "teams": "Team names, managers, logos",
                "draft_results": "Who drafted who (may be limited to recent seasons)",
                "transactions": "Trades, adds, drops (may be limited)",
                "scoreboard": "Weekly matchups with scores"
            },
            "team_level": {
                "roster": "Players on team by week",
                "stats": "Team stats by week",
                "matchups": "All matchups for a team",
                "standings": "Team's rank, record, points"
            },
            "player_level": {
                "stats": "Individual player stats",
                "ownership": "Which team owns a player"
            },
            "limitations": {
                "historical_rosters": "May only be available for recent seasons (1-3 years)",
                "bench_players": "Roster shows who was ON team, not necessarily who STARTED",
                "weekly_lineup_decisions": "May not show which players were benched vs started each week",
                "trades_historical": "Transaction data may be limited to recent seasons",
                "draft_historical": "Draft results may not be available for old seasons"
            },
            "test_instructions": "Use /explore/season/{year} to see actual data for any year"
        }
    }

@router.get("/explore/availability-matrix")
def check_data_availability():
    """
    Tests what data is available across all 19 seasons.
    This will take a while to run!
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import (
            get_all_seasons,
            _convert_to_dict
        )
        
        seasons_data = get_all_seasons()
        seasons = seasons_data.get("seasons", [])
        
        results = []
        
        # Test a sample of years (don't test all 19, too slow)
        test_years = [2025, 2020, 2015, 2010, 2007]
        
        for season in seasons:
            year = season.get("year")
            if year not in test_years:
                continue
                
            league_key = season.get("league_key")
            query = get_query(league_key)
            
            availability = {
                "year": year,
                "league_key": league_key,
                "data_available": {}
            }
            
            # Test each data type
            tests = {
                "standings": lambda: query.get_league_standings(),
                "settings": lambda: query.get_league_settings(),
                "teams": lambda: query.get_league_teams(),
                "draft_results": lambda: query.get_league_draft_results(),
                "transactions": lambda: query.get_league_transactions(),
                "scoreboard_week_1": lambda: query.get_league_scoreboard_by_week(1),
            }
            
            for data_type, fetch_func in tests.items():
                try:
                    result = fetch_func()
                    availability["data_available"][data_type] = "✅ Available"
                except Exception as e:
                    availability["data_available"][data_type] = f"❌ Error: {str(e)[:50]}"
            
            results.append(availability)
        
        return {
            "tested_years": test_years,
            "results": results,
            "note": "This shows which data types Yahoo provides for different years"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/explore/historical-depth")
def test_historical_depth():
    """Tests how far back detailed data goes"""
    test_years = [2007, 2010, 2015, 2020, 2025]
    results = {}
    
    for year in test_years:
        try:
            league_key = get_league_key_for_season(str(year))
            query = get_query(league_key)
            
            year_data = {"year": year}
            
            # Test roster
            try:
                teams = query.get_league_teams()
                teams_dict = _convert_to_dict(teams)
                first_team_key = teams_dict["teams"][0]["team"]["team_key"]
                roster = query.get_team_roster_by_week(first_team_key, 1)
                year_data["roster_week_1"] = "✅ Available"
            except Exception as e:
                year_data["roster_week_1"] = f"❌ {str(e)[:50]}"
            
            # Test scoreboard
            try:
                scoreboard = query.get_league_scoreboard_by_week(1)
                year_data["scoreboard"] = "✅ Available"
            except Exception as e:
                year_data["scoreboard"] = f"❌ {str(e)[:50]}"
            
            # Test transactions
            try:
                trans = query.get_league_transactions()
                year_data["transactions"] = "✅ Available"
            except Exception as e:
                year_data["transactions"] = f"❌ {str(e)[:50]}"
            
            # Test draft
            try:
                draft = query.get_league_draft_results()
                year_data["draft"] = "✅ Available"
            except Exception as e:
                year_data["draft"] = f"❌ {str(e)[:50]}"
            
            results[str(year)] = year_data
            
        except Exception as e:
            results[str(year)] = {"error": str(e)}
    
    return {
        "test_years": test_years,
        "results": results,
        "note": "This shows how far back detailed data is available"
    }

@router.get("/history")
def league_history():
    """
    Season-by-season notable data for all BlackGold seasons (2007–present).

    Returns for each season:
      - Champion (display name, team name, record)
      - Best win-loss record (may differ from champion in a given year)
      - Team with most points scored
      - Last place team
      - First overall draft pick
      - Top fantasy scorer per position: QB, WR, RB, TE
        (rostered players only; live fetch for recent seasons, hardcoded for older ones)
      - Punishment (hardcoded in config.py until voting system is built)

    All 19 seasons returned newest-first.
    """
    try:
        from services.fantasy.league_service import get_league_history
        return get_league_history()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/seed-players")
def seed_top_players(year: str):
    """
    Admin/utility endpoint — run this ONCE after each season ends.

    Fetches the top fantasy scorer per position (QB, WR, RB, TE)
    from all rostered players in the given season, then returns a
    ready-to-paste config block for SEASON_HISTORY_MANUAL in config.py.

    Usage: GET /league/history/seed-players?year=2024
    """
    try:
        from services.fantasy.league_service import (
            get_league_key_for_season,
            _fetch_top_players,
            _fetch_first_pick,
        )
        import json

        league_key = get_league_key_for_season(year)

        top_players = _fetch_top_players(league_key)
        first_pick  = _fetch_first_pick(league_key)

        config_block = {
            int(year): {
                "punishment": None,  # TODO: fill in after vote
                "first_pick": first_pick,
                "top_players": top_players,
            }
        }

        return {
            "year": year,
            "league_key": league_key,
            "top_players": top_players,
            "first_overall_pick": first_pick,
            "paste_into_config": (
                f"    {year}: " + json.dumps(config_block[int(year)], indent=8)
            ),
            "instructions": (
                "Copy the 'paste_into_config' value into SEASON_HISTORY_MANUAL "
                "in config.py, then set punishment once it's been voted on."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/seed")
def seed_all_managers(year: str = Query(..., description="Season year e.g. '2024'")):
    """
    Admin/utility endpoint — run ONCE after each season ends.

    Fetches weekly rosters, player stats, draft results, and transactions
    for ALL managers in the given season. Returns a ready-to-paste config
    block for PLAYER_HISTORY_MANUAL in config.py.

    This is intentionally slow (many API calls) — it runs once per season,
    not on every frontend request.

    Usage: GET /league/seed?year=2024

    After running:
      1. Copy the 'paste_into_config' section from the response
      2. Merge it into PLAYER_HISTORY_MANUAL in config.py
      3. Fill in any 'punishment' fields manually
      4. Commit and deploy
    """
    try:
        from services.fantasy.team_service import build_season_seed
        import json

        year_int = int(year)
        seed_data = build_season_seed(year_int)

        # Build paste-ready config string
        lines = []
        for manager_id, seasons in seed_data.items():
            for yr, data in seasons.items():
                lines.append(f'    # {manager_id} {yr}')
                lines.append(f'    # Add to PLAYER_HISTORY_MANUAL["{manager_id}"][{yr}]:')
                lines.append(f'    {json.dumps({yr: data}, indent=8)}')

        return {
            "year": year,
            "managers_seeded": list(seed_data.keys()),
            "data": seed_data,
            "instructions": (
                "For each manager, merge the data into PLAYER_HISTORY_MANUAL "
                "in config.py under that manager's key. "
                "Example: PLAYER_HISTORY_MANUAL['brian'][2024] = data['brian'][2024]"
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Real Bros NBA league discovery
# ---------------------------------------------------------------------------

@router.get("/explore/nba-discovery")
def discover_nba_league(
    league_id: str = Query(..., description="Your NBA league ID e.g. '38685'"),
):
    """
    Discovers the correct league key for an NBA Yahoo Fantasy league.

    Yahoo requires a numeric game_id prefix (e.g. '428.l.38685') rather than
    just the league ID. This endpoint tries common recent NBA game_ids to find
    the one that matches your league, then returns the full metadata so you can
    confirm it's the right league and build a config from it.

    Usage: GET /league/explore/nba-discovery?league_id=38685
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        # Known NBA game_ids by season (Yahoo increments these annually)
        # NBA seasons span two calendar years — keyed by the season start year
        nba_game_ids = {
            2024: 428,  # 2024-25 season
            2023: 418,  # 2023-24 season
            2022: 406,  # 2022-23 season
            2021: 396,  # 2021-22 season
            2020: 385,  # 2020-21 season
            2019: 375,  # 2019-20 season
            2018: 363,  # 2018-19 season
            2017: 352,  # 2017-18 season
            2016: 341,  # 2016-17 season
            2015: 331,  # 2015-16 season
        }

        found = []
        errors = []

        for season_year, game_id in sorted(nba_game_ids.items(), reverse=True):
            league_key = f"{game_id}.l.{league_id}"
            try:
                query = get_query(league_key)
                raw = query.get_league_metadata()
                meta = _convert_to_dict(raw)

                found.append({
                    "season_year":   season_year,
                    "game_id":       game_id,
                    "league_key":    league_key,
                    "league_name":   meta.get("name"),
                    "season":        meta.get("season"),
                    "num_teams":     meta.get("num_teams"),
                    "game_code":     meta.get("game_code"),
                    "renew":         meta.get("renew"),
                    "renewed":       meta.get("renewed"),
                    "start_date":    meta.get("start_date"),
                    "end_date":      meta.get("end_date"),
                    "is_finished":   meta.get("is_finished"),
                })
            except Exception as e:
                errors.append({
                    "season_year": season_year,
                    "league_key":  league_key,
                    "error":       str(e)[:80],
                })

        return {
            "league_id":    league_id,
            "found_seasons": found,
            "failed_attempts": errors,
            "next_step": (
                "Use the league_key and game_id values from 'found_seasons' "
                "to build a config entry for Real Bros, mirroring how BlackGold "
                "is configured in config.py with LEAGUE_CONFIG and MANUAL_SEASON_MAPPING."
            ),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/nba-season/{league_key}")
def explore_nba_season(league_key: str):
    """
    Same as /explore/season/{year} but takes a full league key directly.
    Use this for NBA leagues where you already know the league key from
    the nba-discovery endpoint.

    Usage: GET /league/explore/nba-season/428.l.38685

    Note: Use dots in the URL — e.g. 428.l.38685
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict

        query = get_query(league_key)
        data  = {}

        for label, fetcher in [
            ("league_metadata",     lambda: query.get_league_metadata()),
            ("league_settings",     lambda: query.get_league_settings()),
            ("league_standings",    lambda: query.get_league_standings()),
            ("league_teams",        lambda: query.get_league_teams()),
            ("draft_results",       lambda: query.get_league_draft_results()),
            ("transactions",        lambda: query.get_league_transactions()),
            ("scoreboard_week_1",   lambda: query.get_league_scoreboard_by_week(1)),
        ]:
            try:
                data[label] = _convert_to_dict(fetcher())
            except Exception as e:
                data[label] = {"error": str(e)[:100]}

        # Try roster for first team
        try:
            teams_raw  = query.get_league_teams()
            teams_dict = _convert_to_dict(teams_raw)
            teams_list = teams_dict if isinstance(teams_dict, list) else \
                         teams_dict.get("teams", [])
            first = teams_list[0] if teams_list else {}
            first_team = first.get("team", first) if isinstance(first, dict) else {}
            tk = first_team.get("team_key")
            if tk:
                tid = tk.split(".t.")[-1]
                data["sample_roster_week_1"] = _convert_to_dict(
                    query.get_team_roster_by_week(tid, 1)
                )
        except Exception as e:
            data["sample_roster_week_1"] = {"error": str(e)[:100]}

        return {
            "league_key":    league_key,
            "available_data": data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/my-leagues")
def get_my_leagues():
    """
    Returns ALL Yahoo Fantasy leagues associated with your authenticated account.
    Tries NBA game keys to find Real Bros league_key without guessing game_ids.

    Usage: GET /league/explore/my-leagues
    """
    try:
        from services.yahoo_service import get_query
        from services.fantasy.league_service import _convert_to_dict
        from config import get_known_league_key

        query = get_query(get_known_league_key())

        results = {}

        # Step 1: get all games this user has played in
        try:
            raw_games = query.get_user_games()
            results["user_games"] = _convert_to_dict(raw_games)
        except Exception as e:
            results["user_games"] = {"error": str(e)}

        # Step 2: try get_user_leagues_by_game_key for nba game keys
        # Yahoo game keys for NBA are the game_id as a string e.g. "428"
        # Try recent NBA game_ids as string keys
        nba_attempts = {}
        for game_id in range(420, 460):
            game_key = str(game_id)
            try:
                raw = query.get_user_leagues_by_game_key(game_key)
                data = _convert_to_dict(raw)
                # Only include if it returned something meaningful
                if data and data != {} and "error" not in str(data).lower():
                    nba_attempts[game_key] = data
                    break  # found one, stop
            except Exception:
                continue
        results["nba_league_search"] = nba_attempts if nba_attempts else "No NBA leagues found in game_id range 420-459"

        # Step 3: also try with "nba" as the game key directly
        try:
            raw_nba = query.get_user_leagues_by_game_key("nba")
            results["nba_by_code"] = _convert_to_dict(raw_nba)
        except Exception as e:
            results["nba_by_code"] = {"error": str(e)}

        return {
            "message": "Yahoo account league data",
            "results": results,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/yfpy-methods")
def get_yfpy_methods():
    """
    Returns all available methods on the YFPY query object.
    Use this to find the correct method for fetching user leagues.
    """
    try:
        from services.yahoo_service import get_query
        from config import get_known_league_key

        query = get_query(get_known_league_key())

        # Get all public methods (no leading underscore)
        methods = [m for m in dir(query) if not m.startswith("_")]

        # Filter to likely relevant ones
        user_methods      = [m for m in methods if "user" in m.lower()]
        league_methods    = [m for m in methods if "league" in m.lower()]
        game_methods      = [m for m in methods if "game" in m.lower()]

        return {
            "user_related":   user_methods,
            "league_related": league_methods,
            "game_related":   game_methods,
            "all_methods":    methods,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Data generation — managers.json
# ---------------------------------------------------------------------------

@router.get("/data/managers")
def generate_managers_data(
    year: str = Query(..., description="Season year e.g. '2025', or 'all' for every season"),
):
    """
    Generates the managers.json data block for a given season (or all seasons).

    Returns a dict keyed by year, ready to merge into data/fantasy/managers.json.
    Each season includes league metadata + every manager's team info.

    Usage:
        GET /league/data/managers?year=2025      — single season
        GET /league/data/managers?year=all       — all seasons (slow, one-time)

    Workflow:
        1. Run this endpoint
        2. Copy the returned JSON
        3. Merge into data/fantasy/managers.json under the year key
        4. Commit to git
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons,
            get_league_key_for_season,
            _convert_to_dict,
            _safe_get,
        )
        from services.fantasy.team_service import _extract_teams_list
        from services.yahoo_service import get_query
        from config import get_manager_identity
        import json, os

        # Force full season cache build — ensures all 19 seasons are discoverable
        seasons_data = get_all_seasons(force_refresh=True)
        all_seasons  = seasons_data.get("seasons", [])

        # Determine which seasons to process
        if year == "all":
            target_years = [str(s["year"]) for s in all_seasons]
        else:
            target_years = [year]

        result = {}

        for yr in target_years:
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                # League metadata
                meta_raw  = query.get_league_metadata()
                meta      = _convert_to_dict(meta_raw)

                # Use get_league_standings — returns full team info
                standings_raw  = query.get_league_standings()
                standings_dict = _convert_to_dict(standings_raw)
                teams_list     = _extract_teams_list(standings_dict)

                managers = []
                for t in teams_list:
                    if not isinstance(t, dict):
                        continue

                    team_key = t.get("team_key", "")
                    team_id  = team_key.split(".t.")[-1] if ".t." in team_key else ""

                    # Extract manager info
                    managers_raw = t.get("managers", {})
                    if isinstance(managers_raw, list):
                        mgr_wrapper = managers_raw[0] if managers_raw else {}
                    else:
                        mgr_wrapper = managers_raw
                    mgr = mgr_wrapper.get("manager", mgr_wrapper) if isinstance(mgr_wrapper, dict) else {}

                    guid        = mgr.get("guid")
                    nickname    = mgr.get("nickname")
                    is_comanager= bool(int(mgr.get("is_comanager", 0) or 0))

                    # Resolve display_name + manager_id from config
                    identity    = get_manager_identity(team_key=team_key, manager_guid=guid)
                    display_name= identity["display_name"] if identity else nickname or "Unknown"
                    manager_id  = identity["manager_id"]   if identity else None

                    # Logo
                    logos = t.get("team_logos", {})
                    if isinstance(logos, list):
                        logos = logos[0] if logos else {}
                    logo_obj = logos.get("team_logo", {}) if isinstance(logos, dict) else {}
                    if isinstance(logo_obj, list):
                        logo_obj = logo_obj[0] if logo_obj else {}
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

                # Sort by team_id numerically for consistent ordering
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

        # Auto-merge into data/fantasy/managers.json
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "fantasy", "managers.json"
        )

        # Load existing file if it exists
        existing = {}
        if os.path.exists(data_path):
            with open(data_path) as f:
                existing = json.load(f)

        # Strip any non-year keys (e.g. "total_seasons" from old format)
        existing = {k: v for k, v in existing.items() if str(k).isdigit()}

        # Merge new seasons in (overwrites existing year keys)
        merged  = {**existing, **{k: v for k, v in result.items() if "error" not in v}}
        errors  = {k: v for k, v in result.items() if "error" in v}

        # Sort by year descending
        sorted_merged = dict(sorted(merged.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else -1, reverse=True))

        # Write back
        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        with open(data_path, "w") as f:
            json.dump(sorted_merged, f, indent=2)

        return {
            "status":          "success",
            "years_updated":   [k for k in result if "error" not in result[k]],
            "years_failed":    errors,
            "total_seasons":   len(sorted_merged),
            "file_written":    data_path,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/managers/download")
def download_managers_json():
    """
    Returns the current contents of data/fantasy/managers.json.
    Run this after building up the file via /data/managers?year=
    to get the final JSON to save locally at C:\\bgyfpy\\data\\fantasy\\managers.json
    and commit to git.
    """
    try:
        import json, os
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "fantasy", "managers.json"
        )
        if not os.path.exists(data_path):
            raise HTTPException(
                status_code=404,
                detail="managers.json not found. Run /league/data/managers?year=2025 first."
            )
        with open(data_path) as f:
            data = json.load(f)
        return {
            "total_seasons": len(data),
            "years":         sorted(data.keys(), reverse=True),
            "data":          data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/managers/status")
def managers_json_status():
    """
    Shows which years are in managers.json and which fields are still null.
    Use this to see what still needs to be enriched via the API.
    """
    try:
        import json, os
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "fantasy", "managers.json"
        )
        if not os.path.exists(data_path):
            return {"status": "file_not_found", "years": []}

        with open(data_path) as f:
            data = json.load(f)

        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season   = data[yr]
            managers = season.get("managers", [])
            # A season is enriched if league_url is populated (comes from API)
            # team_name check as secondary signal
            is_enriched = season.get("url") is not None
            enriched_managers = sum(1 for m in managers if m.get("team_name") is not None)
            summary.append({
                "year":             int(yr),
                "num_managers":     len(managers),
                "enriched_managers":enriched_managers,
                "league_enriched":  is_enriched,
                "needs_api_call":   not is_enriched,
                "league_url":       season.get("url"),
                "league_logo":      season.get("logo_url"),
            })

        return {
            "total_seasons":    len(data),
            "fully_enriched":   sum(1 for s in summary if not s["needs_api_call"]),
            "needs_enrichment": [s["year"] for s in summary if s["needs_api_call"]],
            "seasons":          summary,
        }

        return {
            "total_seasons":       len(data),
            "fully_enriched":      sum(1 for s in summary if not s["needs_api_call"]),
            "needs_enrichment":    [s["year"] for s in summary if s["needs_api_call"]],
            "seasons":             summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/managers/build-all")
def build_all_managers(
    skip_existing: bool = Query(default=True, description="Skip years already enriched"),
    force_clean:   bool = Query(default=False, description="Wipe file and rebuild from scratch"),
):
    """
    Runs /league/data/managers for ALL seasons in sequence.
    Enriches managers.json with live Yahoo data for every year.

    WARNING: Slow — makes API calls for each of the 19 seasons.
    Run once to do the full historical build.

    Use skip_existing=true (default) to skip years already enriched,
    so you can safely re-run without overwriting good data.

    Usage:
        GET /league/data/managers/build-all
        GET /league/data/managers/build-all?skip_existing=false
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons,
            get_league_key_for_season,
            _convert_to_dict,
            _safe_get,
        )
        from services.fantasy.team_service import _extract_teams_list
        from services.yahoo_service import get_query
        from config import get_manager_identity
        import json, os

        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "fantasy", "managers.json"
        )

        # Load existing (or wipe if force_clean)
        existing = {}
        if not force_clean and os.path.exists(data_path):
            raw = json.load(open(data_path))
            existing = {k: v for k, v in raw.items() if str(k).isdigit()}

        seasons_data = get_all_seasons()
        all_years    = [str(s["year"]) for s in seasons_data.get("seasons", [])]

        results  = {"success": [], "skipped": [], "failed": {}}

        for yr in sorted(all_years):
            # Skip if already enriched and skip_existing is True
            if skip_existing and yr in existing and existing[yr].get("url") is not None:
                results["skipped"].append(int(yr))
                continue

            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                meta_raw   = query.get_league_metadata()
                meta       = _convert_to_dict(meta_raw)
                # Use get_league_standings — returns full team info
                standings_raw  = query.get_league_standings()
                standings_dict = _convert_to_dict(standings_raw)
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

        # Write merged file sorted newest first — year keys only
        sorted_data = dict(sorted(
            {k: v for k, v in existing.items() if str(k).isdigit()}.items(),
            key=lambda x: int(x[0]), reverse=True
        ))
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
            "next_step":       "Run GET /league/data/managers/download to save locally",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Data generation — results.json
# ---------------------------------------------------------------------------

def _get_data_path(filename: str) -> str:
    """Resolve path to data/fantasy/ relative to project root."""
    import os
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "fantasy", filename
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


def _build_results_for_season(yr: str, query, league_key: str) -> dict:
    """
    Fetch standings + scoreboard for one season.
    Returns dict keyed by manager_id with full regular_season + playoffs blocks.

    All four point dimensions tracked with total, average, and rank:
      points_for, points_against, projected_points_for, projected_points_against
    """
    from services.fantasy.league_service import _convert_to_dict
    from services.fantasy.team_service import (
        _extract_teams_list, _extract_team_standings,
        _extract_outcome_totals, _extract_logo_url,
    )
    from config import get_manager_identity

    # --- Standings ---
    standings_raw  = query.get_league_standings()
    standings_dict = _convert_to_dict(standings_raw)
    teams_list     = _extract_teams_list(standings_dict)

    # Rank maps from standings (regular season totals)
    def _rank_map(field):
        vals = sorted(
            [(t.get("team_key"), float(_extract_team_standings(t).get(field) or 0))
             for t in teams_list if isinstance(t, dict)],
            key=lambda x: x[1], reverse=True
        )
        return {tk: i+1 for i, (tk, _) in enumerate(vals)}

    pf_rank_map = _rank_map("points_for")
    pa_rank_map = _rank_map("points_against")

    # Build initial season_data from standings
    season_data = {}
    team_key_map = {}  # manager_id -> team_key (for scoreboard lookup)

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
        rank   = ts.get("rank")
        seed   = ts.get("playoff_seed")

        season_data[manager_id] = {
            "team_name": t.get("name"),
            "logo_url":  _extract_logo_url(t),
            # Accumulators filled from scoreboard loop below
            "_rs": {
                "wins": wins, "losses": losses, "ties": ties, "games": games,
                "pf": pf, "pa": pa,
                "proj_pf": 0.0, "proj_pa": 0.0,
                "rank": rank, "seed": seed,
            },
            "_pl": {
                "wins": 0, "losses": 0, "ties": 0, "games": 0,
                "pf": 0.0, "pa": 0.0,
                "proj_pf": 0.0, "proj_pa": 0.0,
            },
        }

    # --- Scoreboard loop: projected + playoff splits ---
    try:
        settings_raw  = query.get_league_settings()
        settings_dict = _convert_to_dict(settings_raw)
        playoff_start = int(settings_dict.get("playoff_start_week") or 15)
        end_week      = int(settings_dict.get("end_week") or 17)
    except Exception:
        playoff_start = 15
        end_week      = 17

    for week in range(1, end_week + 1):
        try:
            sb_raw  = query.get_league_scoreboard_by_week(week)
            sb_dict = _convert_to_dict(sb_raw)
            matchups = sb_dict.get("matchups", []) if isinstance(sb_dict, dict) else                        (sb_dict if isinstance(sb_dict, list) else [])

            is_playoff_week = week >= playoff_start

            for m in matchups:
                matchup = m.get("matchup", m) if isinstance(m, dict) else {}
                teams_m = matchup.get("teams", [])
                if isinstance(teams_m, dict):
                    teams_m = list(teams_m.values())

                winner_key = matchup.get("winner_team_key")
                is_tied    = bool(int(matchup.get("is_tied", 0) or 0))

                # Extract points + projected for both teams
                team_pts  = {}
                team_proj = {}
                tkeys     = []

                for tw in teams_m:
                    tm   = tw.get("team", tw) if isinstance(tw, dict) else {}
                    tk   = tm.get("team_key", "")
                    pts  = float((tm.get("team_points") or {}).get("total") or
                                 tm.get("points") or 0)
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

                    # Only count true playoffs (seed 1-4), not consolation (seed 5-8)
                    seed_val = season_data[mid]["_rs"].get("seed")
                    try:
                        is_true_playoff = is_playoff_week and int(seed_val or 99) <= 4
                    except (TypeError, ValueError):
                        is_true_playoff = False

                    if is_true_playoff:
                        b = season_data[mid]["_pl"]
                        b["pf"]      = round(b["pf"]      + my_pts,   2)
                        b["pa"]      = round(b["pa"]      + opp_pts,  2)
                        b["proj_pf"] = round(b["proj_pf"] + my_proj,  2)
                        b["proj_pa"] = round(b["proj_pa"] + opp_proj, 2)
                        b["games"] += 1
                        if is_tied:              b["ties"]   += 1
                        elif winner_key == tk:   b["wins"]   += 1
                        else:                    b["losses"] += 1
                    elif not is_playoff_week:
                        # RS projected (actual RS totals come from standings)
                        b = season_data[mid]["_rs"]
                        b["proj_pf"] = round(b["proj_pf"] + my_proj,  2)
                        b["proj_pa"] = round(b["proj_pa"] + opp_proj, 2)

        except Exception:
            continue

    # --- Build cross-manager rank maps from scoreboard accumulators ---
    def _cross_rank(field, bucket):
        vals = sorted(
            [(mid, d[bucket][field]) for mid, d in season_data.items()],
            key=lambda x: x[1], reverse=True
        )
        return {mid: i+1 for i, (mid, _) in enumerate(vals)}

    rs_proj_pf_rank = _cross_rank("proj_pf", "_rs")
    rs_proj_pa_rank = _cross_rank("proj_pa", "_rs")
    pl_pf_rank      = _cross_rank("pf",      "_pl")
    pl_pa_rank      = _cross_rank("pa",      "_pl")
    pl_proj_pf_rank = _cross_rank("proj_pf", "_pl")
    pl_proj_pa_rank = _cross_rank("proj_pa", "_pl")

    # --- Assemble final output ---
    for mid, d in season_data.items():
        rs = d["_rs"]
        pl = d["_pl"]
        g_rs = rs["games"]
        g_pl = pl["games"]

        # Effective finish
        try:
            r = int(rs["rank"]) if rs["rank"] is not None else None
            s = int(rs["seed"]) if rs["seed"] is not None else None
        except (TypeError, ValueError):
            r = s = None
        if r in (1, 2, 3, 4, 9, 10):   finish = r
        elif s and 5 <= s <= 8:          finish = s
        else:                            finish = r

        d["regular_season"] = {
            "wins":    rs["wins"], "losses": rs["losses"],
            "ties":    rs["ties"], "games":  g_rs,
            "win_pct": round(rs["wins"] / g_rs, 4) if g_rs else None,
            "rank":    rs["rank"], "playoff_seed": rs["seed"],

            "points_for":               round(rs["pf"], 2),
            "points_for_rank":          pf_rank_map.get(team_key_map.get(mid)),
            "avg_points_for":           round(rs["pf"] / g_rs, 2) if g_rs else None,

            "points_against":           round(rs["pa"], 2),
            "points_against_rank":      pa_rank_map.get(team_key_map.get(mid)),
            "avg_points_against":       round(rs["pa"] / g_rs, 2) if g_rs else None,

            "projected_points_for":     round(rs["proj_pf"], 2) if rs["proj_pf"] else None,
            "projected_points_for_rank":rs_proj_pf_rank.get(mid),
            "avg_projected_points_for": round(rs["proj_pf"] / g_rs, 2) if g_rs and rs["proj_pf"] else None,

            "projected_points_against":      round(rs["proj_pa"], 2) if rs["proj_pa"] else None,
            "projected_points_against_rank": rs_proj_pa_rank.get(mid),
            "avg_projected_points_against":  round(rs["proj_pa"] / g_rs, 2) if g_rs and rs["proj_pa"] else None,
        }

        # Only include playoffs block for true playoff teams (seed 1-4)
        try:
            seed_int = int(d["_rs"].get("seed") or 99)
        except (TypeError, ValueError):
            seed_int = 99
        is_playoff_team = seed_int <= 4

        if is_playoff_team and g_pl > 0:
            d["playoffs"] = {
                "made_playoffs": True,
                "finish":        finish,
                "wins":    pl["wins"], "losses": pl["losses"],
                "ties":    pl["ties"], "games":  g_pl,
                "win_pct": round(pl["wins"] / g_pl, 4) if g_pl else None,

                "points_for":               round(pl["pf"], 2),
                "points_for_rank":          pl_pf_rank.get(mid),
                "avg_points_for":           round(pl["pf"] / g_pl, 2),

                "points_against":           round(pl["pa"], 2),
                "points_against_rank":      pl_pa_rank.get(mid),
                "avg_points_against":       round(pl["pa"] / g_pl, 2),

                "projected_points_for":      round(pl["proj_pf"], 2) if pl["proj_pf"] else None,
                "projected_points_for_rank": pl_proj_pf_rank.get(mid),
                "avg_projected_points_for":  round(pl["proj_pf"] / g_pl, 2) if pl["proj_pf"] else None,

                "projected_points_against":      round(pl["proj_pa"], 2) if pl["proj_pa"] else None,
                "projected_points_against_rank": pl_proj_pa_rank.get(mid),
                "avg_projected_points_against":  round(pl["proj_pa"] / g_pl, 2) if pl["proj_pa"] else None,
            }
        else:
            d["playoffs"] = {"made_playoffs": False}

        # Remove internal accumulators
        del d["_rs"]
        del d["_pl"]

    return season_data


@router.get("/data/results/build-all")
def build_results(
    skip_existing: bool = Query(default=True),
    year: str = Query(default=None, description="Single year e.g. '2025', or omit for all"),
    force_clean:   bool = Query(default=False, description="Wipe file and rebuild from scratch"),
):
    """
    Generates results.json — regular season + playoff W-L-T, points, ranks, projected.

    Fetches standings + weekly scoreboard per season.
    Writes to data/fantasy/results.json keyed by year then manager_id.

    Usage:
        GET /league/data/results/build-all              — all seasons
        GET /league/data/results/build-all?year=2025    — single season
        GET /league/data/results/build-all?skip_existing=false — force refresh all
    """
    try:
        from services.fantasy.league_service import get_all_seasons, get_league_key_for_season
        from services.yahoo_service import get_query

        path     = _get_data_path("results.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        # Force full season cache build — ensures all 19 seasons are discoverable
        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])
        target_years = [year] if year else all_years

        results = {"success": [], "skipped": [], "failed": {}}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                # Fetch is_finished flag from metadata
                from services.fantasy.league_service import _convert_to_dict, _safe_get
                meta_raw    = query.get_league_metadata()
                meta        = _convert_to_dict(meta_raw)
                is_finished = bool(int(_safe_get(meta, "is_finished") or 0))

                season_data = _build_results_for_season(yr, query, league_key)
                existing[yr] = {
                    "is_finished": is_finished,
                    "managers":    season_data,
                }
                results["success"].append(int(yr))
            except Exception as e:
                results["failed"][yr] = str(e)

        sorted_data = dict(sorted(existing.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else -1, reverse=True))
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
            season      = data[yr]
            is_finished = season.get("is_finished")
            mgr_data    = season.get("managers", season)  # handle both old and new shape
            managers    = [k for k in mgr_data if k != "is_finished"]
            enriched    = sum(
                1 for m in mgr_data.values()
                if isinstance(m, dict) and m.get("regular_season", {}).get("points_for")
            )
            summary.append({
                "year":         int(yr),
                "is_finished":  is_finished,
                "num_managers": len(managers),
                "enriched":     enriched,
                "needs_refresh":enriched < len(managers),
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
        path = _get_data_path("results.json")
        data = _load_json(path)
        if not data:
            raise HTTPException(status_code=404, detail="results.json not found.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Data generation — transactions.json (trades + moves/FAAB)
# ---------------------------------------------------------------------------


def _build_week_map(query, yr: str) -> list:
    """Build week->date range map for a season using game weeks API."""
    from services.fantasy.league_service import _convert_to_dict
    try:
        league_key = query.league_key if hasattr(query, 'league_key') else ""
        game_id    = str(league_key).split(".")[0] if league_key else None
        if not game_id:
            return []
        raw   = query.get_game_weeks_by_game_id(game_id)
        data  = _convert_to_dict(raw)
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
    """Map a YYYY-MM-DD date to its season week number."""
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
    year: str = Query(default=None, description="Single year e.g. '2025', or omit for all"),
    force_clean:   bool = Query(default=False, description="Wipe file and rebuild from scratch"),
):
    """
    Generates transactions.json — trades and waiver/FA moves per season.

    Keyed by year: {"2025": {"trades": [...], "moves": [...]}}

    Usage:
        GET /league/data/transactions/build-all
        GET /league/data/transactions/build-all?year=2025
    """
    try:
        from services.fantasy.league_service import get_all_seasons, get_league_key_for_season, _convert_to_dict
        from services.yahoo_service import get_query
        from config import get_manager_identity

        path     = _get_data_path("transactions.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        # Force full season cache build — ensures all 19 seasons are discoverable
        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])
        target_years = [year] if year else all_years

        import datetime

        results = {"success": [], "skipped": [], "failed": {}}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)
                week_map   = _build_week_map(query, yr)

                tx_raw  = query.get_league_transactions()
                tx_dict = _convert_to_dict(tx_raw)
                tx_list = tx_dict if isinstance(tx_dict, list) else                           tx_dict.get("transactions", [])

                trades = []
                moves  = []

                def _ts_to_date(ts):
                    """Convert unix timestamp to readable date string."""
                    try:
                        return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
                    except (TypeError, ValueError):
                        return None

                def _player_info(pw):
                    """Extract name, position, player_key from a player wrapper."""
                    p  = pw.get("player", pw) if isinstance(pw, dict) else {}
                    td = p.get("transaction_data", {})
                    if isinstance(td, list): td = td[0] if td else {}
                    return {
                        "name":       p.get("full_name") or p.get("name", "Unknown"),
                        "position":   p.get("display_position") or p.get("primary_position"),
                        "player_key": p.get("player_key"),
                        "td":         td,
                    }

                for item in tx_list:
                    # YFPY returns flat transaction objects (no "transaction" wrapper)
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

                    # players is a list of {"player": {...}} objects
                    players_raw = tx.get("players", [])
                    if isinstance(players_raw, dict):
                        players_raw = list(players_raw.values())

                    def _extract_player(pw):
                        """Extract player fields from {"player": {...}} wrapper."""
                        p  = pw.get("player", pw) if isinstance(pw, dict) else {}
                        td = p.get("transaction_data", {})
                        if isinstance(td, list): td = td[0] if td else {}
                        # name can be a nested object or flat string
                        name_raw = p.get("name", {})
                        if isinstance(name_raw, dict):
                            name = name_raw.get("full") or p.get("full_name", "Unknown")
                        else:
                            name = p.get("full_name") or str(name_raw) or "Unknown"
                        return {
                            "name":       name,
                            "position":   p.get("display_position") or p.get("primary_position"),
                            "player_key": p.get("player_key"),
                            "td":         td,
                        }

                    if ttype == "trade":
                        trader_tk = tx.get("trader_team_key", "")
                        tradee_tk = tx.get("tradee_team_key", "")
                        ti_a = get_manager_identity(team_key=trader_tk)
                        ti_b = get_manager_identity(team_key=tradee_tk)
                        mgr_a = ti_a["manager_id"] if ti_a else trader_tk
                        mgr_b = ti_b["manager_id"] if ti_b else tradee_tk

                        a_received = []
                        b_received = []

                        for pw in players_raw:
                            pi      = _extract_player(pw)
                            dest_tk = pi["td"].get("destination_team_key", "")
                            entry   = {
                                "name":       pi["name"],
                                "position":   pi["position"],
                                "player_key": pi["player_key"],
                            }
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

                    elif ttype in ("add", "drop", "add/drop", "waiver", "free agent"):
                        added   = []
                        dropped = []

                        for pw in players_raw:
                            pi        = _extract_player(pw)
                            move_type = pi["td"].get("type", "")
                            entry     = {
                                "name":       pi["name"],
                                "position":   pi["position"],
                                "player_key": pi["player_key"],
                            }
                            if move_type == "add":
                                added.append({**entry,
                                    "source_type": pi["td"].get("source_type", "")})
                            elif move_type == "drop":
                                dropped.append(entry)

                        # Resolve manager from first add, fall back to first drop
                        team_key = None
                        for pw in players_raw:
                            pi = _extract_player(pw)
                            mt = pi["td"].get("type", "")
                            if mt == "add":
                                team_key = pi["td"].get("destination_team_key", "")
                                break
                            elif mt == "drop":
                                team_key = pi["td"].get("source_team_key", "")
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

        sorted_data = dict(sorted(existing.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else -1, reverse=True))
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
                "year":        int(yr),
                "trades":      len(season.get("trades", [])),
                "moves":       len(season.get("moves", [])),
                "has_data":    bool(season.get("trades") or season.get("moves")),
            })
        return {
            "total_seasons": len(data),
            "seasons":       summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/transactions/download")
def download_transactions():
    """Returns current transactions.json for local save."""
    try:
        path = _get_data_path("transactions.json")
        data = _load_json(path)
        if not data:
            raise HTTPException(status_code=404, detail="transactions.json not found.")
        return {"total_seasons": len(data), "years": sorted(data.keys(), reverse=True), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Data generation — drafts.json
# ---------------------------------------------------------------------------

@router.get("/data/drafts/build-all")
def build_drafts(
    skip_existing: bool = Query(default=True),
    year: str = Query(default=None, description="Single year e.g. '2025', or omit for all"),
    force_clean:   bool = Query(default=False, description="Wipe file and rebuild from scratch"),
):
    """
    Generates drafts.json — full draft board per season.

    For each pick stores: round, pick number, overall pick, manager,
    player name, position, player_key, and auction cost (if applicable).

    Snake drafts: cost = null
    Auction drafts: cost = dollars spent (2023+)

    Keyed by year: {"2025": {"draft_type": "auction", "picks": [...]}}

    Usage:
        GET /league/data/drafts/build-all
        GET /league/data/drafts/build-all?year=2025
        GET /league/data/drafts/build-all?skip_existing=false
    """
    try:
        from services.fantasy.league_service import (
            get_all_seasons, get_league_key_for_season, _convert_to_dict, _safe_get
        )
        from services.yahoo_service import get_query
        from config import get_manager_identity

        path     = _get_data_path("drafts.json")
        existing = {} if force_clean else {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        seasons_data = get_all_seasons(force_refresh=True)
        all_years    = sorted([str(s["year"]) for s in seasons_data.get("seasons", [])])
        target_years = [year] if year else all_years

        results = {"success": [], "skipped": [], "failed": {}}

        for yr in target_years:
            if skip_existing and yr in existing and existing[yr]:
                results["skipped"].append(int(yr))
                continue
            try:
                league_key = get_league_key_for_season(yr)
                query      = get_query(league_key)

                # Get draft type from settings
                try:
                    settings_raw  = query.get_league_settings()
                    settings_dict = _convert_to_dict(settings_raw)
                    is_auction    = bool(int(settings_dict.get("is_auction_draft") or 0))
                    draft_type    = "auction" if is_auction else "snake"
                except Exception:
                    draft_type = "unknown"
                    is_auction = False

                # Get draft results
                draft_raw  = query.get_league_draft_results()
                draft_dict = _convert_to_dict(draft_raw)
                # YFPY returns flat draft pick objects with fields:
                # pick, round, cost, team_key, player_key — no wrapper, no player names
                picks_raw = draft_dict if isinstance(draft_dict, list) else \
                            draft_dict.get("draft_results", [])

                picks = []
                for item in picks_raw:
                    p          = item if isinstance(item, dict) else {}
                    team_key   = p.get("team_key", "")
                    pick_num   = p.get("pick")
                    round_num  = p.get("round")
                    cost       = p.get("cost")
                    player_key = p.get("player_key", "")

                    if not team_key and not player_key:
                        continue

                    identity     = get_manager_identity(team_key=team_key)
                    manager_id   = identity["manager_id"]   if identity else None
                    display_name = identity["display_name"] if identity else team_key

                    try:
                        cost_int = int(cost) if cost is not None else None
                    except (TypeError, ValueError):
                        cost_int = None

                    picks.append({
                        "overall_pick": int(pick_num)  if pick_num  else None,
                        "round":        int(round_num) if round_num else None,
                        "manager_id":   manager_id,
                        "display_name": display_name,
                        "player_key":   player_key,
                        "player_name":  None,  # not in draft API response
                        "position":     None,  # not in draft API response
                        "cost":         cost_int,
                    })

                # Sort by overall pick number
                picks.sort(key=lambda x: x.get("overall_pick") or 9999)

                existing[yr] = {
                    "year":       int(yr),
                    "draft_type": draft_type,
                    "total_picks":len(picks),
                    "picks":      picks,
                }
                results["success"].append(int(yr))

            except Exception as e:
                results["failed"][yr] = str(e)

        sorted_data = dict(sorted(existing.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else -1, reverse=True))
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


@router.get("/data/drafts/status")
def drafts_status():
    """Shows which years are in drafts.json and draft type per season."""
    try:
        path = _get_data_path("drafts.json")
        data = _load_json(path)
        if not data:
            return {"status": "file_not_found", "years": []}

        summary = []
        for yr in sorted(data.keys(), reverse=True):
            season = data[yr]
            picks  = season.get("picks", [])
            has_player_names = sum(1 for p in picks if p.get("player_name"))
            summary.append({
                "year":             int(yr),
                "draft_type":       season.get("draft_type"),
                "total_picks":      len(picks),
                "picks_with_names": has_player_names,
                "needs_refresh":    has_player_names < len(picks) // 2 if picks else True,
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
        path = _get_data_path("drafts.json")
        data = _load_json(path)
        if not data:
            raise HTTPException(status_code=404, detail="drafts.json not found.")
        return {
            "total_seasons": len(data),
            "years":         sorted(data.keys(), reverse=True),
            "data":          data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Data generation — punishment.json
# ---------------------------------------------------------------------------

@router.get("/data/punishment/build")
def build_punishment():
    """
    Generates punishment.json from SEASON_HISTORY_MANUAL in config.py.

    Structure: {"2025": {"punishment": "..."}, "2024": {...}}

    Loser is NOT stored here — derive it at runtime from results.json
    where rank == 10 for completed seasons.

    Run this once to seed the file. After that, update punishment.json
    directly via the commissioner UI or by editing the file manually.

    Usage:
        GET /league/data/punishment/build
    """
    try:
        from config import get_all_manual_history

        path     = _get_data_path("punishment.json")
        existing = {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        manual = get_all_manual_history()

        for yr, data in manual.items():
            yr_str = str(yr)
            punishment = data.get("punishment")

            # Only add if not already in file (don't overwrite manual edits)
            if yr_str not in existing:
                existing[yr_str] = {
                    "year":       yr,
                    "punishment": punishment,
                }
            else:
                # Update punishment text only if config has one and file doesn't
                if punishment and not existing[yr_str].get("punishment"):
                    existing[yr_str]["punishment"] = punishment

        sorted_data = dict(sorted(existing.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else -1, reverse=True))
        _write_json(path, sorted_data)

        populated   = sum(1 for v in sorted_data.values() if v.get("punishment"))
        unpopulated = [k for k, v in sorted_data.items() if not v.get("punishment")]

        return {
            "status":       "complete",
            "total_seasons":len(sorted_data),
            "populated":    populated,
            "missing":      unpopulated,
            "file_written": path,
            "next_step":    "GET /league/data/punishment/download to save locally",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/punishment/update")
def update_punishment(
    year: int = Query(..., description="Season year e.g. 2026"),
    punishment: str = Query(..., description="Punishment text for the loser"),
    user: dict = Depends(require_permission("edit_settings")),
):
    """
    Commissioner/app owner endpoint — add or update punishment for a season.

    Protected: requires commissioner or app_owner role.

    Usage:
        POST /league/data/punishment/update?year=2026&punishment=Loser+does+X
        Authorization: Bearer <jwt>
    """
    try:
        path     = _get_data_path("punishment.json")
        existing = {k: v for k, v in _load_json(path).items() if str(k).isdigit()}

        yr_str = str(year)
        existing[yr_str] = {
            "year":        year,
            "punishment":  punishment,
            "updated_by":  user.get("display_name"),
            "updated_at":  __import__("datetime").datetime.utcnow().isoformat(),
        }

        sorted_data = dict(sorted(existing.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else -1, reverse=True))
        _write_json(path, sorted_data)

        return {
            "status":     "updated",
            "year":       year,
            "punishment": punishment,
            "updated_by": user.get("display_name"),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/punishment/download")
def download_punishment():
    """Returns current punishment.json for local save."""
    try:
        path = _get_data_path("punishment.json")
        data = _load_json(path)
        if not data:
            raise HTTPException(status_code=404, detail="punishment.json not found. Run /league/data/punishment/build first.")
        return {
            "total_seasons": len(data),
            "years":         sorted(data.keys(), reverse=True),
            "data":          data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))