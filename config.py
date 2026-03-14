"""
Application configuration for BlackGold Fantasy League
"""
import os

# Your league's base configuration
LEAGUE_CONFIG = {
    "name": "BlackGold",
    "known_league_key": "461.l.501623",
    "known_season_year": 2025,
    "first_season": 2007,
    "founded": 2007,
    "cache_duration_hours": 24,
}

# Manual season mapping for years where renew chain breaks
MANUAL_SEASON_MAPPING = {
    2009: {"game_id": 222, "league_id": "727137"},
    2008: {"game_id": 199, "league_id": "394479"},
    2007: {"game_id": 175, "league_id": "492325"},
}

# Manager identity mapping across all seasons
MANAGER_IDENTITY_MAP = {
    "blake": {
        "display_name": "Blake",
        "guid": "X54AYSEFTKPA6C3MX3RQ2XW2JI",
        "team_keys": [
            "175.l.492325.t.10",
            "199.l.394479.t.3",
            "222.l.727137.t.7",
            "242.l.162179.t.9",
            "257.l.208499.t.7",
            "273.l.159744.t.6",
            "314.l.42504.t.9",
            "331.l.37674.t.7",
            "348.l.125651.t.10",
            "359.l.229979.t.10",
            "371.l.472717.t.10",
            "380.l.217545.t.9",
            "390.l.322665.t.9",
            "399.l.129567.t.3",
            "406.l.768183.t.3",
            "414.l.392137.t.3",
            "423.l.495176.t.3",
            "449.l.150305.t.3",
            "461.l.501623.t.3"
        ]
    },
    "brian": {
        "display_name": "Brian",
        "guid": "IQHD5CED7LQZAJP3ISPARVVDDQ",
        "team_keys": [
            "175.l.492325.t.1",
            "199.l.394479.t.8",
            "222.l.727137.t.4",
            "242.l.162179.t.7",
            "257.l.208499.t.6",
            "273.l.159744.t.7",
            "314.l.42504.t.7",
            "331.l.37674.t.6",
            "348.l.125651.t.7",
            "359.l.229979.t.7",
            "371.l.472717.t.7",
            "380.l.217545.t.4",
            "390.l.322665.t.4",
            "399.l.129567.t.6",
            "406.l.768183.t.6",
            "414.l.392137.t.6",
            "423.l.495176.t.6",
            "449.l.150305.t.6",
            "461.l.501623.t.6"
        ]
    },
    "danny": {
        "display_name": "Danny",
        "guid": None,
        "team_keys": ["175.l.492325.t.4"]
    },
    "frank": {
        "display_name": "Frank",
        "guid": "5652MIZAVSIETJMML3FZ22DB2I",
        "team_keys": [
            "273.l.159744.t.10",
            "314.l.42504.t.8",
            "331.l.37674.t.2",
            "348.l.125651.t.2",
            "359.l.229979.t.2",
            "371.l.472717.t.2",
            "380.l.217545.t.6",
            "390.l.322665.t.6",
            "399.l.129567.t.4",
            "406.l.768183.t.4",
            "414.l.392137.t.4",
            "423.l.495176.t.4",
            "449.l.150305.t.4",
            "461.l.501623.t.4"
        ]
    },
    "george": {
        "display_name": "George",
        "guid": None,
        "team_keys": ["175.l.492325.t.7"]
    },
    "jake": {
        "display_name": "Jake",
        "guid": "YBTOITPOIDWKRAXD4MU5JVORZU",
        "team_keys": [
            "175.l.492325.t.6",
            "199.l.394479.t.6",
            "222.l.727137.t.10",
            "242.l.162179.t.3",
            "257.l.208499.t.3",
            "273.l.159744.t.3",
            "314.l.42504.t.6",
            "331.l.37674.t.3",
            "348.l.125651.t.5",
            "359.l.229979.t.5",
            "371.l.472717.t.5",
            "380.l.217545.t.3",
            "390.l.322665.t.3",
            "399.l.129567.t.9",
            "406.l.768183.t.9",
            "414.l.392137.t.9",
            "423.l.495176.t.9",
            "449.l.150305.t.10",
            "461.l.501623.t.10"
        ]
    },
    "joey": {
        "display_name": "Joey",
        "guid": "QOMSHBDWB5QPAQYACTW2HMO4VA",
        "team_keys": [
            "175.l.492325.t.2",
            "199.l.394479.t.1",
            "222.l.727137.t.1",
            "242.l.162179.t.6",
            "257.l.208499.t.2",
            "273.l.159744.t.2",
            "314.l.42504.t.2",
            "331.l.37674.t.4",
            "348.l.125651.t.3",
            "359.l.229979.t.3",
            "371.l.472717.t.3",
            "380.l.217545.t.10",
            "390.l.322665.t.10",
            "399.l.129567.t.7",
            "406.l.768183.t.7",
            "414.l.392137.t.7",
            "423.l.495176.t.7",
            "449.l.150305.t.7",
            "461.l.501623.t.7"
        ]
    },
    "jordan": {
        "display_name": "Jordan",
        "guid": "VVPN5IDANOQVOBUHIEBIINOVZE",
        "team_keys": [
            "390.l.322665.t.8",
            "399.l.129567.t.2",
            "406.l.768183.t.2",
            "414.l.392137.t.2",
            "423.l.495176.t.2",
            "449.l.150305.t.2",
            "461.l.501623.t.2"
        ]
    },
    "kyle": {
        "display_name": "Kyle",
        "guid": "53ELOA5F2IAFZAHFCILHZX2IZY",
        "team_keys": [
            "175.l.492325.t.3",
            "199.l.394479.t.5",
            "222.l.727137.t.3",
            "242.l.162179.t.1",
            "257.l.208499.t.10",
            "273.l.159744.t.5",
            "314.l.42504.t.3",
            "331.l.37674.t.9",
            "348.l.125651.t.6",
            "359.l.229979.t.6",
            "371.l.472717.t.6",
            "380.l.217545.t.7",
            "390.l.322665.t.7",
            "399.l.129567.t.8",
            "406.l.768183.t.8",
            "414.l.392137.t.8",
            "423.l.495176.t.8",
            "449.l.150305.t.8",
            "461.l.501623.t.8"
        ]
    },
    "matt": {
        "display_name": "Matt",
        "guid": None,
        "team_keys": ["175.l.492325.t.5"]
    },
    "nick": {
        "display_name": "Nick",
        "guid": "5NOEDPXWKEFDO3LHGG5THAWXMQ",
        "team_keys": [
            "175.l.492325.t.8",
            "199.l.394479.t.4",
            "222.l.727137.t.5",
            "242.l.162179.t.8",
            "257.l.208499.t.8",
            "273.l.159744.t.8",
            "314.l.42504.t.10",
            "331.l.37674.t.10",
            "348.l.125651.t.9",
            "359.l.229979.t.9",
            "371.l.472717.t.9",
            "380.l.217545.t.5",
            "390.l.322665.t.5",
            "399.l.129567.t.5",
            "406.l.768183.t.5",
            "414.l.392137.t.5",
            "423.l.495176.t.5",
            "449.l.150305.t.5",
            "461.l.501623.t.5"
        ]
    },
    "raphi": {
        "display_name": "Raphi",
        "guid": None,
        "team_keys": [
            "199.l.394479.t.9",
            "222.l.727137.t.2",
            "242.l.162179.t.5",
            "257.l.208499.t.9"
        ]
    },
    "reuben": {
        "display_name": "Reuben",
        "guid": None,
        "team_keys": ["199.l.394479.t.2"]
    },
    "rob": {
        "display_name": "Rob",
        "guid": "KR4ZW6KHARXK67S4TTUYRHDZSI",
        "team_keys": [
            "199.l.394479.t.10",
            "222.l.727137.t.8",
            "242.l.162179.t.10",
            "257.l.208499.t.5",
            "273.l.159744.t.9",
            "314.l.42504.t.4",
            "331.l.37674.t.8",
            "348.l.125651.t.8",
            "359.l.229979.t.8",
            "371.l.472717.t.8",
            "380.l.217545.t.2",
            "390.l.322665.t.2",
            "399.l.129567.t.10",
            "406.l.768183.t.10",
            "414.l.392137.t.10",
            "423.l.495176.t.10",
            "449.l.150305.t.9",
            "461.l.501623.t.9"
        ]
    },
    "sam": {
        "display_name": "Sam",
        "guid": "UOOBQORBBE2LMHDZWZLYLCPRB4",
        "team_keys": [
            "222.l.727137.t.6",
            "242.l.162179.t.4",
            "257.l.208499.t.4",
            "273.l.159744.t.4",
            "314.l.42504.t.5",
            "331.l.37674.t.5",
            "348.l.125651.t.4",
            "359.l.229979.t.4",
            "371.l.472717.t.4",
            "380.l.217545.t.8"
        ]
    },
    "zef": {
        "display_name": "Zef",
        "guid": "3JYXPSSMU2OOSZEZYREF43ATIQ",
        "team_keys": [
            "175.l.492325.t.9",
            "199.l.394479.t.7",
            "222.l.727137.t.9",
            "242.l.162179.t.2",
            "257.l.208499.t.1",
            "273.l.159744.t.1",
            "314.l.42504.t.1",
            "331.l.37674.t.1",
            "348.l.125651.t.1",
            "359.l.229979.t.1",
            "371.l.472717.t.1",
            "380.l.217545.t.1",
            "390.l.322665.t.1",
            "399.l.129567.t.1",
            "406.l.768183.t.1",
            "414.l.392137.t.1",
            "423.l.495176.t.1",
            "449.l.150305.t.1",
            "461.l.501623.t.1"
        ]
    }
}


