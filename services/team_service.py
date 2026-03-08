from services.yahoo_service import get_query
from services.league_service import (
    get_current_season,
    get_all_seasons,
    _convert_to_dict,
)
from config import get_manager_identity, get_league_name, MANAGER_IDENTITY_MAP


# ---------------------------------------------------------------------------
# Config-based helpers  (no API calls needed for identity resolution)
# ---------------------------------------------------------------------------

def _get_manager_data(display_name: str) -> dict | None:
    """
    Find a manager's full config entry by display_name (case-insensitive).
    Returns the manager dict (with manager_id injected) or None.
    """
    dn = display_name.lower()
    for manager_id, data in MANAGER_IDENTITY_MAP.items():
        if data["display_name"].lower() == dn:
            return {"manager_id": manager_id, **data}
    return None


def _get_team_key(display_name: str, league_key: str) -> str | None:
    """
    Return the team_key for a manager in a specific season using config.py.
    Zero API calls.

    Args:
        display_name: e.g. "Brian"
        league_key:   e.g. "461.l.501623"
    """
    manager_data = _get_manager_data(display_name)
    if not manager_data:
        return None
    for team_key in manager_data.get("team_keys", []):
        if team_key.startswith(league_key + ".t."):
            return team_key
    return None


def _get_seasons_for_manager(display_name: str) -> list[dict]:
    """
    Return every season a manager participated in, sorted oldest → newest.
    Uses config.py only — zero API calls.

    Returns list of {"year": int, "league_key": str, "team_key": str}
    """
    manager_data = _get_manager_data(display_name)
    if not manager_data:
        return []

    seasons_data = get_all_seasons()
    league_key_to_year = {
        s["league_key"]: s["year"] for s in seasons_data.get("seasons", [])
    }

    results = []
    for team_key in manager_data.get("team_keys", []):
        parts = team_key.split(".t.")
        if len(parts) != 2:
            continue
        league_key = parts[0]
        year = league_key_to_year.get(league_key)
        if year:
            results.append({
                "year": year,
                "league_key": league_key,
                "team_key": team_key,
            })

    return sorted(results, key=lambda s: s["year"])


def _resolve_year(year: str) -> str:
    if year == "current":
        return str(get_current_season())
    return year


# ---------------------------------------------------------------------------
# YFPY structure helpers — defensive parsing for list/dict inconsistencies
# ---------------------------------------------------------------------------

def _extract_manager_dict(team_dict: dict) -> dict:
    managers_raw = team_dict.get("managers", {})
    if isinstance(managers_raw, list):
        first = managers_raw[0] if managers_raw else {}
        return first.get("manager", first) if isinstance(first, dict) else {}
    if isinstance(managers_raw, dict):
        mgr = managers_raw.get("manager", {})
        if isinstance(mgr, list):
            return mgr[0] if mgr else {}
        return mgr
    return {}


def _extract_team_standings(team_dict: dict) -> dict:
    ts = team_dict.get("team_standings", {})
    if isinstance(ts, list):
        return ts[0] if ts else {}
    return ts if isinstance(ts, dict) else {}


def _extract_outcome_totals(team_standings: dict) -> dict:
    ot = team_standings.get("outcome_totals", {})
    if isinstance(ot, list):
        return ot[0] if ot else {}
    return ot if isinstance(ot, dict) else {}


def _extract_logo_url(team_dict: dict) -> str | None:
    logos = team_dict.get("team_logos", {})
    if isinstance(logos, list):
        logos = logos[0] if logos else {}
    logo = logos.get("team_logo", {}) if isinstance(logos, dict) else {}
    if isinstance(logo, list):
        logo = logo[0] if logo else {}
    return logo.get("url") if isinstance(logo, dict) else None


