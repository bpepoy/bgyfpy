from fastapi import FastAPI
from oauth import router as oauth_router

app = FastAPI()

app.include_router(oauth_router)

@app.get("/")
def root():
    return {"message": "bgyfpy-backend is running"}
