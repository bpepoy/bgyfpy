from services.yahoo_service import get_query

@router.get("/{league_key}/settings")
def league_settings(league_key: str):
    # If the user passes a full key, strip the prefix
    if "." in league_key:
        league_key = league_key.split(".")[-1]

    return get_league_settings(league_key)

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