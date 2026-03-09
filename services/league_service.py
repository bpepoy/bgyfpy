from services.yahoo_service import get_query
import time

# Season mapping cache with timestamp
_season_cache = None
_cache_timestamp = None


def get_all_seasons(force_refresh=False):
    """
    Discover all seasons by following renew chain backwards AND renewed chain forwards.
    Automatically detects new seasons without code changes.
    
    Args:
        force_refresh: Force refresh of cached data
    
    Returns:
        dict: Complete season mapping with normalized names
    """
    global _season_cache, _cache_timestamp
    
    from config import LEAGUE_CONFIG, get_known_league_key, get_known_season_year, get_first_season
    
    # Check if cache is still valid
    cache_duration = LEAGUE_CONFIG["cache_duration_hours"] * 3600
    if not force_refresh and _season_cache and _cache_timestamp:
        if time.time() - _cache_timestamp < cache_duration:
            return _season_cache
    
    seasons = {}
    
    # Start from known league key
    starting_key = get_known_league_key()
    starting_year = get_known_season_year()
    
    # Parse the starting league key
    parts = starting_key.split(".")
    if len(parts) == 3:
        starting_game_id = int(parts[0])
        starting_league_id = parts[2]
    else:
        raise Exception(f"Invalid league key format: {starting_key}")
    
    # Add the starting season
    try:
        query = get_query(starting_key)
        raw = query.get_league_metadata()
        raw_dict = _convert_to_dict(raw)
        
        seasons[starting_year] = {
            "year": starting_year,
            "game_id": starting_game_id,
            "league_id": starting_league_id,
            "league_key": starting_key,
            "renew": _safe_get(raw_dict, "renew"),
            "renewed": _safe_get(raw_dict, "renewed"),
        }
        
        # Normalize the name
        seasons[starting_year] = _normalize_season_data(seasons[starting_year], raw_dict)
        
    except Exception as e:
        print(f"Error fetching starting season {starting_year}: {str(e)}")
    
    # Follow the chain BACKWARDS (older seasons)
    _follow_chain_backwards(seasons, starting_year, get_first_season())
    
    # Follow the chain FORWARDS (newer seasons) - This catches 2026+
    _follow_chain_forwards(seasons, starting_year)
    
    # Find the current (latest) season
    current_year = max(seasons.keys()) if seasons else starting_year
    
    # Convert to sorted list
    seasons_list = []
    for year in sorted(seasons.keys(), reverse=True):
        season = seasons[year]
        season["is_current"] = (year == current_year)
        seasons_list.append(season)
    
    result = {
        "league_name": LEAGUE_CONFIG["name"],
        "current_season": current_year,
        "seasons": seasons_list,
        "total_seasons": len(seasons_list),
        "cached_at": time.time()
    }
    
    # Update cache
    _season_cache = result
    _cache_timestamp = time.time()
    
    return result


