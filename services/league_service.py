from services.yahoo_service import get_query

def get_league_settings(league_id: str):
    # Ensure we pass only the numeric part to yfpy
    if "." in league_id:
        league_id = league_id.split(".")[-1]

    query = get_query(league_id)
    raw = query.get_league_metadata()

    # Normalize the Yahoo response into clean, frontend-friendly JSON
    settings = {
        "league_id": league_id,
        "name": raw.get("name"),
        "season": raw.get("season"),
        "num_teams": raw.get("num_teams"),
        "scoring_type": raw.get("scoring_type"),
        "draft_status": raw.get("draft_status"),
        "is_keeper": raw.get("is_keeper"),
        "start_week": raw.get("start_week"),
        "end_week": raw.get("end_week"),
        "waiver_type": raw.get("waiver_type"),
        "trade_end_date": raw.get("trade_end_date"),
    }

    return settings