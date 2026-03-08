from services.yahoo_service import get_query
from services.league_service import (
    get_league_key_for_season,
    get_current_season,
    get_all_seasons,
    _convert_to_dict,
    _safe_get,
)
from config import get_manager_identity, get_league_name


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_year(year: str) -> str:
    """Resolve 'current' alias to the actual season year string."""
    if year == "current":
        return str(get_current_season())
    return year


def _get_all_team_keys(query) -> dict:
    """
    Return a mapping of { team_key: team_dict } for every team in the league.
    Used internally to look up team info without an extra API call.
    """
    raw = query.get_league_teams()
    teams_dict = _convert_to_dict(raw)
    mapping = {}
    for wrapper in teams_dict.get("teams", []):
        t = wrapper.get("team", {})
        mapping[t.get("team_key")] = t
    return mapping


def _manager_info(team_dict: dict) -> dict:
    """Extract and enrich manager info from a raw team dict."""
    managers_data = team_dict.get("managers", {})
    mgr = managers_data.get("manager", {})
    guid = mgr.get("guid")
    team_key = team_dict.get("team_key")

    identity = get_manager_identity(team_key=team_key, manager_guid=guid)
    return {
        "manager_guid": guid,
        "manager_nickname": mgr.get("nickname"),
        "manager_id": identity["manager_id"] if identity else None,
        "manager_display_name": identity["display_name"] if identity else mgr.get("nickname"),
        "manager_image_url": mgr.get("image_url"),
        "manager_felo_score": mgr.get("felo_score"),
        "manager_felo_tier": mgr.get("felo_tier"),
    }


def _logo_url(team_dict: dict) -> str | None:
    logos = team_dict.get("team_logos", {})
    logo = logos.get("team_logo", {})
    return logo.get("url")


# ---------------------------------------------------------------------------
# Team lookup helpers (resolve guid → team_key for a given season)
# ---------------------------------------------------------------------------

def get_team_key_for_guid(query, guid: str) -> str | None:
    """
    Find the team_key for a manager's GUID within the given season's query context.
    Returns None if the GUID is not found.
    """
    teams_dict = _convert_to_dict(query.get_league_teams())
    for wrapper in teams_dict.get("teams", []):
        t = wrapper.get("team", {})
        mgr = t.get("managers", {}).get("manager", {})
        if mgr.get("guid") == guid:
            return t.get("team_key")
    return None


# ---------------------------------------------------------------------------
# /fantasy/{guid}/home  –  Team overview (all seasons summary)
# ---------------------------------------------------------------------------

def get_team_overview(guid: str) -> dict:
    """
    Returns a high-level career summary for one manager across all seasons:
    total seasons, championships, last-place finishes, and cumulative points.
    """
    seasons_data = get_all_seasons()
    all_seasons = seasons_data.get("seasons", [])

    career = {
        "guid": guid,
        "manager_display_name": None,
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

    num_teams = 10  # BlackGold always has 10 teams

    for season in sorted(all_seasons, key=lambda s: s["year"]):
        year = season["year"]
        league_key = season["league_key"]

        try:
            query = get_query(league_key)
            team_key = get_team_key_for_guid(query, guid)
            if not team_key:
                continue  # Manager was not in this season

            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)

            for wrapper in standings_dict.get("teams", []):
                t = wrapper.get("team", {})
                if t.get("team_key") != team_key:
                    continue

                mgr = t.get("managers", {}).get("manager", {})
                identity = get_manager_identity(team_key=team_key, manager_guid=guid)

                ts = t.get("team_standings", {})
                ot = ts.get("outcome_totals", {})
                rank = ts.get("rank")
                seed = ts.get("playoff_seed")

                wins = int(ot.get("wins") or 0)
                losses = int(ot.get("losses") or 0)
                ties = int(ot.get("ties") or 0)
                pf = float(ts.get("points_for") or 0)
                pa = float(ts.get("points_against") or 0)

                # Populate display name on first found
                if not career["manager_display_name"]:
                    career["manager_display_name"] = (
                        identity["display_name"] if identity else mgr.get("nickname")
                    )

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
                if seed is not None and int(seed) <= 4:
                    career["playoff_appearances"] += 1

                career["season_history"].append({
                    "year": year,
                    "team_name": t.get("name"),
                    "rank": rank,
                    "playoff_seed": seed,
                    "wins": wins,
                    "losses": losses,
                    "ties": ties,
                    "points_for": pf,
                    "points_against": pa,
                    "logo_url": _logo_url(t),
                })
                break

        except Exception as e:
            career["season_history"].append({"year": year, "error": str(e)})

    # Round career totals
    career["total_points_for"] = round(career["total_points_for"], 2)
    career["total_points_against"] = round(career["total_points_against"], 2)

    return career