def _follow_chain_backwards(seasons, start_year, first_season):
    """
    Follow the renew chain backwards to find older seasons.
    Falls back to manual mapping if renew chain breaks.
    
    Args:
        seasons: Dict to populate with season data
        start_year: Year to start from
        first_season: Earliest possible season year
    """
    from config import get_manual_season_mapping
    
    current_year = start_year - 1
    
    # Get the renew field from the starting season
    if start_year in seasons and seasons[start_year]["renew"]:
        renew_value = seasons[start_year]["renew"]
    else:
        renew_value = None
    
    while current_year >= first_season:
        # If renew chain is broken, check manual mapping
        if not renew_value:
            manual_mapping = get_manual_season_mapping()
            if current_year in manual_mapping:
                print(f"✅ Using manual mapping for {current_year}")
                
                game_id = manual_mapping[current_year]["game_id"]
                league_id = manual_mapping[current_year]["league_id"]
                league_key = f"{game_id}.l.{league_id}"
                
                try:
                    # Fetch this season's data
                    query = get_query(league_key)
                    raw = query.get_league_metadata()
                    raw_dict = _convert_to_dict(raw)
                    
                    seasons[current_year] = {
                        "year": current_year,
                        "game_id": game_id,
                        "league_id": league_id,
                        "league_key": league_key,
                        "renew": _safe_get(raw_dict, "renew"),
                        "renewed": _safe_get(raw_dict, "renewed"),
                    }
                    
                    # Normalize the name
                    seasons[current_year] = _normalize_season_data(seasons[current_year], raw_dict)
                    
                    # Continue to next year
                    current_year -= 1
                    
                    # Check if this season has a renew value to continue the chain
                    if seasons.get(current_year + 1, {}).get("renew"):
                        renew_value = seasons[current_year + 1]["renew"]
                    else:
                        renew_value = None
                    
                    continue
                    
                except Exception as e:
                    print(f"❌ Error fetching manually mapped season {current_year}: {str(e)}")
                    current_year -= 1
                    continue
            else:
                # No manual mapping and no renew - stop here
                print(f"⛔ Renew chain broken at {current_year + 1}, no manual mapping available for {current_year}")
                break
        
        # Normal renew chain processing
        try:
            # Parse renew field (format: "game_id_league_id")
            parts = str(renew_value).split("_")
            if len(parts) != 2:
                # Try manual mapping if parse fails
                print(f"⚠️ Failed to parse renew value: {renew_value}")
                renew_value = None
                continue
            
            game_id = int(parts[0])
            league_id = parts[1]
            league_key = f"{game_id}.l.{league_id}"
            
            # Fetch this season's data
            query = get_query(league_key)
            raw = query.get_league_metadata()
            raw_dict = _convert_to_dict(raw)
            
            seasons[current_year] = {
                "year": current_year,
                "game_id": game_id,
                "league_id": league_id,
                "league_key": league_key,
                "renew": _safe_get(raw_dict, "renew"),
                "renewed": _safe_get(raw_dict, "renewed"),
            }
            
            # Normalize the name
            seasons[current_year] = _normalize_season_data(seasons[current_year], raw_dict)
            
            # Get the next renew value for the previous year
            renew_value = seasons[current_year]["renew"]
            current_year -= 1
            
        except Exception as e:
            print(f"❌ Error fetching season {current_year}: {str(e)}")
            # Try manual mapping on error
            renew_value = None


def _follow_chain_forwards(seasons, start_year):
    """
    Follow the renewed chain forwards to find newer seasons.
    This automatically discovers 2026, 2027, etc. when they become available.
    
    Args:
        seasons: Dict to populate with season data
        start_year: Year to start from
    """
    current_year = start_year + 1
    max_future_years = 5  # Don't check more than 5 years into future
    
    # Get the renewed field from the starting season
    if start_year in seasons and seasons[start_year].get("renewed"):
        renewed_value = seasons[start_year]["renewed"]
    else:
        # No renewed field yet - try to detect by game_id increment
        if start_year in seasons:
            next_game_id = seasons[start_year]["game_id"] + 1
            # Try the same league ID (often stays consistent)
            possible_id = seasons[start_year]["league_id"]
            
            try:
                test_key = f"{next_game_id}.l.{possible_id}"
                query = get_query(test_key)
                raw = query.get_league_metadata()
                raw_dict = _convert_to_dict(raw)
                
                # Check if this is actually the next season
                season_year = _safe_get(raw_dict, "season")
                if season_year == current_year:
                    seasons[current_year] = {
                        "year": current_year,
                        "game_id": next_game_id,
                        "league_id": possible_id,
                        "league_key": test_key,
                        "renew": _safe_get(raw_dict, "renew"),
                        "renewed": _safe_get(raw_dict, "renewed"),
                    }
                    
                    # Normalize the name
                    seasons[current_year] = _normalize_season_data(seasons[current_year], raw_dict)
                    
                    print(f"✅ Auto-discovered new season: {current_year}")
            except Exception as e:
                print(f"No future season found for {current_year}: {str(e)}")
        
        return
    
    # If there's a renewed field, follow it
    while current_year <= start_year + max_future_years and renewed_value:
        try:
            # Parse renewed field (format similar to renew)
            parts = str(renewed_value).split("_")
            if len(parts) != 2:
                break
            
            game_id = int(parts[0])
            league_id = parts[1]
            league_key = f"{game_id}.l.{league_id}"
            
            # Fetch this season's data
            query = get_query(league_key)
            raw = query.get_league_metadata()
            raw_dict = _convert_to_dict(raw)
            
            seasons[current_year] = {
                "year": current_year,
                "game_id": game_id,
                "league_id": league_id,
                "league_key": league_key,
                "renew": _safe_get(raw_dict, "renew"),
                "renewed": _safe_get(raw_dict, "renewed"),
            }
            
            # Normalize the name
            seasons[current_year] = _normalize_season_data(seasons[current_year], raw_dict)
            
            # Get the next renewed value for the next year
            renewed_value = seasons[current_year].get("renewed")
            current_year += 1
            
        except Exception as e:
            print(f"No future season found for {current_year}: {str(e)}")
            break