# Existing functions...
def get_known_league_key():
    return os.getenv("KNOWN_LEAGUE_KEY", LEAGUE_CONFIG["known_league_key"])

def get_known_season_year():
    return int(os.getenv("KNOWN_SEASON_YEAR", LEAGUE_CONFIG["known_season_year"]))

def get_first_season():
    return LEAGUE_CONFIG["first_season"]

def get_league_name():
    return LEAGUE_CONFIG["name"]

def get_founded_year():
    return LEAGUE_CONFIG["founded"]

def get_manual_season_mapping():
    return MANUAL_SEASON_MAPPING


# NEW: Manager identity helper function
def get_manager_identity(team_key: str = None, manager_guid: str = None):
    """
    Get manager identity using team_key or manager_guid.
    
    Priority:
    1. Try team_key match (most accurate for historical data)
    2. Try GUID match (future-proof for new seasons)
    3. Return None (unknown manager)
    
    Args:
        team_key: Full team key (e.g., "461.l.501623.t.6")
        manager_guid: Yahoo manager GUID from API
    
    Returns:
        dict: {"manager_id": "brian", "display_name": "Brian"} or None
    """
    # Method 1: Try team_key first (most accurate)
    if team_key:
        for manager_id, manager_data in MANAGER_IDENTITY_MAP.items():
            if team_key in manager_data.get("team_keys", []):
                return {
                    "manager_id": manager_id,
                    "display_name": manager_data["display_name"]
                }
    
    # Method 2: Try GUID (future-proof)
    if manager_guid:
        for manager_id, manager_data in MANAGER_IDENTITY_MAP.items():
            if manager_data.get("guid") == manager_guid:
                return {
                    "manager_id": manager_id,
                    "display_name": manager_data["display_name"]
                }
    
    # Not found
    return None

