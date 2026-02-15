from services.yahoo_service import get_query

def get_league_settings(league_id: str, game_id: int = 461):
    """
    Fetches league settings/metadata from Yahoo Fantasy Sports.
    
    Args:
        league_id: League ID (numeric like "501623" or full key like "461.l.501623")
        game_id: Yahoo game ID (461 for NFL 2025)
    
    Returns:
        dict: Normalized league settings
    """
    try:
        # Pass the league_id and game_id to get_query
        query = get_query(league_id, game_id=game_id)
        raw = query.get_league_metadata()
        
        # YFPY returns objects, not dicts - convert to dict
        if hasattr(raw, 'to_json'):
            raw_dict = raw.to_json()
        elif hasattr(raw, '__dict__'):
            raw_dict = raw.__dict__
        else:
            raw_dict = raw
        
        # Normalize the Yahoo response into clean, frontend-friendly JSON
        settings = {
            "league_id": league_id,
            "name": _safe_get(raw_dict, "name"),
            "season": _safe_get(raw_dict, "season"),
            "num_teams": _safe_get(raw_dict, "num_teams"),
            "scoring_type": _safe_get(raw_dict, "scoring_type"),
            "draft_status": _safe_get(raw_dict, "draft_status"),
            "is_keeper": _safe_get(raw_dict, "is_keeper"),
            "start_week": _safe_get(raw_dict, "start_week"),
            "end_week": _safe_get(raw_dict, "end_week"),
            "current_week": _safe_get(raw_dict, "current_week"),
            "waiver_type": _safe_get(raw_dict, "waiver_type"),
            "trade_end_date": _safe_get(raw_dict, "trade_end_date"),
            "game_code": _safe_get(raw_dict, "game_code"),
            "url": _safe_get(raw_dict, "url"),
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