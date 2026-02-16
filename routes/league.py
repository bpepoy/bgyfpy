from fastapi import APIRouter, HTTPException
from services.league_service import get_league_settings
from services.yahoo_service import get_query

router = APIRouter(prefix="/league", tags=["League"])

@router.get("/{league_key}/settings")
def league_settings(league_key: str):
    """
    Get league settings.
    
    Args:
        league_key: League ID or full league key (e.g., "501623" or "461.l.501623")
    """
    try:
        return get_league_settings(league_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{league_key}/raw")
def league_raw_data(league_key: str):
    """
    Get ALL raw league data to see what's available.
    Temporary endpoint for exploring available fields.
    
    Args:
        league_key: League ID or full league key
    """
    try:
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