def _extract_teams_list(standings_dict) -> list:
    """
    Normalize get_league_standings() output to a plain list of unwrapped team dicts.
    Handles:
      {"teams": [{"team": {...}}, ...]}
      [{"team": {...}}, ...]
      [{"team_key": ...}, ...]   (already unwrapped)
    """
    if isinstance(standings_dict, list):
        raw_list = standings_dict
    elif isinstance(standings_dict, dict):
        raw_list = standings_dict.get("teams", [])
    else:
        return []

    result = []
    for item in raw_list:
        if isinstance(item, dict):
            result.append(item.get("team", item))
    return result


def _find_team_in_standings(teams_list: list, team_key: str) -> dict | None:
    for t in teams_list:
        if isinstance(t, dict) and t.get("team_key") == team_key:
            return t
    return None


def _get_all_team_map(query) -> dict:
    """Return {team_key: team_dict} for all teams. Used for name lookups."""
    raw = query.get_league_teams()
    teams_dict = _convert_to_dict(raw)
    teams_list = _extract_teams_list(teams_dict)
    return {t.get("team_key"): t for t in teams_list if isinstance(t, dict)}


def _resolve_opponent_name(opp_team_key: str, team_map: dict) -> str:
    """Resolve an opponent's display_name via config, falling back to team name."""
    identity = get_manager_identity(team_key=opp_team_key)
    if identity:
        return identity["display_name"]
    team_dict = team_map.get(opp_team_key, {})
    return team_dict.get("name", opp_team_key)


def _extract_points(team_wrapper: dict) -> float:
    pts_raw = team_wrapper.get("team_points") or {}
    if isinstance(pts_raw, list):
        pts_raw = pts_raw[0] if pts_raw else {}
    return float(pts_raw.get("total") or 0)


# ---------------------------------------------------------------------------
# /teams/managers  — List all managers (useful for frontend dropdowns)
# ---------------------------------------------------------------------------

def get_all_managers() -> dict:
    seasons_data = get_all_seasons()
    current_league_key = next(
        (s["league_key"] for s in seasons_data.get("seasons", []) if s.get("is_current")),
        None,
    )

    managers = []
    for manager_id, data in MANAGER_IDENTITY_MAP.items():
        team_keys = data.get("team_keys", [])
        is_active = any(
            tk.startswith(current_league_key + ".t.") for tk in team_keys
        ) if current_league_key else False

        managers.append({
            "manager_id": manager_id,
            "display_name": data["display_name"],
            "seasons_played": len(team_keys),
            "is_active": is_active,
        })

    managers.sort(key=lambda m: m["display_name"])
    return {"managers": managers, "total": len(managers)}


# ---------------------------------------------------------------------------
# /teams/{name}/overview  — Career summary across all seasons
# ---------------------------------------------------------------------------

def get_team_overview(display_name: str) -> dict:
    manager_data = _get_manager_data(display_name)
    if not manager_data:
        raise Exception(
            f"Manager '{display_name}' not found. "
            f"Call /teams/managers to see valid names."
        )

    num_teams = 10
    career = {
        "display_name": manager_data["display_name"],
        "manager_id": manager_data["manager_id"],
        "seasons_played": 0,
        "championships": 0,
        "last_place_finishes": 0,
        "playoff_appearances": 0,
        "total_wins": 0,
        "total_losses": 0,
        "total_ties": 0,
        "total_points_for": 0.0,
        "total_points_against": 0.0,
        "season_history": [],
    }

    for season in _get_seasons_for_manager(display_name):
        year = season["year"]
        league_key = season["league_key"]
        team_key = season["team_key"]

        try:
            query = get_query(league_key)
            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)
            teams_list = _extract_teams_list(standings_dict)
            t = _find_team_in_standings(teams_list, team_key)

            if not t:
                career["season_history"].append({"year": year, "error": "Team not found in standings"})
                continue

            ts = _extract_team_standings(t)
            ot = _extract_outcome_totals(ts)

            rank = ts.get("rank")
            seed = ts.get("playoff_seed")
            wins = int(ot.get("wins") or 0)
            losses = int(ot.get("losses") or 0)
            ties = int(ot.get("ties") or 0)
            pf = float(ts.get("points_for") or 0)
            pa = float(ts.get("points_against") or 0)

            career["seasons_played"] += 1
            career["total_wins"] += wins
            career["total_losses"] += losses
            career["total_ties"] += ties
            career["total_points_for"] += pf
            career["total_points_against"] += pa

            if rank == 1:
                career["championships"] += 1
            if rank == num_teams:
                career["last_place_finishes"] += 1
            try:
                if seed is not None and int(seed) <= 4:
                    career["playoff_appearances"] += 1
            except (ValueError, TypeError):
                pass

            career["season_history"].append({
                "year": year,
                "team_name": t.get("name"),
                "rank": rank,
                "playoff_seed": seed,
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "points_for": round(pf, 2),
                "points_against": round(pa, 2),
                "logo_url": _extract_logo_url(t),
            })

        except Exception as e:
            career["season_history"].append({"year": year, "error": str(e)})

    career["total_points_for"] = round(career["total_points_for"], 2)
    career["total_points_against"] = round(career["total_points_against"], 2)
    return career


