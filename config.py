"""
Application configuration for BlackGold Fantasy League
"""
import os

# Your league's base configuration
LEAGUE_CONFIG = {
    "name": "BlackGold",  # Normalized name for all seasons
    
    # Starting point - a known league ID/key from any season
    "known_league_key": "461.l.501623",  # 2025 season
    "known_season_year": 2025,
    
    # League history
    "first_season": 2007,  # When your league started
    
    # Cache settings
    "cache_duration_hours": 24,
}

# Manual season mapping for years where renew chain breaks
# The renew chain breaks at 2010, so we manually add 2007-2009
MANUAL_SEASON_MAPPING = {
    2009: {"game_id": 222, "league_id": "727137"},
    2008: {"game_id": 199, "league_id": "394479"},
    2007: {"game_id": 175, "league_id": "492325"},
}


def get_known_league_key():
    """Get a known league key to use as starting point"""
    return os.getenv("KNOWN_LEAGUE_KEY", LEAGUE_CONFIG["known_league_key"])


def get_known_season_year():
    """Get the year for the known league key"""
    return int(os.getenv("KNOWN_SEASON_YEAR", LEAGUE_CONFIG["known_season_year"]))


def get_first_season():
    """Get the first season year"""
    return LEAGUE_CONFIG["first_season"]


def get_league_name():
    """Get the normalized league name"""
    return LEAGUE_CONFIG["name"]


def get_manual_season_mapping():
    """Get manual season mapping for broken renew chains"""
    return MANUAL_SEASON_MAPPING