# ---------------------------------------------------------------------------
# /fantasy/{guid}/record  –  W-L-T per season
# ---------------------------------------------------------------------------

def get_team_record(guid: str) -> dict:
    """
    Returns W-L-T record for every season the manager participated in,
    including luck metric (actual wins vs expected wins based on weekly scores).
    """
    seasons_data = get_all_seasons()
    records = []

    for season in sorted(seasons_data.get("seasons", []), key=lambda s: s["year"], reverse=True):
        year = season["year"]
        league_key = season["league_key"]

        try:
            query = get_query(league_key)
            team_key = get_team_key_for_guid(query, guid)
            if not team_key:
                continue

            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)

            for wrapper in standings_dict.get("teams", []):
                t = wrapper.get("team", {})
                if t.get("team_key") != team_key:
                    continue

                ts = t.get("team_standings", {})
                ot = ts.get("outcome_totals", {})
                streak = ts.get("streak", {})

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
                break

        except Exception as e:
            records.append({"year": year, "error": str(e)})

    return {
        "guid": guid,
        "records": records,
        "total_seasons": len([r for r in records if "error" not in r]),
    }


# ---------------------------------------------------------------------------
# /fantasy/{guid}/points  –  Points for/against per season
# ---------------------------------------------------------------------------

def get_team_points(guid: str) -> dict:
    """
    Returns points for/against for every season, plus per-season ranking
    and weekly breakdowns for the current/specified season.
    """
    seasons_data = get_all_seasons()
    points_history = []

    for season in sorted(seasons_data.get("seasons", []), key=lambda s: s["year"], reverse=True):
        year = season["year"]
        league_key = season["league_key"]

        try:
            query = get_query(league_key)
            team_key = get_team_key_for_guid(query, guid)
            if not team_key:
                continue

            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)

            # Collect all teams' points_for to calculate rank
            all_pf = []
            team_entry = None

            for wrapper in standings_dict.get("teams", []):
                t = wrapper.get("team", {})
                ts = t.get("team_standings", {})
                pf = float(ts.get("points_for") or 0)
                all_pf.append((t.get("team_key"), pf))
                if t.get("team_key") == team_key:
                    team_entry = (t, ts)

            if not team_entry:
                continue

            t, ts = team_entry
            pf = float(ts.get("points_for") or 0)
            pa = float(ts.get("points_against") or 0)

            # Points rank (1 = highest scorer)
            sorted_pf = sorted(all_pf, key=lambda x: x[1], reverse=True)
            points_rank = next(
                (i + 1 for i, (tk, _) in enumerate(sorted_pf) if tk == team_key), None
            )

            points_history.append({
                "year": year,
                "team_name": t.get("name"),
                "points_for": pf,
                "points_against": pa,
                "points_differential": round(pf - pa, 2),
                "points_rank": points_rank,
                "overall_rank": ts.get("rank"),
            })

        except Exception as e:
            points_history.append({"year": year, "error": str(e)})

    return {
        "guid": guid,
        "points_history": points_history,
    }


# ---------------------------------------------------------------------------
# /fantasy/{guid}/matchups  –  All matchups (H2H summary vs every opponent)
# ---------------------------------------------------------------------------

def get_team_matchups(guid: str, year: str = "current") -> dict:
    """
    Returns all matchups for the manager in a given season,
    plus an H2H summary (W-L-T) against each opponent.
    """
    year = _resolve_year(year)
    league_key = get_league_key_for_season(year)
    query = get_query(league_key)

    team_key = get_team_key_for_guid(query, guid)
    if not team_key:
        raise Exception(f"Manager GUID {guid} not found in {year} season")

    # Get team name map for this season
    team_map = _get_all_team_keys(query)

    # Fetch all matchups for this team
    raw_matchups = query.get_team_matchups(team_key)
    matchups_dict = _convert_to_dict(raw_matchups)

    matchup_list = []
    h2h = {}  # opponent_team_key → { wins, losses, ties }

    for m in matchups_dict.get("matchups", []):
        matchup = m.get("matchup", m)  # handle both wrapped and unwrapped

        week = matchup.get("week")
        is_playoffs = bool(int(matchup.get("is_playoffs", 0)))
        is_consolation = bool(int(matchup.get("is_consolation", 0)))
        winner_key = matchup.get("winner_team_key")
        is_tied = bool(int(matchup.get("is_tied", 0)))

        teams = matchup.get("teams", [])

        my_points = None
        opp_points = None
        opp_team_key = None
        opp_name = None

        for team_wrapper in teams:
            t = team_wrapper.get("team", team_wrapper)
            tk = t.get("team_key")
            pts = float((t.get("team_points") or {}).get("total") or 0)

            if tk == team_key:
                my_points = pts
            else:
                opp_points = pts
                opp_team_key = tk
                opp_info = team_map.get(tk, {})
                opp_name = opp_info.get("name", tk)

        if opp_team_key:
            if opp_team_key not in h2h:
                h2h[opp_team_key] = {
                    "opponent_team_key": opp_team_key,
                    "opponent_name": opp_name,
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
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
                "week": week,
                "is_playoffs": is_playoffs,
                "is_consolation": is_consolation,
                "result": result,
                "my_points": my_points,
                "opponent_team_key": opp_team_key,
                "opponent_name": opp_name,
                "opponent_points": opp_points,
                "margin": round((my_points or 0) - (opp_points or 0), 2),
                "is_tied": is_tied,
            })

    # Sort matchups by week
    matchup_list.sort(key=lambda m: int(m["week"] or 0))

    return {
        "guid": guid,
        "year": year,
        "team_key": team_key,
        "matchups": matchup_list,
        "h2h_summary": list(h2h.values()),
        "total_matchups": len(matchup_list),
    }


