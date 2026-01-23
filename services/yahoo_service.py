import os
import json
import requests

def get_yahoo_profile():
    # Load the token JSON from your environment variable
    token_json = os.getenv("YAHOO_ACCESS_TOKEN_JSON")
    if not token_json:
        raise Exception("No Yahoo token found in environment variable")

    token = json.loads(token_json)
    access_token = token.get("access_token")

    if not access_token:
        raise Exception("Access token missing from stored token JSON")

    # Yahoo user identity endpoint
    url = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1?format=json"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    # Parse Yahoo’s nested structure
    user = data["fantasy_content"]["users"]["0"]["user"][0]

    return {
        "guid": user.get("guid"),
        "username": user.get("nickname"),
        "email": user.get("email"),
        "raw": data
    }
