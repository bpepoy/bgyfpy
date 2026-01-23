from yfpy.query import YahooFantasySportsQuery

def get_query(league_id: str, game_code="nfl", game_id=449):
    return YahooFantasySportsQuery(
        league_id=league_id,
        game_code=game_code,
        game_id=game_id,
        env_var_fallback=True
    )