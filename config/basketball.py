"""
Basketball (Real Bros NBA) Configuration
=========================================
League identity and season history for the Real Bros NBA fantasy league.

Current season: 2025-26
League key:     466.l.38685
Game ID:        466
Previous season: 454.l.2122 (2024-25)

Add manager identity map and season history as data becomes available.
Run GET /league/explore/nba-season/466.l.38685 to explore available data.
"""
import os

# ---------------------------------------------------------------------------
# League Config
# ---------------------------------------------------------------------------

NBA_LEAGUE_CONFIG = {
    "name":               "Real Bros",
    "known_league_key":   "466.l.38685",
    "known_season_year":  2025,          # 2025-26 NBA season
    "first_season":       2024,          # earliest known season (454.l.2122)
    "founded":            2024,
    "game_code":          "nba",
    "cache_duration_hours": 24,
}

# ---------------------------------------------------------------------------
# Manual Season Mapping
# ---------------------------------------------------------------------------
# NBA seasons span two calendar years — keyed by the start year.
# The renew chain connects seasons automatically; add manual entries
# only if the chain breaks.

NBA_MANUAL_SEASON_MAPPING = {
    2024: {"game_id": 454, "league_id": "2122"},  # 2024-25 season
}

# ---------------------------------------------------------------------------
# Manager Identity Map
# ---------------------------------------------------------------------------
# TODO: populate with Real Bros manager GUIDs and team keys after running:
# GET /league/explore/nba-season/466.l.38685
#
# Format mirrors MANAGER_IDENTITY_MAP in fantasy.py:
# "manager_id": {
#     "display_name": "...",
#     "guid": "...",
#     "team_keys": ["466.l.38685.t.1", ...]
# }

NBA_MANAGER_IDENTITY_MAP: dict = {
    # Populated after exploring the league data
}

# ---------------------------------------------------------------------------
# Season History — Manual Data
# ---------------------------------------------------------------------------
# punishment: voted on each year
# first_pick: first overall draft pick
# top_players: top fantasy scorer per position (PG, SG, SF, PF, C)

NBA_SEASON_HISTORY_MANUAL = {
    2025: {  # 2025-26 season
        "punishment": None,
        "first_pick": None,
        "top_players": None,
    },
    2024: {  # 2024-25 season
        "punishment": None,
        "first_pick": None,
        "top_players": None,
    },
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_nba_known_league_key() -> str:
    return os.getenv("NBA_KNOWN_LEAGUE_KEY", NBA_LEAGUE_CONFIG["known_league_key"])


def get_nba_known_season_year() -> int:
    return int(os.getenv("NBA_KNOWN_SEASON_YEAR", NBA_LEAGUE_CONFIG["known_season_year"]))


def get_nba_first_season() -> int:
    return NBA_LEAGUE_CONFIG["first_season"]


def get_nba_league_name() -> str:
    return NBA_LEAGUE_CONFIG["name"]


def get_nba_founded_year() -> int:
    return NBA_LEAGUE_CONFIG["founded"]


def get_nba_manual_season_mapping() -> dict:
    return NBA_MANUAL_SEASON_MAPPING


def get_nba_manager_identity(team_key: str = None, manager_guid: str = None) -> dict | None:
    """
    Resolve a manager's identity from a team_key or GUID.
    Returns {"manager_id": "...", "display_name": "..."} or None.
    Mirrors get_manager_identity() in fantasy.py.
    """
    if team_key:
        for manager_id, data in NBA_MANAGER_IDENTITY_MAP.items():
            if team_key in data.get("team_keys", []):
                return {"manager_id": manager_id, "display_name": data["display_name"]}

    if manager_guid:
        for manager_id, data in NBA_MANAGER_IDENTITY_MAP.items():
            if data.get("guid") == manager_guid:
                return {"manager_id": manager_id, "display_name": data["display_name"]}

    return None


def get_nba_season_manual_data(year: int) -> dict:
    return NBA_SEASON_HISTORY_MANUAL.get(year, {})