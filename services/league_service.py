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
    
    Args:
        seasons: Dict to populate with season data
        start_year: Year to start from
        first_season: Earliest possible season year
    """
    current_year = start_year - 1
    
    # Get the renew field from the starting season
    if start_year in seasons and seasons[start_year]["renew"]:
        renew_value = seasons[start_year]["renew"]
    else:
        return
    
    while current_year >= first_season and renew_value:
        try:
            # Parse renew field (format: "game_id_league_id")
            parts = str(renew_value).split("_")
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
            
            # Get the next renew value for the previous year
            renew_value = seasons[current_year]["renew"]
            current_year -= 1
            
        except Exception as e:
            print(f"Error fetching season {current_year}: {str(e)}")
            break


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