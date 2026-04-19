"""
main.py — add these two lines to register the basketball router
===============================================================

1. Add the import near the other route imports:

    from routes.basketball.league import router as basketball_league_router

2. Add the include_router call near the others:

    app.include_router(basketball_league_router)


Full updated main.py for reference:
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from oauth import router as oauth_router
from routes.auth import router as auth_router
from routes.fantasy.league import router as fantasy_league_router
from routes.fantasy.teams import router as fantasy_teams_router
from routes.fantasy.yahoo import router as yahoo_router
from routes.explore import router as explore_router
from routes.basketball.league import router as basketball_league_router
from routes.fantasy.views import router as fantasy_views_router
import os

app = FastAPI(
    title="bgyfpy API",
    description="Backend API for BlackGold Fantasy + Real Bros Basketball",
    version="2.0.0"
)

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    os.getenv("FRONTEND_URL", ""),
]
origins = [o for o in origins if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(oauth_router)
app.include_router(auth_router)
app.include_router(fantasy_league_router)
app.include_router(fantasy_teams_router)
app.include_router(explore_router)
app.include_router(yahoo_router)
app.include_router(basketball_league_router)
app.include_router(fantasy_views_router)


@app.get("/")
def root():
    return {"message": "bgyfpy-backend is running", "version": "2.0.0"}


@app.get("/health")
def health_check():
    return {
        "status":            "healthy",
        "yahoo_credentials": bool(os.getenv("YAHOO_CONSUMER_KEY") and os.getenv("YAHOO_CONSUMER_SECRET")),
        "yahoo_token":       bool(os.getenv("YAHOO_ACCESS_TOKEN_JSON")),
        "resend_configured": bool(os.getenv("RESEND_API_KEY")),
        "jwt_configured":    bool(os.getenv("JWT_SECRET_KEY")),
        "environment":       os.getenv("ENVIRONMENT", "development"),
    }