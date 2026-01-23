from yfpy.query import YahooFantasySportsQuery

def get_query(league_id=None, game_code="nfl", game_id=449):
    return YahooFantasySportsQuery(
        league_id=league_id,
        game_code=game_code,
        game_id=game_id,
        env_var_fallback=True
    )

def get_yahoo_profile():
    query = get_query()

    # Yahoo user identity endpoint
    url = "https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1?format=json"

    # Use yfpy's internal API caller
    raw = query._call_api(url)

    # Navigate Yahoo’s nested structure
    user = raw["fantasy_content"]["users"]["0"]["user"][0]

    return {
        "guid": user.get("guid"),
        "username": user.get("nickname"),
        "email": user.get("email"),
        "raw": raw
    }
