from services.yahoo_service import get_query

def get_league_settings(league_id: str):
    """
    Fetches league settings/metadata from Yahoo Fantasy Sports.
    
    Args:
        league_id: League ID (numeric like "501623" or full key like "461.l.501623")
    
    Returns:
        dict: Normalized league settings
    """
    try:
        query = get_query(league_id)
        raw = query.get_league_metadata()
        
        # YFPY returns objects, not dicts - convert to dict
        if hasattr(raw, 'to_json'):
            raw_dict = raw.to_json()
        elif hasattr(raw, '__dict__'):
            raw_dict = raw.__dict__
        else:
            raw_dict = raw
        
        # If raw_dict is a string (JSON), parse it
        if isinstance(raw_dict, str):
            import json
            raw_dict = json.loads(raw_dict)
        
        # Parse renew field for historical data tracking
        renew_data = _parse_renew_field(_safe_get(raw_dict, "renew"))
        
        # Normalize the Yahoo response into clean, frontend-friendly JSON
        settings = {
            # Basic Info
            "league_id": league_id,
            "league_key": _safe_get(raw_dict, "league_key"),
            "name": _safe_get(raw_dict, "name"),
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