from fastapi import APIRouter, HTTPException
from services.league_service import get_league_settings

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