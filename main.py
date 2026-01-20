from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "bgyfpy-backend is running"}
