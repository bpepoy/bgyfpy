from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from oauth import router as oauth_router
from routes.league import router as league_router
from routes.yahoo import router as yahoo_router
import os

app = FastAPI(
    title="Yahoo Fantasy Sports API",
    description="Backend API for Yahoo Fantasy Sports",
    version="1.0.0"
)

# CORS Configuration - Update with your frontend domain
origins = [
    "http://localhost:3000",  # Local React/Next.js
    "http://localhost:5173",  # Local Vite
    os.getenv("FRONTEND_URL", ""),  # Production frontend from env
]

# Remove empty strings
origins = [o for o in origins if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],  # Fallback to all origins in dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth routes (login + callback)
app.include_router(oauth_router)

# League routes (settings, history, etc.)
app.include_router(league_router)

# Yahoo route (account login sustainability)
app.include_router(yahoo_router)

@app.get("/")
def root():
    return {"message": "bgyfpy-backend is running"}

@app.get("/health")
def health_check():
    """Health check endpoint for Render"""
    yahoo_token_present = bool(os.getenv("YAHOO_ACCESS_TOKEN_JSON"))
    yahoo_creds_present = bool(
        os.getenv("YAHOO_CONSUMER_KEY") and 
        os.getenv("YAHOO_CONSUMER_SECRET")
    )
    
    return {
        "status": "healthy",
        "yahoo_credentials_configured": yahoo_creds_present,
        "yahoo_token_configured": yahoo_token_present,
        "environment": os.getenv("ENVIRONMENT", "development")
    }