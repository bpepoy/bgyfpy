import os
import base64
import json
import requests
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse

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
    """
    Initiates the Yahoo OAuth flow.
    Redirects user to Yahoo login page.
    """
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
    """
    Handles the OAuth callback from Yahoo.
    Exchanges authorization code for access token.
    
    ⚠️ IMPORTANT: You must manually copy the returned JSON
    into Render's YAHOO_ACCESS_TOKEN_JSON environment variable.
    """
    code = request.query_params.get("code")
    error = request.query_params.get("error")
    
    if error:
        raise HTTPException(
            status_code=400, 
            detail=f"OAuth error from Yahoo: {error}"
        )
    
    if not code:
        raise HTTPException(
            status_code=400, 
            detail="Missing 'code' in callback"
        )

    consumer_key, consumer_secret, redirect_uri = get_config()

    # Yahoo expects Basic auth header
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
        "token_time": float(token_data.get("expires_in", 3600)),  # Convert to float
        "token_type": token_data.get("token_type", "bearer"),
    }

    # Return user-friendly HTML with copy button
    json_string = json.dumps(access_token_json, indent=2)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OAuth Success</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #6001d2;
            }}
            .success {{
                color: #28a745;
                font-size: 18px;
                margin-bottom: 20px;
            }}
            .instructions {{
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 5px;
                padding: 15px;
                margin: 20px 0;
            }}
            .instructions ol {{
                margin: 10px 0;
                padding-left: 20px;
            }}
            .json-container {{
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 15px;
                margin: 20px 0;
                overflow-x: auto;
            }}
            pre {{
                margin: 0;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            button {{
                background-color: #6001d2;
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 16px;
                border-radius: 5px;
                cursor: pointer;
                margin-top: 10px;
            }}
            button:hover {{
                background-color: #4a01a3;
            }}
            .copied {{
                color: #28a745;
                margin-left: 10px;
                display: none;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✅ OAuth Authentication Successful!</h1>
            <p class="success">You have successfully authenticated with Yahoo Fantasy Sports.</p>
            
            <div class="instructions">
                <h3>📝 Next Steps:</h3>
                <ol>
                    <li>Click the "Copy Token JSON" button below</li>
                    <li>Go to your Render Dashboard</li>
                    <li>Navigate to your web service</li>
                    <li>Click on "Environment" in the left sidebar</li>
                    <li>Find the <code>YAHOO_ACCESS_TOKEN_JSON</code> environment variable</li>
                    <li>Paste the copied JSON as the value (replace the old value completely)</li>
                    <li>Click "Save Changes"</li>
                    <li>Wait for your service to redeploy (~2 minutes)</li>
                </ol>
            </div>
            
            <h3>Token JSON:</h3>
            <div class="json-container">
                <pre id="tokenJson">{json_string}</pre>
            </div>
            
            <button onclick="copyToken()">📋 Copy Token JSON</button>
            <span class="copied" id="copiedMessage">✓ Copied!</span>
        </div>
        
        <script>
            function copyToken() {{
                const tokenText = document.getElementById('tokenJson').textContent;
                navigator.clipboard.writeText(tokenText).then(() => {{
                    const copiedMsg = document.getElementById('copiedMessage');
                    copiedMsg.style.display = 'inline';
                    setTimeout(() => {{
                        copiedMsg.style.display = 'none';
                    }}, 3000);
                }});
            }}
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@router.get("/oauth/status")
def oauth_status():
    """
    Check if OAuth token is configured.
    Useful for debugging.
    """
    token_json = os.getenv("YAHOO_ACCESS_TOKEN_JSON")
    has_token = bool(token_json)
    
    if has_token:
        try:
            token_data = json.loads(token_json)
            return {
                "authenticated": True,
                "has_access_token": bool(token_data.get("access_token")),
                "has_refresh_token": bool(token_data.get("refresh_token")),
                "guid": token_data.get("guid", "N/A")
            }
        except json.JSONDecodeError:
            return {
                "authenticated": False,
                "error": "Invalid token JSON format"
            }
    
    return {
        "authenticated": False,
        "message": "No token configured. Visit /oauth/start to authenticate."
    }