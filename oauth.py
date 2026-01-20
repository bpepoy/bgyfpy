import os
import base64
import requests
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

router = APIRouter()

YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


def get_config():
    consumer_key = os.getenv("YAHOO_CONSUMER_KEY")
    consumer_secret = os.getenv("YAHOO_CONSUMER_SECRET")
    redirect_uri = os.getenv("YAHOO_REDIRECT_URI")

    if not consumer_key or not consumer_secret or not redirect_uri:
        raise RuntimeError("Missing Yahoo OAuth environment variables")

    return consumer_key, consumer_secret, redirect_uri


@router.get("/oauth/start")
def oauth_start():
    consumer_key, _, redirect_uri = get_config()

    params = {
        "client_id": consumer_key,
        "redirect_uri": redirect_uri,
        "response_type": "code",
    }

    url = f"{YAHOO_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/oauth/callback")
def oauth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' in callback")

    consumer_key, consumer_secret, redirect_uri = get_config()

    # Yahoo expects either Basic auth header or client_id/client_secret in body.
    basic_auth = base64.b64encode(
        f"{consumer_key}:{consumer_secret}".encode("utf-8")
    ).decode("utf-8")

    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": code,
    }

    resp = requests.post(YAHOO_TOKEN_URL, headers=headers, data=data)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Error from Yahoo token endpoint: {resp.text}",
        )

    token_data = resp.json()

    # Shape this into what YFPY expects for YAHOO_ACCESS_TOKEN_JSON
    access_token_json = {
        "access_token": token_data.get("access_token"),
        "consumer_key": consumer_key,
        "consumer_secret": consumer_secret,
        "guid": token_data.get("xoauth_yahoo_guid"),
        "refresh_token": token_data.get("refresh_token"),
        "token_time": token_data.get("created_at", 0),
        "token_type": token_data.get("token_type", "bearer"),
    }

    return JSONResponse(
        {
            "message": "OAuth success. Copy the JSON below into YAHOO_ACCESS_TOKEN_JSON in Render.",
            "YAHOO_ACCESS_TOKEN_JSON": access_token_json,
        }
    )