def _normalize_season_data(season_dict, raw_dict):
    """
    Normalize season data with consistent "BlackGold" naming.
    
    Args:
        season_dict: Season data being built
        raw_dict: Raw Yahoo API response
    
    Returns:
        dict: Normalized season data
    """
    from config import get_league_name
    
    # Get the original name from Yahoo
    original_name = _safe_get(raw_dict, "name")
    
    # Always use "BlackGold" as the display name
    season_dict["name"] = get_league_name()
    
    # Keep original name for reference if different
    if original_name and original_name != get_league_name():
        season_dict["original_name"] = original_name
    
    return season_dict


def _convert_to_dict(raw):
    """Convert YFPY object to dict"""
    if hasattr(raw, 'to_json'):
        raw_dict = raw.to_json()
    elif hasattr(raw, '__dict__'):
        raw_dict = raw.__dict__
    else:
        raw_dict = raw
    
    if isinstance(raw_dict, str):
        import json
        raw_dict = json.loads(raw_dict)
    
    return raw_dict


def get_current_season():
    """
    Get the current (latest) season year.
    Auto-discovers new seasons.
    """
    seasons_data = get_all_seasons()
    return seasons_data["current_season"]


def get_league_key_for_season(year: str):
    """
    Get the league key for a specific season year.
    
    Args:
        year: Season year as string (e.g., "2024")
    
    Returns:
        str: League key for that season
    """
    # Get all seasons (will auto-discover new ones)
    seasons_data = get_all_seasons()
    
    # Find the matching year
    year_int = int(year)
    for season in seasons_data["seasons"]:
        if season["year"] == year_int:
            return season["league_key"]
    
    raise Exception(f"Season {year} not found for this league")


def get_league_settings(league_id: str):
    """
    Fetches league settings/metadata from Yahoo Fantasy Sports.
    
    Args:
        league_id: League ID (numeric like "501623" or full key like "461.l.501623")
    
    Returns:
        dict: Normalized league settings with "BlackGold" name
    """
    try:
        from config import get_league_name
        
        query = get_query(league_id)
        raw = query.get_league_metadata()
        raw_dict = _convert_to_dict(raw)
        
        # Get original name from Yahoo
        original_name = _safe_get(raw_dict, "name")
        
        # Parse renew field for historical data tracking
        renew_data = _parse_renew_field(_safe_get(raw_dict, "renew"))
        
        # Normalize the Yahoo response into clean, frontend-friendly JSON
        settings = {
            # Basic Info
            "league_id": league_id,
            "league_key": _safe_get(raw_dict, "league_key"),
            "name": get_league_name(),  # Always "BlackGold"
            "season": _safe_get(raw_dict, "season"),
            "game_code": _safe_get(raw_dict, "game_code"),
            
            # League Type & Status
            "league_type": _safe_get(raw_dict, "league_type"),  # public/private
            "is_cash_league": bool(_safe_get(raw_dict, "is_cash_league", 0)),
            "is_finished": bool(_safe_get(raw_dict, "is_finished", 0)),
            "felo_tier": _safe_get(raw_dict, "felo_tier"),  # bronze/silver/gold/platinum
            
            # Teams & Roster
            "num_teams": _safe_get(raw_dict, "num_teams"),
            "roster_type": _safe_get(raw_dict, "roster_type"),  # week/season
            
            # Scoring
            "scoring_type": _safe_get(raw_dict, "scoring_type"),  # head/point
            
            # Schedule
            "start_week": _safe_get(raw_dict, "start_week"),
            "end_week": _safe_get(raw_dict, "end_week"),
            "current_week": _safe_get(raw_dict, "current_week"),
            "matchup_week": _safe_get(raw_dict, "matchup_week"),
            "start_date": _safe_get(raw_dict, "start_date"),
            "end_date": _safe_get(raw_dict, "end_date"),
            
            # Draft
            "draft_status": _safe_get(raw_dict, "draft_status"),
            
            # Links & Media
            "url": _safe_get(raw_dict, "url"),
            "logo_url": _safe_get(raw_dict, "logo_url"),
            
            # Historical Data Tracking
            "previous_season": renew_data,  # Link to previous season
            
            # Metadata
            "league_update_timestamp": _safe_get(raw_dict, "league_update_timestamp"),
            
            # Optional Features
            "is_plus_league": bool(_safe_get(raw_dict, "is_plus_league", 0)),
            "is_pro_league": bool(_safe_get(raw_dict, "is_pro_league", 0)),
        }
        
        # Add original name if different
        if original_name and original_name != get_league_name():
            settings["original_name"] = original_name
        
        return settings
        
    except Exception as e:
        raise Exception(f"Failed to fetch league settings: {str(e)}")

