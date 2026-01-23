from fastapi import APIRouter, HTTPException
from services.yahoo_service import get_yahoo_profile

router = APIRouter(prefix="/yahoo", tags=["Yahoo"])

@router.get("/me")
def yahoo_me():
    try:
        profile = get_yahoo_profile()

        # Normalize the response
        return {
            "guid": profile.get("guid"),
            "username": profile.get("nickname"),
            "email": profile.get("email"),
            "raw": profile
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))