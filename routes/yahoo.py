from fastapi import APIRouter, HTTPException
from services.yahoo_service import get_yahoo_profile

router = APIRouter(prefix="/yahoo", tags=["Yahoo"])

@router.get("/me")
def yahoo_me():
    try:
        return get_yahoo_profile()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
