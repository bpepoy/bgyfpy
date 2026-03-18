from fastapi import APIRouter, HTTPException
from services.yahoo_service import get_yahoo_profile, get_user_leagues, get_query

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

@router.get("/debug/query")
def debug_query(league_id: str):
    """
    Debug endpoint to see what parameters are being passed to YFPY
    """
    try:
        # Import to see internal state
        import os
        
        # Check if league_id has dots
        has_dots = "." in str(league_id)
        
        # Show what would be passed
        result = {
            "league_id_input": league_id,
            "has_dots": has_dots,
            "would_set_game_id": not has_dots,
            "default_game_id": 461
        }
        
        # Try to create the query and catch any errors
        try:
            query = get_query(league_id)
            result["query_created"] = True
            result["query_league_id"] = getattr(query, 'league_id', 'N/A')
        except Exception as e:
            result["query_created"] = False
            result["error"] = str(e)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))