from fastapi import APIRouter, HTTPException
from services.league_service import (
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
        from services.league_service import get_league_standings
        
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
        from services.league_service import get_league_rules
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
        from services.league_service import (
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
        from services.league_service import (
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