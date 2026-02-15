from fastapi import APIRouter, HTTPException, Query
from services.league_service import get_league_settings

router = APIRouter(prefix="/league", tags=["League"])

@router.get("/{league_key}/settings")
def league_settings(
    league_key: str,
    game_id: int = Query(default=461, description="Yahoo game ID (461 for NFL 2025)")
):
    """
    Get league settings.
    
    Args:
        league_key: League ID or full league key (e.g., "501623" or "461.l.501623")
        game_id: Yahoo game ID (461 for NFL 2025, 449 for NFL 2024)
    """
    try:
        return get_league_settings(league_key, game_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))