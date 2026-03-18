"""
Config Package
==============
Re-exports everything from sub-modules so that existing imports
like `from config import get_league_name` keep working without changes.

Direct imports for sport-specific config:
  from config.fantasy    import MANAGER_IDENTITY_MAP, get_league_name, ...
  from config.basketball import NBA_MANAGER_IDENTITY_MAP, get_nba_league_name, ...
  from config.shared     import LEAGUE_ERAS, get_league_eras, ...
  from config.users      import USERS, get_user, has_permission, ...
"""

# Fantasy (BlackGold NFL) — all existing imports keep working
from config.fantasy import (
    LEAGUE_CONFIG,
    MANUAL_SEASON_MAPPING,
    MANAGER_IDENTITY_MAP,
    LEAGUE_RULES,
    SEASON_HISTORY_MANUAL,
    PLAYER_HISTORY_MANUAL,
    get_known_league_key,
    get_known_season_year,
    get_first_season,
    get_league_name,
    get_founded_year,
    get_manual_season_mapping,
    get_manager_identity,
    get_payment_rules,
    get_season_manual_data,
    get_all_manual_history,
    get_player_history,
    get_player_history_season,
    get_auction_budget_default,
    get_faab_budget_default,
)

# Shared / sport-agnostic
from config.shared import (
    LEAGUE_ERAS,
    AUCTION_BUDGET_DEFAULT,
    FAAB_BUDGET_DEFAULT,
    get_league_eras,
    get_era,
    year_in_era,
)

# Basketball (Real Bros NBA)
from config.basketball import (
    NBA_LEAGUE_CONFIG,
    NBA_MANAGER_IDENTITY_MAP,
    NBA_SEASON_HISTORY_MANUAL,
    get_nba_known_league_key,
    get_nba_league_name,
    get_nba_manager_identity,
    get_nba_season_manual_data,
)

# Users and roles
from config.users import (
    USERS,
    ROLE_PERMISSIONS,
    get_user,
    get_user_role,
    has_permission,
    is_known_user,
    get_all_users,
)

__all__ = [
    # Fantasy
    "LEAGUE_CONFIG", "MANUAL_SEASON_MAPPING", "MANAGER_IDENTITY_MAP",
    "LEAGUE_RULES", "SEASON_HISTORY_MANUAL", "PLAYER_HISTORY_MANUAL",
    "get_known_league_key", "get_known_season_year", "get_first_season",
    "get_league_name", "get_founded_year", "get_manual_season_mapping",
    "get_manager_identity", "get_payment_rules", "get_season_manual_data",
    "get_all_manual_history", "get_player_history", "get_player_history_season",
    "get_auction_budget_default", "get_faab_budget_default",
    # Shared
    "LEAGUE_ERAS", "AUCTION_BUDGET_DEFAULT", "FAAB_BUDGET_DEFAULT",
    "get_league_eras", "get_era", "year_in_era",
    # Basketball
    "NBA_LEAGUE_CONFIG", "NBA_MANAGER_IDENTITY_MAP", "NBA_SEASON_HISTORY_MANUAL",
    "get_nba_known_league_key", "get_nba_league_name",
    "get_nba_manager_identity", "get_nba_season_manual_data",
    # Users
    "USERS", "ROLE_PERMISSIONS", "get_user", "get_user_role",
    "has_permission", "is_known_user", "get_all_users",
]