# League rules and payment information
LEAGUE_RULES = {
    "payment": {
        "entry_fee": 200,
        "total_pot": 2000,
        "num_teams": 10,
        "currency": "USD",
        
        "playoff_payouts": {
            "1st_place": {
                "amount": 700,
                "description": "Champion"
            },
            "2nd_place": {
                "amount": 200,
                "description": "Runner-up"
            },
            "3rd_place": {
                "amount": 100,
                "description": "Third place"
            }
        },
        
        "season_awards": {
            "best_record": {
                "amount": 200,
                "description": "Best regular season record"
            },
            "most_points": {
                "amount": 200,
                "description": "Highest total points scored in regular season"
            }
        },
        
        "weekly_prizes": {
            "high_score": {
                "amount": 20,
                "frequency": "weekly",
                "weeks": 15,
                "total": 300,
                "description": "Highest scoring team each week (Weeks 1-15)"
            },
            "position_leader": {
                "amount": 20,
                "frequency": "weekly",
                "weeks": 15,
                "total": 300,
                "description": "Team with highest-scoring player in randomly selected position each week",
                "positions": ["QB", "WR", "RB", "TE", "DEF"],
                "note": "Position randomly selected at start of season, repeats 3 times over 15 weeks"
            }
        },
        
        "payout_summary": {
            "playoff_total": 1000,
            "season_awards_total": 400,
            "weekly_prizes_total": 600,
            "grand_total": 2000
        },
        
        "payment_methods": ["Venmo", "Zelle", "Cash"],
        "payment_deadline": "Before draft begins",
        "notes": "Multiple ways to win throughout the season!"
    }
}


def get_payment_rules():
    """Get payment/prize structure"""
    return LEAGUE_RULES["payment"]

