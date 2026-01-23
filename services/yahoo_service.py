from yfpy.query import YahooFantasySportsQuery

def get_query(league_id: str = None, game_code="nfl", game_id=449):
    return YahooFantasySportsQuery(
        league_id=league_id,
        game_code=game_code,
        game_id=game_id,
        env_var_fallback=True
    )

def get_yahoo_profile():
    # Create a query object without needing a league_id
    query = YahooFantasySportsQuery(
        league_id=None,
        game_code="nfl",
        game_id=449,
        env_var_fallback=True
    )

    # yfpy exposes this method for user identity
    return query.get_user_info()
