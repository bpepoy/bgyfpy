from fastapi import APIRouter, HTTPException
from services.league_service import get_league_settings

router = APIRouter(prefix="/league", tags=["League"])

@router.get("/{league_id}/settings")
def league_settings(league_id: str):
    try:
        return get_league_settings(league_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))