def get_league_standings(league_id: str):
    """
    Fetches league standings from Yahoo Fantasy Sports.
    
    Args:
        league_id: League ID (numeric like "501623" or full key like "461.l.501623")
    
    Returns:
        dict: Standings with team records and rankings
    """
    try:
        from config import get_league_name
        
        query = get_query(league_id)
        standings_data = query.get_league_standings()
        
        # Convert to dict
        standings_dict = _convert_to_dict(standings_data)
        
        # Extract teams array
        teams_array = standings_dict.get("teams", [])
        
        teams = []
        
        for team_wrapper in teams_array:
            # Each item is {"team": {...}}
            team_dict = team_wrapper.get("team", {})
            
            # Extract manager info
            managers_data = team_dict.get("managers", {})
            manager_dict = managers_data.get("manager", {})
            
            # Extract team standings
            team_standings = team_dict.get("team_standings", {})
            outcome_totals = team_standings.get("outcome_totals", {})
            
            # Extract team logo
            team_logos = team_dict.get("team_logos", {})
            team_logo = team_logos.get("team_logo", {})
            
            # Build clean team info
            team_info = {
            "team_id": team_dict.get("team_id"),
            "team_key": team_dict.get("team_key"),
            "name": team_dict.get("name"),
            "rank": team_standings.get("rank"),
            "playoff_seed": team_standings.get("playoff_seed"),

            # Record
            "wins": outcome_totals.get("wins"),
            "losses": outcome_totals.get("losses"),
            "ties": outcome_totals.get("ties"),
            "percentage": outcome_totals.get("percentage"),

            # Points
            "points_for": team_standings.get("points_for"),
            "points_against": team_standings.get("points_against"),

            # Manager
            "manager_nickname": manager_dict.get("nickname"),
            "manager_guid": manager_dict.get("guid"),
            "manager_felo_score": manager_dict.get("felo_score"),
            "manager_felo_tier": manager_dict.get("felo_tier"),

            # Additional info
            "clinched_playoffs": bool(team_dict.get("clinched_playoffs", 0)),
            "number_of_moves": team_dict.get("number_of_moves"),
            "number_of_trades": team_dict.get("number_of_trades"),
            "team_logo_url": team_logo.get("url"),
            "url": team_dict.get("url"),

            # Streak
            "streak_type": team_standings.get("streak", {}).get("type"),
            "streak_value": team_standings.get("streak", {}).get("value"),
        }

            # Add consistent manager identity
            from config import get_manager_identity

            manager_identity = get_manager_identity(
            team_key=team_info["team_key"],
            manager_guid=team_info.get("manager_guid")
            )

            if manager_identity:
                team_info["manager_id"] = manager_identity["manager_id"]
                team_info["manager_display_name"] = manager_identity["display_name"]
            else:
                # Fallback if not in map (unknown manager)
                team_info["manager_id"] = None
                team_info["manager_display_name"] = manager_dict.get("nickname")

            teams.append(team_info)
        
        # Sort by rank
        # Sort teams with proper logic:
        # 1. Teams with playoff_seed 1-4: sort by rank (playoff results)
        # 2. Teams with playoff_seed 5+: sort by playoff_seed (regular season)
        # 3. Teams with no playoff_seed: sort by rank
        def sort_key(team):
            seed = team.get("playoff_seed")
            rank = team.get("rank")
            
            if seed is not None:
                if seed <= 4:
                    # Top 4 playoff teams - sort by rank (championship results)
                    return (0, rank if rank else 999, 0)
                else:
                    # Seeds 5+ - sort by playoff_seed (regular season)
                    return (1, seed, 0)
            else:
                # No playoff seed - sort by rank (non-playoff teams)
                return (2, rank if rank else 999, 0)
        
        teams.sort(key=sort_key)
        
        # Add a "display_rank" field based on the corrected sort order
        for idx, team in enumerate(teams, start=1):
            team["display_rank"] = idx
        
        # Get league metadata for context
        league_metadata = query.get_league_metadata()
        league_dict = _convert_to_dict(league_metadata)
        
        result = {
            "league_id": league_id,
            "league_key": _safe_get(league_dict, "league_key"),
            "league_name": get_league_name(),
            "season": _safe_get(league_dict, "season"),
            "num_teams": _safe_get(league_dict, "num_teams"),
            "standings": teams
        }
        
        return result
        
    except Exception as e:
        raise Exception(f"Failed to fetch league standings: {str(e)}")

