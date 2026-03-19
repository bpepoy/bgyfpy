from fastapi import APIRouter, HTTPException, Query
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

        seasons_data = get_all_seasons()
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

                # Teams + manager info
                teams_raw  = query.get_league_teams()
                teams_dict = _convert_to_dict(teams_raw)
                teams_list = _extract_teams_list(teams_dict)

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
                    "year":       int(yr),
                    "league_key": league_key,
                    "league_id":  _safe_get(meta, "league_id") or league_key.split(".l.")[-1],
                    "league_name":_safe_get(meta, "name") or "BlackGold",
                    "url":        _safe_get(meta, "url"),
                    "logo_url":   _safe_get(meta, "logo_url"),
                    "num_teams":  _safe_get(meta, "num_teams"),
                    "season":     _safe_get(meta, "season"),
                    "managers":   managers,
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

        # Merge new seasons in (overwrites existing year keys)
        merged  = {**existing, **{k: v for k, v in result.items() if "error" not in v}}
        errors  = {k: v for k, v in result.items() if "error" in v}

        # Sort by year descending
        sorted_merged = dict(sorted(merged.items(), key=lambda x: int(x[0]), reverse=True))

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
            enriched = sum(1 for m in managers if m.get("team_name") is not None)
            summary.append({
                "year":            int(yr),
                "num_managers":    len(managers),
                "enriched":        enriched,
                "needs_api_call":  enriched < len(managers),
                "league_url":      season.get("url"),
                "league_logo":     season.get("logo_url"),
            })

        return {
            "total_seasons":       len(data),
            "fully_enriched":      sum(1 for s in summary if not s["needs_api_call"]),
            "needs_enrichment":    [s["year"] for s in summary if s["needs_api_call"]],
            "seasons":             summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))