# ---------------------------------------------------------------------------
# /fantasy/{guid}/trades  –  All trades the manager has made
# ---------------------------------------------------------------------------

def get_team_trades(guid: str, year: str = "current") -> dict:
    """
    Returns all trades involving this manager's team in a given season,
    with full player details for each side of the trade.
    """
    year = _resolve_year(year)
    league_key = get_league_key_for_season(year)
    query = get_query(league_key)

    team_key = get_team_key_for_guid(query, guid)
    if not team_key:
        raise Exception(f"Manager GUID {guid} not found in {year} season")

    team_map = _get_all_team_keys(query)

    raw_transactions = query.get_league_transactions()
    transactions_dict = _convert_to_dict(raw_transactions)

    trades = []

    transactions = transactions_dict.get("transactions", [])
    if not transactions:
        # Some seasons wrap differently
        transactions = transactions_dict if isinstance(transactions_dict, list) else []

    for wrapper in transactions:
        tx = wrapper.get("transaction", wrapper)
        if tx.get("type") != "trade":
            continue
        if tx.get("status") != "successful":
            continue

        trader_key = tx.get("trader_team_key")
        tradee_key = tx.get("tradee_team_key")

        # Only include if this team is involved
        if team_key not in (trader_key, tradee_key):
            continue

        opp_key = tradee_key if trader_key == team_key else trader_key
        opp_info = team_map.get(opp_key, {})

        import datetime
        ts = tx.get("timestamp")
        trade_date = (
            datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
            if ts
            else None
        )

        # Split players by direction
        received = []
        sent = []

        for p_wrapper in tx.get("players", []):
            p = p_wrapper.get("player", p_wrapper)
            p_name = _safe_get(p.get("name", {}), "full") or p.get("name")
            p_position = p.get("display_position") or p.get("position_type")
            td = p.get("transaction_data", {})
            dest = td.get("destination_team_key")
            src = td.get("source_team_key")

            player_info = {
                "player_key": p.get("player_key"),
                "name": p_name,
                "position": p_position,
            }

            if dest == team_key:
                received.append(player_info)
            elif src == team_key:
                sent.append(player_info)

        trades.append({
            "transaction_key": tx.get("transaction_key"),
            "trade_date": trade_date,
            "opponent_team_key": opp_key,
            "opponent_name": opp_info.get("name", opp_key),
            "players_received": received,
            "players_sent": sent,
        })

    return {
        "guid": guid,
        "year": year,
        "team_key": team_key,
        "trades": trades,
        "total_trades": len(trades),
    }


# ---------------------------------------------------------------------------
# /fantasy/teams/records  –  All-team records comparison
# ---------------------------------------------------------------------------

def get_all_teams_records(year: str = "current") -> dict:
    """
    Returns W-L-T, points, and ranking for every team in a given season.
    """
    year = _resolve_year(year)
    league_key = get_league_key_for_season(year)
    query = get_query(league_key)

    standings_raw = query.get_league_standings()
    standings_dict = _convert_to_dict(standings_raw)

    teams = []
    for wrapper in standings_dict.get("teams", []):
        t = wrapper.get("team", {})
        ts = t.get("team_standings", {})
        ot = ts.get("outcome_totals", {})

        mgr_info = _manager_info(t)

        teams.append({
            "team_key": t.get("team_key"),
            "team_id": t.get("team_id"),
            "name": t.get("name"),
            "rank": ts.get("rank"),
            "playoff_seed": ts.get("playoff_seed"),
            "wins": ot.get("wins"),
            "losses": ot.get("losses"),
            "ties": ot.get("ties"),
            "win_pct": ot.get("percentage"),
            "points_for": ts.get("points_for"),
            "points_against": ts.get("points_against"),
            "clinched_playoffs": bool(t.get("clinched_playoffs", 0)),
            "logo_url": _logo_url(t),
            **mgr_info,
        })

    teams.sort(key=lambda x: (x.get("rank") or 999))

    return {
        "year": year,
        "league_name": get_league_name(),
        "teams": teams,
    }


