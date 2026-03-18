"""
Shared Configuration
====================
Sport-agnostic config used across fantasy, basketball, and any
future sports sections. Includes era definitions and budget defaults.
"""

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