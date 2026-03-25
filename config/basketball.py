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
# Manager identity mapping across nba seasons
NBA_MANAGER_IDENTITY_MAP: dict = {
    "amboy": {
        "display_name": "Amboy",
        "guid": "TEYJ76XYU5CMXPSE4JDVN4J2YM",
        "team_keys": [
            "466.l.38685.t.5"
        ]
    },
    "brian": {
        "display_name": "Brian",
        "guid": "IQHD5CED7LQZAJP3ISPARVVDDQ",
        "team_keys": [
            "466.l.38685.t.10"
        ]
    },
    "dean": {
        "display_name": "Dean",
        "guid": "4BACI3WLYXRF2UTVMMR2OA75AU",
        "team_keys": [
            "466.l.38685.t.7"
        ]
    },
    "kroppe": {
        "display_name": "Kroppe",
        "guid": "VWU7L7UTIJPHCKFCW5RMQ44BRI",
        "team_keys": [
            "466.l.38685.t.6"
        ]
    },
    "eric": {
        "display_name": "Eric",
        "guid": "MTVXSYU5OITG3ONCVR3IWSN5Q4",
        "team_keys": [
            "466.l.38685.t.3"
        ]
    },
    "jezak": {
        "display_name": "Jezak",
        "guid": "R3A36ONORIMVBZREKQYF4IAPQ4",
        "team_keys": [
            "466.l.38685.t.4"
        ]
    },
    "brett": {
        "display_name": "Brett",
        "guid": "SGNLESVHGYNBPYNDR6L54TF4GA",
        "team_keys": [
            "466.l.38685.t.2"
        ]
    },
    "kyle": {
        "display_name": "Kyle",
        "guid": "53ELOA5F2IAFZAHFCILHZX2IZY",
        "team_keys": [
        ]
    },
    "ray": {
        "display_name": "Ray",
        "guid": "RXHQAU6D6I7L6AATYCA7EIFEIM",
        "team_keys": [
            # TODO: add correct NBA team_key — 175.l.492325.t.5 was a football league key
        ]
    },
    "nick": {
        "display_name": "Nick",
        "guid": "5NOEDPXWKEFDO3LHGG5THAWXMQ",
        "team_keys": [
            "466.l.38685.t.8"
        ]
    },
    "sam": {
        "display_name": "Sam",
        "guid": "UOOBQORBBE2LMHDZWZLYLCPRB4",
        "team_keys": [
            "466.l.38685.t.1"
        ]
    },
    "zef": {
        "display_name": "Zef",
        "guid": "3JYXPSSMU2OOSZEZYREF43ATIQ",
        "team_keys": [
            "466.l.38685.t.10"
        ]
    }
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