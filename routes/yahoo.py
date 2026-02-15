from fastapi import APIRouter, HTTPException
from services.yahoo_service import get_yahoo_profile, get_user_leagues

router = APIRouter(prefix="/yahoo", tags=["Yahoo"])

@router.get("/me")
def yahoo_me():
    try:
        return get_yahoo_profile()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leagues")
def yahoo_leagues(game_code: str = "nfl"):
    """
    Get all leagues for the authenticated user for a specific sport.
    
    Args:
        game_code: Sport code (nfl, nba, nhl, mlb)
    """
    try:
        return get_user_leagues(game_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))