import os
import json
import requests
from yfpy.query import YahooFantasySportsQuery

# -----------------------------
# Fantasy API helper (used by league, standings, teams, etc.)
# -----------------------------
def get_query(league_id=None, game_code="nfl", game_id=449):
    # If the league_id already contains a dot, assume it's a full league key
    if league_id and "." in league_id:
        full_league_key = league_id
    else:
        full_league_key = f"{game_id}.l.{league_id}"

    return YahooFantasySportsQuery(
        league_id=full_league_key,
        game_code=game_code,
        game_id=game_id,
        env_var_fallback=True
    )

# -----------------------------
# Direct Yahoo OAuth call for /yahoo/me
# -----------------------------
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

    # TEMP: return raw Yahoo response so we can see the real error
    return data

    return {
        "guid": user.get("guid"),
        "username": user.get("nickname"),
        "email": user.get("email"),
        "raw": data
    }
