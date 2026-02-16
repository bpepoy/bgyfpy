"""
Application configuration for BlackGold Fantasy League
"""
import os

# Your league's base configuration
LEAGUE_CONFIG = {
    "name": "BlackGold",  # Normalized name for all seasons
    
    # Starting point - a known league ID/key from any season
    # This is used as the entry point to discover all seasons
    "known_league_key": "461.l.501623",  # 2025 season
    "known_season_year": 2025,
    
    # League history
    "first_season": 2007,  # When your league started
    
    # Cache settings
    "cache_duration_hours": 24,  # How long to cache season data
}


def get_known_league_key():
    """
    Get a known league key to use as starting point.
    This can be from any season - we'll discover the rest.
    """
    # Allow override via environment variable for easy updates
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