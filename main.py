from fastapi import FastAPI
from oauth import router as oauth_router
from routes.league import router as league_router
from routes.yahoo import router as yahoo_router

app = FastAPI()

# OAuth routes (login + callback)
app.include_router(oauth_router)

# League routes (settings, history, etc.)
app.include_router(league_router)

# Yahoo route (account login sustainability)
app.include_router(yahoo_router)

@app.get("/")
def root():
    return {"message": "bgyfpy-backend is running"}