# ---------------------------------------------------------------------------
# League Eras
# ---------------------------------------------------------------------------
# Used across team_service, league_service, and any future analytics services.
# Each era has a slug (used as a dict key), display name, and year range.
# end_year=None means "present" (inclusive of current and future seasons).

LEAGUE_ERAS = {
    "overall": {
        "display_name": "Overall",
        "description": "All-time (2007–present)",
        "start_year": 2007,
        "end_year": None,
    },
    "darkness": {
        "display_name": "Darkness Era",
        "description": "2007–2011",
        "start_year": 2007,
        "end_year": 2011,
    },
    "samwise": {
        "display_name": "Samwise Era",
        "description": "2009–2018",
        "start_year": 2009,
        "end_year": 2018,
    },
    "fupa_frank": {
        "display_name": "Fupa Frank Era",
        "description": "2012–present",
        "start_year": 2012,
        "end_year": None,
    },
    "old_man": {
        "display_name": "Old Man Era",
        "description": "2019–present",
        "start_year": 2019,
        "end_year": None,
    },
    "auction": {
        "display_name": "Auction Era",
        "description": "2023–present",
        "start_year": 2023,
        "end_year": None,
    },
}


def get_league_eras():
    """Return the full era definitions dict."""
    return LEAGUE_ERAS


def get_era(slug: str) -> dict | None:
    """Return a single era by slug (e.g. 'darkness'), or None if not found."""
    return LEAGUE_ERAS.get(slug)


def year_in_era(year: int, era_slug: str) -> bool:
    """Return True if the given year falls within the named era."""
    era = LEAGUE_ERAS.get(era_slug)
    if not era:
        return False
    if year < era["start_year"]:
        return False
    if era["end_year"] is not None and year > era["end_year"]:
        return False
    return True


# ---------------------------------------------------------------------------
# Draft / Waiver hardcoded fallbacks
# ---------------------------------------------------------------------------
# Yahoo's settings API does not reliably expose auction_budget or faab_budget
# in older seasons. These are hardcoded here as a fallback.
# UPDATE THIS if the league ever changes the budget amount.
AUCTION_BUDGET_DEFAULT = 200   # dollars — used for both draft auction and FAAB
FAAB_BUDGET_DEFAULT    = 200   # dollars — waivers; same amount since 2016-ish


def get_auction_budget_default() -> int:
    return AUCTION_BUDGET_DEFAULT


def get_faab_budget_default() -> int:
    return FAAB_BUDGET_DEFAULT


# ---------------------------------------------------------------------------
# Season History — Manual / Hardcoded Data
# ---------------------------------------------------------------------------
# This dict stores data that cannot be reliably fetched from the Yahoo API:
#   - punishment: voted on each year by league members
#   - first_pick:  first overall draft pick (fallback if API fails)
#   - top_players: top fantasy scorer per position for that season
#                  (keyed by position: QB, WR, RB, TE)
#                  Populate this ONCE after each season ends using the
#                  /league/history/seed-players?year=YYYY admin endpoint,
#                  then paste the result here.
#
# For seasons pre-2012, top_players must be fully hardcoded (API unreliable).
# For 2012+, the live fetch is attempted first; this data is the fallback.
#
# top_players shape per position:
#   {
#       "name":   "Josh Allen",        # player name
#       "team":   "Blake",             # BlackGold display_name of the manager
#       "points": 412.50               # total fantasy points that season
#   }
#
# first_pick shape:
#   {
#       "player": "Christian McCaffrey",
#       "team":   "Zef",               # BlackGold display_name
#       "position": "RB"
#   }
# ---------------------------------------------------------------------------