def _safe_get(data, key, default=None):
    """
    Safely get a value from dict or object.
    
    Args:
        data: Dictionary or object
        key: Key/attribute name
        default: Default value if key not found
    
    Returns:
        Value or default
    """
    if isinstance(data, dict):
        return data.get(key, default)
    else:
        return getattr(data, key, default)


def _parse_renew_field(renew_value):
    """
    Parse the 'renew' field to extract previous season info.
    Format is typically "game_id_league_id" (e.g., "449_150305")
    
    Args:
        renew_value: Raw renew field value
    
    Returns:
        dict: Parsed previous season data or None
    """
    if not renew_value:
        return None
    
    try:
        parts = str(renew_value).split("_")
        if len(parts) == 2:
            return {
                "game_id": int(parts[0]),
                "league_id": parts[1],
                "league_key": f"{parts[0]}.l.{parts[1]}"
            }
    except:
        pass
    
    return {"raw": renew_value}

def get_league_rules():
    """
    Get current season league ruleset: identity, draft, waivers, schedule,
    scoring, roster, and payment structure.

    Always uses the CURRENT season's data — never a previous season.
    The current season is auto-discovered via the renew/renewed chain.

    Returns:
        dict: Structured league ruleset for the current season
    """
    try:
        from config import get_payment_rules, get_league_name, get_founded_year
        import datetime

        # Always resolve the current season dynamically
        current_year = get_current_season()
        league_key = get_league_key_for_season(str(current_year))

        query = get_query(league_key)

        # Two API calls: metadata (identity/schedule) + settings (rules)
        settings = query.get_league_settings()
        settings_dict = _convert_to_dict(settings)

        metadata = query.get_league_metadata()
        metadata_dict = _convert_to_dict(metadata)

        founded = get_founded_year()
        current_calendar_year = datetime.datetime.now().year
        years_active = current_calendar_year - founded + 1

        return {
            "league": _parse_league_identity(metadata_dict, settings_dict, founded, years_active),
            "draft": _parse_draft_settings(settings_dict),
            "waivers": _parse_waiver_settings(settings_dict),
            "schedule": _parse_schedule_settings(settings_dict),
            "scoring": _parse_scoring_rules(settings_dict),
            "roster": _parse_roster_settings(settings_dict),
            "payment": get_payment_rules(),
        }

    except Exception as e:
        raise Exception(f"Failed to fetch league rules: {str(e)}")