# ---------------------------------------------------------------------------
# /teams/{name}/record  — Season-by-season W-L-T
# ---------------------------------------------------------------------------

def get_team_record(display_name: str) -> dict:
    manager_data = _get_manager_data(display_name)
    if not manager_data:
        raise Exception(f"Manager '{display_name}' not found.")

    records = []

    for season in reversed(_get_seasons_for_manager(display_name)):
        year = season["year"]
        league_key = season["league_key"]
        team_key = season["team_key"]

        try:
            query = get_query(league_key)
            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)
            teams_list = _extract_teams_list(standings_dict)
            t = _find_team_in_standings(teams_list, team_key)

            if not t:
                records.append({"year": year, "error": "Team not found in standings"})
                continue

            ts = _extract_team_standings(t)
            ot = _extract_outcome_totals(ts)
            streak = ts.get("streak", {})
            if isinstance(streak, list):
                streak = streak[0] if streak else {}

            records.append({
                "year": year,
                "team_name": t.get("name"),
                "rank": ts.get("rank"),
                "playoff_seed": ts.get("playoff_seed"),
                "wins": ot.get("wins"),
                "losses": ot.get("losses"),
                "ties": ot.get("ties"),
                "win_pct": ot.get("percentage"),
                "points_for": ts.get("points_for"),
                "points_against": ts.get("points_against"),
                "clinched_playoffs": bool(t.get("clinched_playoffs", 0)),
                "final_streak_type": streak.get("type"),
                "final_streak_value": streak.get("value"),
                "number_of_moves": t.get("number_of_moves"),
                "number_of_trades": t.get("number_of_trades"),
            })

        except Exception as e:
            records.append({"year": year, "error": str(e)})

    return {
        "display_name": manager_data["display_name"],
        "records": records,
        "total_seasons": len([r for r in records if "error" not in r]),
    }


# ---------------------------------------------------------------------------
# /teams/{name}/points  — Points for/against per season
# ---------------------------------------------------------------------------

def get_team_points(display_name: str) -> dict:
    manager_data = _get_manager_data(display_name)
    if not manager_data:
        raise Exception(f"Manager '{display_name}' not found.")

    points_history = []

    for season in reversed(_get_seasons_for_manager(display_name)):
        year = season["year"]
        league_key = season["league_key"]
        team_key = season["team_key"]

        try:
            query = get_query(league_key)
            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)
            teams_list = _extract_teams_list(standings_dict)

            all_pf = [
                (t.get("team_key"), float(_extract_team_standings(t).get("points_for") or 0))
                for t in teams_list if isinstance(t, dict)
            ]

            t = _find_team_in_standings(teams_list, team_key)
            if not t:
                points_history.append({"year": year, "error": "Team not found in standings"})
                continue

            ts = _extract_team_standings(t)
            pf = float(ts.get("points_for") or 0)
            pa = float(ts.get("points_against") or 0)

            sorted_pf = sorted(all_pf, key=lambda x: x[1], reverse=True)
            points_rank = next(
                (i + 1 for i, (tk, _) in enumerate(sorted_pf) if tk == team_key), None
            )

            points_history.append({
                "year": year,
                "team_name": t.get("name"),
                "points_for": round(pf, 2),
                "points_against": round(pa, 2),
                "points_differential": round(pf - pa, 2),
                "points_rank": points_rank,
                "overall_rank": ts.get("rank"),
            })

        except Exception as e:
            points_history.append({"year": year, "error": str(e)})

    return {
        "display_name": manager_data["display_name"],
        "points_history": points_history,
    }