SEASON_HISTORY_MANUAL = {
    2025: {
        "punishment": "Loser Wears a Caleb Williams Jersey Downtown before a Lions Game",
        "first_pick": None,  # TODO: populate or will be fetched live from API
        "top_players": None, # TODO: run seed-players endpoint after season ends
    },
    2024: {
        "punishment": "Loser Gets a Broccoli Dangle and Goes out to the Club Dressed like Gen Z",
        "first_pick": None,
        "top_players": None,
    },
    2023: {
        "punishment": "Loser Wears a Diaper at Next Year's Draft and Can't Take it Off Until Next Day or He Shits",
        "first_pick": None,
        "top_players": None,
    },
    2022: {
        "punishment": "Loser Wears a Diaper at Next Year's Draft and Can't Take it Off Until Next Day or He Shits",
        "first_pick": None,
        "top_players": None,
    },
    2021: {
        "punishment": "Loser Eats Surströmming",
        "first_pick": None,
        "top_players": None,
    },
    2020: {
        "punishment": "Loser Takes Blow Up Doll on a Date to Twin Peaks",
        "first_pick": None,
        "top_players": None,
    },
    2019: {
        "punishment": "Loser Gets Shot at with Paintballs",
        "first_pick": None,
        "top_players": None,
    },
    2018: {
        "punishment": "Loser Wears a Dress and Fake Nails at Next Draft",
        "first_pick": None,
        "top_players": None,
    },
    2017: {
        "punishment": "Loser Wears a Dress and Fake Nails at Next Draft",
        "first_pick": None,
        "top_players": None,
    },
    2016: {
        "punishment": "Loser Recreates ESPN The Body Issue",
        "first_pick": None,
        "top_players": None,
    },
    2015: {
        "punishment": "Loser Skates Around Campus Martius in a Tutu with an 'I Suck At Fantasy Football' Sign",
        "first_pick": None,
        "top_players": None,
    },
    2014: {
        "punishment": "Loser Wears a Dress and Stands at the Corner of Big Beaver with an 'I Suck At Fantasy Football' Sign",
        "first_pick": None,
        "top_players": None,
    },
    2013: {
        "punishment": "Loser Goes Out to the Bars with Frosted Tips",
        "first_pick": None,
        "top_players": None,
    },
    2012: {
        "punishment": "Loser Gets the Darkest Spray Tan",
        "first_pick": None,
        "top_players": None,
    },
    # Pre-2012: Yahoo stats API unreliable — top_players must be fully hardcoded
    2011: {
        "punishment": "Shot Out of Nick's Belly Button",
        "first_pick": None,
        "top_players": None,  # TODO: hardcode manually
    },
    2010: {
        "punishment": None,
        "first_pick": None,
        "top_players": None,
    },
    2009: {
        "punishment": None,
        "first_pick": None,
        "top_players": None,
    },
    2008: {
        "punishment": None,
        "first_pick": None,
        "top_players": None,
    },
    2007: {
        "punishment": None,
        "first_pick": None,
        "top_players": None,
    },
}


def get_season_manual_data(year: int) -> dict:
    """Return manual history data for a given season year, or empty dict."""
    return SEASON_HISTORY_MANUAL.get(year, {})


def get_all_manual_history() -> dict:
    """Return the full manual history dict."""
    return SEASON_HISTORY_MANUAL


# ---------------------------------------------------------------------------
# Player History — Per-Manager Hardcoded Data
# ---------------------------------------------------------------------------
# Populated by running GET /league/seed?year=YYYY after each season ends.
# Paste the returned config block here.
#
# Structure per manager per season:
#   top_starters: {
#       "QB": {"name": "Josh Allen",  "team_name": "Frank Black",
#              "total_points": 412.5, "weeks_started": 15},
#       "WR": {...}, "RB": {...}, "TE": {...}
#   }
#   frequent_players: [
#       {"name": "Ja'Marr Chase", "position": "WR",
#        "weeks_on_roster": 15, "weeks_as_starter": 14,
#        "total_points": 310.2},
#       ...  (top 10)
#   ]
#   starter_points_total: 1654.2   # sum of starter-slot points only
#   best_week:  {"week": 12, "points": 198.4}
#   worst_week: {"week":  3, "points":  62.1}
#
# Player history for /players endpoint, keyed by player_key:
#   players: {
#       "nfl.p.8793": {
#           "name": "Ja'Marr Chase", "position": "WR",
#           "total_points": 310.2,
#           "weeks_on_roster": 15, "weeks_as_starter": 14,
#           "acquired_type": "draft" | "waiver" | "trade",
#           "acquired_detail": "Pick 1.03" | "$42 FAAB" | "From: Zef",
#       }
#   }
# ---------------------------------------------------------------------------

PLAYER_HISTORY_MANUAL: dict = {
    # Format:
    # "brian": {
    #     2024: { "top_starters": {...}, "frequent_players": [...],
    #             "starter_points_total": ..., "players": {...} },
    #     2023: { ... },
    # },
}


def get_player_history(manager_id: str) -> dict:
    """Return all seeded season data for a manager, or empty dict."""
    return PLAYER_HISTORY_MANUAL.get(manager_id.lower(), {})


def get_player_history_season(manager_id: str, year: int) -> dict:
    """Return seeded data for a manager's specific season, or empty dict."""
    return PLAYER_HISTORY_MANUAL.get(manager_id.lower(), {}).get(year, {})