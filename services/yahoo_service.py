import os
import json
import requests
from yfpy.query import YahooFantasySportsQuery

# -----------------------------
# Fantasy API helper (used by league, standings, teams, etc.)
# -----------------------------
def get_query(league_id=None, game_code="nfl", game_id=449):
    """
    Creates a YahooFantasySportsQuery instance.
    
    Args:
        league_id: League ID (can be numeric or full key like "449.l.501623")
        game_code: Sport code (nfl, nba, nhl, mlb)
        game_id: Yahoo game ID (449 for NFL 2024)
    
    Returns:
        YahooFantasySportsQuery instance
    """
    # Get token from environment
    token_json_str = os.getenv("YAHOO_ACCESS_TOKEN_JSON")
    
    query_kwargs = {
        "game_code": game_code,
        "game_id": game_id,
        "env_var_fallback": True,
    }
    
    # Handle league_id - pass it directly to YFPY without modification
    # YFPY will handle the format internally
    if league_id:
        query_kwargs["league_id"] = league_id
    
    # If we have a token JSON, use it directly for authentication
    if token_json_str:
        try:
            token_data = json.loads(token_json_str)
            query_kwargs["yahoo_access_token_json"] = token_data
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid YAHOO_ACCESS_TOKEN_JSON format: {str(e)}")
    
    try:
        return YahooFantasySportsQuery(**query_kwargs)
    except Exception as e:
        raise Exception(f"Failed to initialize Yahoo Fantasy API: {str(e)}")


# -----------------------------
# Direct Yahoo OAuth call for /yahoo/me
# -----------------------------
def get_yahoo_profile():
    """
    Gets the current user's Yahoo profile information.
    This makes a direct API call to Yahoo (not using YFPY).
    
    Returns:
        dict: User profile information
    """
    # Load the token JSON from environment variable
    token_json_str = os.getenv("YAHOO_ACCESS_TOKEN_JSON")
    if not token_json_str:
        raise Exception(
            "No Yahoo token found. Please authenticate via /oauth/start first."
        )

    try:
        token = json.loads(token_json_str)
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid token JSON format: {str(e)}")
    
    access_token = token.get("access_token")
    if not access_token:
        raise Exception("Access token missing from stored token JSON")

    # Yahoo user identity endpoint
    url = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1?format=json"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to fetch Yahoo profile: {str(e)}")

    data = response.json()
    
    # Yahoo's response structure is deeply nested
    # Structure: fantasy_content -> users -> 0 -> user -> [array of objects]
    try:
        fantasy_content = data.get("fantasy_content", {})
        users = fantasy_content.get("users", {})
        
        # Get the first user (key "0")
        first_user = users.get("0", {})
        user_array = first_user.get("user", [])
        
        # Yahoo returns user data as an array of objects
        # Parse it into a single dict
        user_data = {}
        if isinstance(user_array, list):
            for item in user_array:
                if isinstance(item, dict):
                    user_data.update(item)
        
        # Extract the key fields
        result = {
            "guid": user_data.get("guid"),
            "username": user_data.get("nickname"),
        }
        
        # Add optional fields if they exist
        if "email" in user_data:
            result["email"] = user_data["email"]
        if "profile_url" in user_data:
            result["profile_url"] = user_data["profile_url"]
        if "image_url" in user_data:
            result["image_url"] = user_data["image_url"]
        
        # If we got the guid, return the cleaned data
        if result["guid"]:
            return result
        else:
            # If parsing failed, return raw for debugging
            return {
                "error": "Could not parse user data",
                "raw_response": data
            }
            
    except Exception as e:
        # If parsing fails completely, return raw data for debugging
        return {
            "error": f"Failed to parse response: {str(e)}",
            "raw_response": data
        }


def refresh_access_token():
    """
    Refreshes the Yahoo access token using the refresh token.
    This should be called when the access token expires.
    
    Note: YFPY handles token refresh automatically, but this can be used
    for manual refresh if needed.
    """
    token_json_str = os.getenv("YAHOO_ACCESS_TOKEN_JSON")
    if not token_json_str:
        raise Exception("No Yahoo token found")
    
    try:
        token = json.loads(token_json_str)
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid token JSON format: {str(e)}")
    
    refresh_token = token.get("refresh_token")
    consumer_key = token.get("consumer_key")
    consumer_secret = token.get("consumer_secret")
    
    if not all([refresh_token, consumer_key, consumer_secret]):
        raise Exception("Missing required token fields for refresh")
    
    import base64
    basic_auth = base64.b64encode(
        f"{consumer_key}:{consumer_secret}".encode("utf-8")
    ).decode("utf-8")
    
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    
    token_url = "https://api.login.yahoo.com/oauth2/get_token"
    
    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to refresh token: {str(e)}")
    
    new_token_data = response.json()
    
    # Update the token JSON with new values
    updated_token = {
        "access_token": new_token_data.get("access_token"),
        "consumer_key": consumer_key,
        "consumer_secret": consumer_secret,
        "guid": token.get("guid"),  # Keep existing guid
        "refresh_token": new_token_data.get("refresh_token"),
        "token_time": float(new_token_data.get("expires_in", 3600)),
        "token_type": new_token_data.get("token_type", "bearer"),
    }
    
    return updated_token