# ---------------------------------------------------------------------------
# /teams/{name}/matchups  — Matchups + H2H summary for a season
# ---------------------------------------------------------------------------

def get_team_matchups(display_name: str, year: str = "current") -> dict:
    year = _resolve_year(year)
    from services.league_service import get_league_key_for_season
    league_key = get_league_key_for_season(year)

    team_key = _get_team_key(display_name, league_key)
    if not team_key:
        raise Exception(f"Manager '{display_name}' not found in {year} season.")

    query = get_query(league_key)
    team_map = _get_all_team_map(query)

    raw_matchups = query.get_team_matchups(team_key)
    matchups_dict = _convert_to_dict(raw_matchups)

    if isinstance(matchups_dict, dict):
        matchups_raw = matchups_dict.get("matchups", [])
    elif isinstance(matchups_dict, list):
        matchups_raw = matchups_dict
    else:
        matchups_raw = []

    matchup_list = []
    h2h = {}

    for m in matchups_raw:
        matchup = m.get("matchup", m) if isinstance(m, dict) else {}
        teams = matchup.get("teams", [])
        if isinstance(teams, dict):
            teams = list(teams.values())

        my_points = None
        opp_points = None
        opp_team_key = None

        for tw in teams:
            t = tw.get("team", tw) if isinstance(tw, dict) else {}
            tk = t.get("team_key")
            pts = _extract_points(t)
            if tk == team_key:
                my_points = pts
            else:
                opp_points = pts
                opp_team_key = tk

        if not opp_team_key:
            continue

        opp_name = _resolve_opponent_name(opp_team_key, team_map)
        winner_key = matchup.get("winner_team_key")
        is_tied = bool(int(matchup.get("is_tied", 0) or 0))

        if opp_team_key not in h2h:
            h2h[opp_team_key] = {
                "opponent_name": opp_name,
                "wins": 0, "losses": 0, "ties": 0,
            }

        if is_tied:
            h2h[opp_team_key]["ties"] += 1
            result = "T"
        elif winner_key == team_key:
            h2h[opp_team_key]["wins"] += 1
            result = "W"
        else:
            h2h[opp_team_key]["losses"] += 1
            result = "L"

        matchup_list.append({
            "week": matchup.get("week"),
            "is_playoffs": bool(int(matchup.get("is_playoffs", 0) or 0)),
            "is_consolation": bool(int(matchup.get("is_consolation", 0) or 0)),
            "result": result,
            "my_points": my_points,
            "opponent_name": opp_name,
            "opponent_points": opp_points,
            "margin": round((my_points or 0) - (opp_points or 0), 2),
        })

    matchup_list.sort(key=lambda m: int(m.get("week") or 0))

    return {
        "display_name": display_name,
        "year": year,
        "matchups": matchup_list,
        "h2h_summary": list(h2h.values()),
        "total_matchups": len(matchup_list),
    }


# ---------------------------------------------------------------------------
# /teams/{name}/trades  — All trades in a season
# ---------------------------------------------------------------------------

