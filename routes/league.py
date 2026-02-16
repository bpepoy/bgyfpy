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