def _parse_league_identity(metadata_dict, settings_dict, founded, years_active):
    """League identity block — combines metadata + settings top-level fields."""
    return {
        "name": _safe_get(metadata_dict, "name") or _safe_get(settings_dict, "name"),
        "season": _safe_get(metadata_dict, "season"),
        "founded": founded,
        "years_active": years_active,
        "num_teams": _safe_get(metadata_dict, "num_teams"),
        "scoring_type": _safe_get(metadata_dict, "scoring_type"),
        "league_type": _safe_get(metadata_dict, "league_type"),
        "felo_tier": _safe_get(metadata_dict, "felo_tier"),
        "is_finished": bool(_safe_get(metadata_dict, "is_finished", 0)),
        "current_week": _safe_get(metadata_dict, "current_week"),
        "start_date": _safe_get(metadata_dict, "start_date"),
        "end_date": _safe_get(metadata_dict, "end_date"),
        "url": _safe_get(metadata_dict, "url"),
        "logo_url": _safe_get(metadata_dict, "logo_url"),
    }


def _parse_draft_settings(settings_dict):
    """Draft configuration block."""
    is_auction = settings_dict.get("is_auction_draft") == 1
    draft_type_raw = settings_dict.get("draft_type", "")

    if is_auction:
        draft_type = "Auction"
    elif draft_type_raw == "live":
        draft_type = "Live Snake"
    else:
        draft_type = "Snake"

    # Auction budget lives in settings as auction_budget_total
    auction_budget = None
    raw_budget = settings_dict.get("auction_budget_total") or settings_dict.get("auction_budget")
    if raw_budget is not None:
        try:
            auction_budget = int(raw_budget)
        except (ValueError, TypeError):
            pass

    return {
        "type": draft_type,
        "auction_budget": auction_budget if is_auction else None,
    }


def _parse_waiver_settings(settings_dict):
    """Waiver / FAAB configuration block."""
    uses_faab = bool(int(settings_dict.get("uses_faab") or 0))
    waiver_type = settings_dict.get("waiver_type", "")

    if uses_faab:
        system = "FAAB"
        order = "Inverse Order of Standings" if waiver_type == "FWR" else waiver_type
    else:
        system = "Standard Waivers"
        order = "Inverse Order of Standings" if waiver_type == "R" else waiver_type

    # FAAB budget from settings
    faab_budget = None
    raw_faab = settings_dict.get("faab_budget")
    if uses_faab and raw_faab is not None:
        try:
            faab_budget = int(raw_faab)
        except (ValueError, TypeError):
            pass

    return {
        "system": system,
        "order": order,
        "faab_budget": faab_budget,
    }