def get_team_trades(display_name: str, year: str = "current") -> dict:
    year = _resolve_year(year)
    from services.league_service import get_league_key_for_season
    league_key = get_league_key_for_season(year)

    team_key = _get_team_key(display_name, league_key)
    if not team_key:
        raise Exception(f"Manager '{display_name}' not found in {year} season.")

    query = get_query(league_key)
    team_map = _get_all_team_map(query)

    raw_transactions = query.get_league_transactions()
    transactions_dict = _convert_to_dict(raw_transactions)

    if isinstance(transactions_dict, dict):
        transactions = transactions_dict.get("transactions", [])
    elif isinstance(transactions_dict, list):
        transactions = transactions_dict
    else:
        transactions = []

    import datetime
    trades = []

    for wrapper in transactions:
        tx = wrapper.get("transaction", wrapper) if isinstance(wrapper, dict) else {}
        if tx.get("type") != "trade" or tx.get("status") != "successful":
            continue

        trader_key = tx.get("trader_team_key")
        tradee_key = tx.get("tradee_team_key")
        if team_key not in (trader_key, tradee_key):
            continue

        opp_key = tradee_key if trader_key == team_key else trader_key
        opp_name = _resolve_opponent_name(opp_key, team_map)

        ts = tx.get("timestamp")
        trade_date = (
            datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d") if ts else None
        )

        players_raw = tx.get("players", [])
        if isinstance(players_raw, dict):
            players_raw = list(players_raw.values())

        received, sent = [], []
        for p_wrapper in players_raw:
            p = p_wrapper.get("player", p_wrapper) if isinstance(p_wrapper, dict) else {}
            name_raw = p.get("name", {})
            p_name = name_raw.get("full") if isinstance(name_raw, dict) else str(name_raw)
            p_pos = p.get("display_position") or p.get("position_type")
            td = p.get("transaction_data", {})
            if isinstance(td, list):
                td = td[0] if td else {}

            player_info = {"player_key": p.get("player_key"), "name": p_name, "position": p_pos}
            if td.get("destination_team_key") == team_key:
                received.append(player_info)
            elif td.get("source_team_key") == team_key:
                sent.append(player_info)

        trades.append({
            "transaction_key": tx.get("transaction_key"),
            "trade_date": trade_date,
            "opponent_name": opp_name,
            "players_received": received,
            "players_sent": sent,
        })

    return {
        "display_name": display_name,
        "year": year,
        "trades": trades,
        "total_trades": len(trades),
    }


# ---------------------------------------------------------------------------
# /teams/all/records  — All teams W-L-T for a season
# ---------------------------------------------------------------------------

def get_all_teams_records(year: str = "current") -> dict:
    year = _resolve_year(year)
    from services.league_service import get_league_key_for_season
    league_key = get_league_key_for_season(year)
    query = get_query(league_key)

    standings_raw = query.get_league_standings()
    standings_dict = _convert_to_dict(standings_raw)
    teams_list = _extract_teams_list(standings_dict)

    teams = []
    for t in teams_list:
        if not isinstance(t, dict):
            continue
        ts = _extract_team_standings(t)
        ot = _extract_outcome_totals(ts)
        team_key = t.get("team_key")
        identity = get_manager_identity(team_key=team_key)

        teams.append({
            "team_key": team_key,
            "team_name": t.get("name"),
            "display_name": identity["display_name"] if identity else t.get("name"),
            "manager_id": identity["manager_id"] if identity else None,
            "rank": ts.get("rank"),
            "playoff_seed": ts.get("playoff_seed"),
            "wins": ot.get("wins"),
            "losses": ot.get("losses"),
            "ties": ot.get("ties"),
            "win_pct": ot.get("percentage"),
            "points_for": ts.get("points_for"),
            "points_against": ts.get("points_against"),
            "clinched_playoffs": bool(t.get("clinched_playoffs", 0)),
            "logo_url": _extract_logo_url(t),
        })

    teams.sort(key=lambda x: (x.get("rank") or 999))
    return {"year": year, "league_name": get_league_name(), "teams": teams}


# ---------------------------------------------------------------------------
# /teams/all/points  — Points leaderboard
# ---------------------------------------------------------------------------

