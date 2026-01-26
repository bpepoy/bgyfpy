from fastapi import APIRouter, HTTPException
from services.league_service import get_league_settings

router = APIRouter(prefix="/league", tags=["League"])

@router.get("/{league_key}/settings")
def league_settings(league_key: str):
    # If the user passes a full league key like "449.l.501623",
    # strip the prefix so yfpy doesn't duplicate it.
    if "." in league_key:
        league_key = league_key.split(".")[-1]

    try:
        return get_league_settings(league_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))