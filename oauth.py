import os
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from yfpy.oauth import YahooOAuth2

router = APIRouter()

def get_oauth():
    return YahooOAuth2(
        client_id=os.getenv("YAHOO_CLIENT_ID"),
        client_secret=os.getenv("YAHOO_CLIENT_SECRET"),
        redirect_uri=os.getenv("YAHOO_REDIRECT_URI"),
    )

@router.get("/oauth/start")
def oauth_start():
    oauth = get_oauth()
    auth_url = oauth.get_authorization_url()
    return RedirectResponse(auth_url)

@router.get("/oauth/callback")
def oauth_callback(request: Request):
    oauth = get_oauth()
    full_url = str(request.url)
    tokens = oauth.fetch_access_token(full_url)
    return {"tokens": tokens}