def _parse_schedule_settings(settings_dict):
    """Playoffs, trade, and schedule configuration block."""
    trade_ratify = settings_dict.get("trade_ratify_type", "")
    if trade_ratify == "commish":
        trade_approval = "Commissioner Review"
    elif trade_ratify == "none":
        trade_approval = "No Review (Instant)"
    else:
        trade_approval = "League Vote"

    return {
        "playoff_teams": settings_dict.get("num_playoff_teams"),
        "playoff_start_week": settings_dict.get("playoff_start_week"),
        "trade_deadline": settings_dict.get("trade_end_date"),
        "trade_approval": trade_approval,
        "trade_review_days": settings_dict.get("trade_reject_time", 0),
        "fractional_points": bool(settings_dict.get("uses_fractional_points", 0)),
        "negative_points": bool(settings_dict.get("uses_negative_points", 0)),
    }
    stat_categories = settings_dict.get("stat_categories", {})
    stat_modifiers = settings_dict.get("stat_modifiers", {})
    
    # Build a lookup of stat_id to stat info
    stat_lookup = {}
    if stat_categories and "stats" in stat_categories:
        for stat_wrapper in stat_categories["stats"]:
            stat = stat_wrapper.get("stat", {})
            stat_id = stat.get("stat_id")
            if stat_id:
                stat_lookup[stat_id] = {
                    "name": stat.get("name"),
                    "display_name": stat.get("display_name"),
                    "abbr": stat.get("abbr"),
                    "group": stat.get("group")
                }
    
    # Build a lookup of stat_id to point value
    points_lookup = {}
    if stat_modifiers and "stats" in stat_modifiers:
        for stat_wrapper in stat_modifiers["stats"]:
            stat = stat_wrapper.get("stat", {})
            stat_id = stat.get("stat_id")
            value = stat.get("value")
            if stat_id is not None and value is not None:
                points_lookup[stat_id] = value
    
    # Combine them into organized scoring rules
    scoring = {
        "passing": {},
        "rushing": {},
        "receiving": {},
        "misc": {},
        "defense": {}
    }
    
    # Map stat_ids to readable keys
    stat_mapping = {
        # Passing
        4: ("passing", "yards", "Passing Yards"),
        5: ("passing", "touchdowns", "Passing Touchdowns"),
        6: ("passing", "interceptions", "Interceptions"),
        
        # Rushing
        9: ("rushing", "yards", "Rushing Yards"),
        10: ("rushing", "touchdowns", "Rushing Touchdowns"),
        
        # Receiving
        11: ("receiving", "receptions", "Receptions"),
        12: ("receiving", "yards", "Receiving Yards"),
        13: ("receiving", "touchdowns", "Receiving Touchdowns"),
        
        # Misc
        15: ("misc", "return_touchdowns", "Return Touchdowns"),
        16: ("misc", "two_point_conversions", "2-Point Conversions"),
        18: ("misc", "fumbles_lost", "Fumbles Lost"),
        57: ("misc", "fumble_return_td", "Offensive Fumble Return TD"),
        
        # Defense
        32: ("defense", "sack", "Sack"),
        33: ("defense", "interception", "Interception"),
        34: ("defense", "fumble_recovery", "Fumble Recovery"),
        35: ("defense", "touchdown", "Touchdown"),
        36: ("defense", "safety", "Safety"),
        37: ("defense", "blocked_kick", "Blocked Kick"),
        49: ("defense", "return_touchdown", "Return TD"),
        67: ("defense", "fourth_down_stop", "4th Down Stop"),
        50: ("defense", "points_allowed_0", "Points Allowed 0"),
        51: ("defense", "points_allowed_1_6", "Points Allowed 1-6"),
        52: ("defense", "points_allowed_7_13", "Points Allowed 7-13"),
        53: ("defense", "points_allowed_14_20", "Points Allowed 14-20"),
        54: ("defense", "points_allowed_21_27", "Points Allowed 21-27"),
        55: ("defense", "points_allowed_28_34", "Points Allowed 28-34"),
        56: ("defense", "points_allowed_35_plus", "Points Allowed 35+"),
        82: ("defense", "extra_point_returned", "Extra Point Returned"),
    }
    
    # Build the scoring structure
    for stat_id, (category, key, display) in stat_mapping.items():
        if stat_id in points_lookup:
            points = points_lookup[stat_id]
            scoring[category][key] = {
                "points": points,
                "display": display
            }
    
    return scoring


def _parse_roster_settings(settings_dict):
    """
    Parse roster settings from Yahoo settings.
    """
    roster_positions = settings_dict.get("roster_positions", [])
    
    starting_positions = []
    bench_spots = 0
    ir_spots = 0
    
    for pos_wrapper in roster_positions:
        pos = pos_wrapper.get("roster_position", {})
        position = pos.get("position")
        count = pos.get("count", 0)
        is_starting = pos.get("is_starting_position", 0)
        
        if is_starting == 1:
            # Starting position
            display_name = position
            if position == "W/R/T":
                display_name = "FLEX (W/R/T)"
            
            starting_positions.append({
                "position": position,
                "display": display_name,
                "count": count
            })
        elif position == "BN":
            bench_spots = count
        elif position == "IR":
            ir_spots = count
    
    total_roster = sum(p["count"] for p in starting_positions) + bench_spots + ir_spots
    
    return {
        "starting_positions": starting_positions,
        "bench_spots": bench_spots,
        "ir_spots": ir_spots,
        "total_roster_size": total_roster
    }