# ---------------------------------------------------------------------------
# /fantasy/teams/points  –  Points leaderboard
# ---------------------------------------------------------------------------

def get_all_teams_points(year: str = "current") -> dict:
    """
    Returns points for/against for all teams in a season, sorted by points scored.
    """
    result = get_all_teams_records(year)
    teams = result["teams"]

    # Sort by points_for descending
    teams.sort(key=lambda x: float(x.get("points_for") or 0), reverse=True)

    for idx, t in enumerate(teams, 1):
        t["points_rank"] = idx

    return {
        "year": result["year"],
        "league_name": result["league_name"],
        "teams": teams,
    }


# ---------------------------------------------------------------------------
# /fantasy/teams/matchups/{team1}/vs/{team2}  –  H2H between two teams
# ---------------------------------------------------------------------------

def get_h2h_matchups(guid1: str, guid2: str, year: str = "current") -> dict:
    """
    Returns the head-to-head matchup history between two managers for a season.
    Pass year='all' to aggregate across all seasons.
    """
    if year == "all":
        return _get_h2h_all_seasons(guid1, guid2)

    year = _resolve_year(year)
    league_key = get_league_key_for_season(year)
    query = get_query(league_key)

    team_key1 = get_team_key_for_guid(query, guid1)
    team_key2 = get_team_key_for_guid(query, guid2)

    if not team_key1:
        raise Exception(f"Manager GUID {guid1} not found in {year} season")
    if not team_key2:
        raise Exception(f"Manager GUID {guid2} not found in {year} season")

    raw_matchups = query.get_team_matchups(team_key1)
    matchups_dict = _convert_to_dict(raw_matchups)

    matchups = []
    summary = {"team1_wins": 0, "team2_wins": 0, "ties": 0}

    for m in matchups_dict.get("matchups", []):
        matchup = m.get("matchup", m)

        teams = matchup.get("teams", [])
        team_keys_in_matchup = []
        points_map = {}

        for tw in teams:
            t = tw.get("team", tw)
            tk = t.get("team_key")
            pts = float((t.get("team_points") or {}).get("total") or 0)
            team_keys_in_matchup.append(tk)
            points_map[tk] = pts

        # Only include matchups between the two specified teams
        if team_key2 not in team_keys_in_matchup:
            continue

        winner_key = matchup.get("winner_team_key")
        is_tied = bool(int(matchup.get("is_tied", 0)))

        if is_tied:
            summary["ties"] += 1
            result = "T"
        elif winner_key == team_key1:
            summary["team1_wins"] += 1
            result = "team1"
        else:
            summary["team2_wins"] += 1
            result = "team2"

        matchups.append({
            "week": matchup.get("week"),
            "year": year,
            "is_playoffs": bool(int(matchup.get("is_playoffs", 0))),
            "is_consolation": bool(int(matchup.get("is_consolation", 0))),
            "team1_points": points_map.get(team_key1),
            "team2_points": points_map.get(team_key2),
            "margin": round(
                (points_map.get(team_key1) or 0) - (points_map.get(team_key2) or 0), 2
            ),
            "winner": result,
            "is_tied": is_tied,
        })

    matchups.sort(key=lambda m: int(m["week"] or 0))

    return {
        "guid1": guid1,
        "guid2": guid2,
        "year": year,
        "team1_key": team_key1,
        "team2_key": team_key2,
        "summary": summary,
        "matchups": matchups,
    }


def _get_h2h_all_seasons(guid1: str, guid2: str) -> dict:
    """Aggregate H2H matchup data across every shared season."""
    seasons_data = get_all_seasons()
    all_matchups = []
    total_summary = {"team1_wins": 0, "team2_wins": 0, "ties": 0}

    for season in sorted(seasons_data.get("seasons", []), key=lambda s: s["year"], reverse=True):
        year = str(season["year"])
        try:
            result = get_h2h_matchups(guid1, guid2, year=year)
            all_matchups.extend(result["matchups"])
            total_summary["team1_wins"] += result["summary"]["team1_wins"]
            total_summary["team2_wins"] += result["summary"]["team2_wins"]
            total_summary["ties"] += result["summary"]["ties"]
        except Exception:
            continue  # One or both managers not in this season

    return {
        "guid1": guid1,
        "guid2": guid2,
        "year": "all",
        "summary": total_summary,
        "matchups": all_matchups,
    }