def get_all_teams_points(year: str = "current") -> dict:
    result = get_all_teams_records(year)
    result["teams"].sort(key=lambda x: float(x.get("points_for") or 0), reverse=True)
    for idx, t in enumerate(result["teams"], 1):
        t["points_rank"] = idx
    return result


# ---------------------------------------------------------------------------
# /teams/{name1}/vs/{name2}  — H2H between two managers
# ---------------------------------------------------------------------------

def get_h2h_matchups(name1: str, name2: str, year: str = "current") -> dict:
    if year == "all":
        return _get_h2h_all_seasons(name1, name2)

    year = _resolve_year(year)
    from services.league_service import get_league_key_for_season
    league_key = get_league_key_for_season(year)

    team_key1 = _get_team_key(name1, league_key)
    team_key2 = _get_team_key(name2, league_key)

    if not team_key1:
        raise Exception(f"Manager '{name1}' not found in {year} season.")
    if not team_key2:
        raise Exception(f"Manager '{name2}' not found in {year} season.")

    query = get_query(league_key)
    raw_matchups = query.get_team_matchups(team_key1)
    matchups_dict = _convert_to_dict(raw_matchups)

    if isinstance(matchups_dict, dict):
        matchups_raw = matchups_dict.get("matchups", [])
    elif isinstance(matchups_dict, list):
        matchups_raw = matchups_dict
    else:
        matchups_raw = []

    matchups = []
    summary = {"name1_wins": 0, "name2_wins": 0, "ties": 0}

    for m in matchups_raw:
        matchup = m.get("matchup", m) if isinstance(m, dict) else {}
        teams = matchup.get("teams", [])
        if isinstance(teams, dict):
            teams = list(teams.values())

        points_map = {}
        found_opp = False
        for tw in teams:
            t = tw.get("team", tw) if isinstance(tw, dict) else {}
            tk = t.get("team_key")
            points_map[tk] = _extract_points(t)
            if tk == team_key2:
                found_opp = True

        if not found_opp:
            continue

        winner_key = matchup.get("winner_team_key")
        is_tied = bool(int(matchup.get("is_tied", 0) or 0))

        if is_tied:
            summary["ties"] += 1
            winner = "tie"
        elif winner_key == team_key1:
            summary["name1_wins"] += 1
            winner = name1
        else:
            summary["name2_wins"] += 1
            winner = name2

        matchups.append({
            "week": matchup.get("week"),
            "year": year,
            "is_playoffs": bool(int(matchup.get("is_playoffs", 0) or 0)),
            "is_consolation": bool(int(matchup.get("is_consolation", 0) or 0)),
            f"{name1.lower()}_points": points_map.get(team_key1),
            f"{name2.lower()}_points": points_map.get(team_key2),
            "margin": round(
                (points_map.get(team_key1) or 0) - (points_map.get(team_key2) or 0), 2
            ),
            "winner": winner,
        })

    matchups.sort(key=lambda m: int(m.get("week") or 0))
    return {"name1": name1, "name2": name2, "year": year, "summary": summary, "matchups": matchups}


def _get_h2h_all_seasons(name1: str, name2: str) -> dict:
    all_matchups = []
    total_summary = {"name1_wins": 0, "name2_wins": 0, "ties": 0}

    seasons_data = get_all_seasons()
    for season in sorted(seasons_data.get("seasons", []), key=lambda s: s["year"], reverse=True):
        year = str(season["year"])
        try:
            result = get_h2h_matchups(name1, name2, year=year)
            all_matchups.extend(result["matchups"])
            total_summary["name1_wins"] += result["summary"]["name1_wins"]
            total_summary["name2_wins"] += result["summary"]["name2_wins"]
            total_summary["ties"] += result["summary"]["ties"]
        except Exception:
            continue

    return {"name1": name1, "name2": name2, "year": "all", "summary": total_summary, "matchups": all_matchups}