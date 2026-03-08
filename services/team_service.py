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


def _team_id_from_key(team_key: str) -> str:
    """
    Extract the short numeric team ID from a full team key.

    YFPY's query object is already scoped to a league, so passing the full
    team key (e.g. "461.l.501623.t.6") causes it to double up the league
    prefix. Pass just the numeric ID ("6") instead.

    "461.l.501623.t.6"  →  "6"
    "175.l.492325.t.10" →  "10"
    """
    if ".t." in team_key:
        return team_key.split(".t.")[-1]
    return team_key


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

def _effective_finish(rank, seed) -> int | None:
    """
    Calculate the effective finishing position for average place calculation.

    Rules:
      - rank 1, 2, 3, 4  → use rank   (playoff finishers 1st–4th)
      - rank 9, 10        → use rank   (consolation bottom finishers)
      - playoff_seed 5–8  → use seed   (non-playoff teams; rank is unreliable)
      - fallback          → use rank
    """
    try:
        rank = int(rank) if rank is not None else None
        seed = int(seed) if seed is not None else None
    except (ValueError, TypeError):
        return None

    if rank is None:
        return None

    if rank in (1, 2, 3, 4, 9, 10):
        return rank

    # Seeds 5–8: use playoff_seed as the finishing position
    if seed is not None and 5 <= seed <= 8:
        return seed

    # Fallback
    return rank


def get_team_overview(display_name: str) -> dict:
    from config import LEAGUE_CONFIG

    manager_data = _get_manager_data(display_name)
    if not manager_data:
        raise Exception(
            f"Manager '{display_name}' not found. "
            f"Call /teams/managers to see valid names."
        )

    # Only include seasons that belong to the BlackGold league chain.
    # get_all_seasons() follows the renew chain from the known BlackGold key,
    # so this set is already scoped correctly — this guard makes it explicit.
    seasons_data = get_all_seasons()
    blackgold_league_keys = {s["league_key"] for s in seasons_data.get("seasons", [])}

    num_teams = 10

    # Accumulators
    total_wins = 0
    total_losses = 0
    total_ties = 0
    total_points_for = 0.0
    total_points_against = 0.0
    total_games = 0          # wins + losses + ties across all seasons
    championships = 0
    last_place_finishes = 0
    playoff_appearances = 0
    seasons_played = 0

    points_ranks = []       # for avg_points_rank
    finish_positions = []   # for avg_finish (effective)
    best_record_season = None
    worst_record_season = None

    season_history = []

    for season in _get_seasons_for_manager(display_name):
        year = season["year"]
        league_key = season["league_key"]
        team_key = season["team_key"]

        # Skip any season not in the BlackGold league chain
        if league_key not in blackgold_league_keys:
            continue

        try:
            query = get_query(league_key)

            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)
            teams_list = _extract_teams_list(standings_dict)

            # Points rank: compare this manager's PF against all teams
            all_pf = [
                (t.get("team_key"), float(_extract_team_standings(t).get("points_for") or 0))
                for t in teams_list if isinstance(t, dict)
            ]
            sorted_pf = sorted(all_pf, key=lambda x: x[1], reverse=True)
            points_rank = next(
                (i + 1 for i, (tk, _) in enumerate(sorted_pf) if tk == team_key), None
            )

            t = _find_team_in_standings(teams_list, team_key)
            if not t:
                season_history.append({"year": year, "error": "Team not found in standings"})
                continue

            ts = _extract_team_standings(t)
            ot = _extract_outcome_totals(ts)

            rank = ts.get("rank")
            seed = ts.get("playoff_seed")
            wins = int(ot.get("wins") or 0)
            losses = int(ot.get("losses") or 0)
            ties = int(ot.get("ties") or 0)
            games = wins + losses + ties
            pf = float(ts.get("points_for") or 0)
            pa = float(ts.get("points_against") or 0)
            win_pct = float(ot.get("percentage") or 0)
            avg_ppg = round(pf / games, 2) if games else 0.0

            # Accumulate
            seasons_played += 1
            total_wins += wins
            total_losses += losses
            total_ties += ties
            total_games += games
            total_points_for += pf
            total_points_against += pa

            if rank == 1:
                championships += 1
            if rank == num_teams:
                last_place_finishes += 1
            try:
                if seed is not None and int(seed) <= 4:
                    playoff_appearances += 1
            except (ValueError, TypeError):
                pass

            # Best and worst record seasons (by win_pct)
            if best_record_season is None or win_pct > best_record_season["win_pct"]:
                best_record_season = {
                    "year": year,
                    "wins": wins,
                    "losses": losses,
                    "ties": ties,
                    "win_pct": win_pct,
                    "record_str": f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}",
                }
            if worst_record_season is None or win_pct < worst_record_season["win_pct"]:
                worst_record_season = {
                    "year": year,
                    "wins": wins,
                    "losses": losses,
                    "ties": ties,
                    "win_pct": win_pct,
                    "record_str": f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}",
                }

            if points_rank is not None:
                points_ranks.append(points_rank)

            effective = _effective_finish(rank, seed)
            if effective is not None:
                finish_positions.append(effective)

            season_history.append({
                "year": year,
                "team_name": t.get("name"),
                "rank": rank,
                "playoff_seed": seed,
                "effective_finish": effective,
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "games_played": games,
                "win_pct": round(win_pct, 4),
                "points_for": round(pf, 2),
                "points_against": round(pa, 2),
                "avg_points_per_game": avg_ppg,
                "points_rank": points_rank,
                "logo_url": _extract_logo_url(t),
            })

        except Exception as e:
            season_history.append({"year": year, "error": str(e)})

    # --- Derived career stats ---
    avg_points_per_season = round(total_points_for / seasons_played, 2) if seasons_played else 0.0
    avg_points_per_game = round(total_points_for / total_games, 2) if total_games else 0.0
    avg_points_against_per_season = round(total_points_against / seasons_played, 2) if seasons_played else 0.0
    avg_points_against_per_game = round(total_points_against / total_games, 2) if total_games else 0.0
    avg_points_rank = round(sum(points_ranks) / len(points_ranks), 2) if points_ranks else None
    avg_finish = round(sum(finish_positions) / len(finish_positions), 2) if finish_positions else None
    record_str = f"{total_wins}-{total_losses}-{total_ties}" if total_ties else f"{total_wins}-{total_losses}"

    return {
        "display_name": manager_data["display_name"],
        "manager_id": manager_data["manager_id"],
        "league": LEAGUE_CONFIG["name"],

        # Core career stats
        "seasons_played": seasons_played,
        "championships": championships,
        "last_place_finishes": last_place_finishes,
        "playoff_appearances": playoff_appearances,

        # Record
        "total_wins": total_wins,
        "total_losses": total_losses,
        "total_ties": total_ties,
        "total_games": total_games,
        "total_record": record_str,
        "best_record_season": best_record_season,
        "worst_record_season": worst_record_season,

        # Points
        "total_points_for": round(total_points_for, 2),
        "total_points_against": round(total_points_against, 2),
        "avg_points_per_season": avg_points_per_season,
        "avg_points_per_game": avg_points_per_game,
        "avg_points_against_per_season": avg_points_against_per_season,
        "avg_points_against_per_game": avg_points_against_per_game,

        # Rankings
        "avg_points_rank": avg_points_rank,
        "avg_finish": avg_finish,

        # Full season-by-season breakdown
        "season_history": season_history,
    }


# ---------------------------------------------------------------------------
# /teams/{name}/results  — Combined record + points (replaces /record & /points)
# ---------------------------------------------------------------------------

def get_team_results(display_name: str) -> dict:
    """
    Single endpoint combining season-by-season record and points data.
    One standings fetch per season serves both sections — no duplicate API calls.
    """
    from config import LEAGUE_CONFIG

    manager_data = _get_manager_data(display_name)
    if not manager_data:
        raise Exception(f"Manager '{display_name}' not found.")

    seasons_data = get_all_seasons()
    blackgold_league_keys = {s["league_key"] for s in seasons_data.get("seasons", [])}

    rows = []

    for season in _get_seasons_for_manager(display_name):
        year = season["year"]
        league_key = season["league_key"]
        team_key = season["team_key"]

        if league_key not in blackgold_league_keys:
            continue

        try:
            query = get_query(league_key)
            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)
            teams_list = _extract_teams_list(standings_dict)

            # Points rank across all teams this season
            all_pf = [
                (t.get("team_key"), float(_extract_team_standings(t).get("points_for") or 0))
                for t in teams_list if isinstance(t, dict)
            ]
            sorted_pf = sorted(all_pf, key=lambda x: x[1], reverse=True)
            points_rank = next(
                (i + 1 for i, (tk, _) in enumerate(sorted_pf) if tk == team_key), None
            )

            t = _find_team_in_standings(teams_list, team_key)
            if not t:
                rows.append({"year": year, "error": "Team not found in standings"})
                continue

            ts = _extract_team_standings(t)
            ot = _extract_outcome_totals(ts)

            rank = ts.get("rank")
            seed = ts.get("playoff_seed")
            wins = int(ot.get("wins") or 0)
            losses = int(ot.get("losses") or 0)
            ties = int(ot.get("ties") or 0)
            games = wins + losses + ties
            pf = float(ts.get("points_for") or 0)
            pa = float(ts.get("points_against") or 0)
            win_pct = float(ot.get("percentage") or 0)
            effective = _effective_finish(rank, seed)
            record_str = f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}"
            avg_ppg = round(pf / games, 2) if games else 0.0
            avg_pa_ppg = round(pa / games, 2) if games else 0.0

            rows.append({
                "year": year,
                "team_name": t.get("name"),
                "record": record_str,
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "games_played": games,
                "win_pct": round(win_pct, 4),
                "effective_finish": effective,
                "points_for": round(pf, 2),
                "points_against": round(pa, 2),
                "avg_points_per_game": avg_ppg,
                "avg_points_against_per_game": avg_pa_ppg,
                "points_rank": points_rank,
                "logo_url": _extract_logo_url(t),
            })

        except Exception as e:
            rows.append({"year": year, "error": str(e)})

    # Newest first
    rows.sort(key=lambda r: r.get("year", 0), reverse=True)

    def _summarize(subset):
        valid = [r for r in subset if "error" not in r]
        if not valid:
            return {}
        total_wins = sum(r["wins"] for r in valid)
        total_losses = sum(r["losses"] for r in valid)
        total_ties = sum(r["ties"] for r in valid)
        total_games = sum(r["games_played"] for r in valid)
        total_pf = sum(r["points_for"] for r in valid)
        total_pa = sum(r["points_against"] for r in valid)
        finish_vals = [r["effective_finish"] for r in valid if r.get("effective_finish") is not None]
        rank_vals = [r["points_rank"] for r in valid if r.get("points_rank") is not None]
        record_str = (
            f"{total_wins}-{total_losses}-{total_ties}"
            if total_ties else f"{total_wins}-{total_losses}"
        )
        return {
            "seasons": len(valid),
            "record": record_str,
            "win_pct": round(total_wins / total_games, 4) if total_games else None,
            "avg_finish": round(sum(finish_vals) / len(finish_vals), 2) if finish_vals else None,
            "avg_points_per_game": round(total_pf / total_games, 2) if total_games else None,
            "avg_points_against_per_game": round(total_pa / total_games, 2) if total_games else None,
            "avg_points_rank": round(sum(rank_vals) / len(rank_vals), 2) if rank_vals else None,
        }

    valid_rows = [r for r in rows if "error" not in r]
    last_5 = valid_rows[:5]  # newest-first, so first 5 = last 5 seasons

    return {
        "display_name": manager_data["display_name"],
        "league": LEAGUE_CONFIG["name"],
        "all_time": _summarize(valid_rows),
        "last_5_seasons": _summarize(last_5),
        "seasons": rows,
    }


# ---------------------------------------------------------------------------
# /teams/{name}/matchups  — All-time H2H table vs every opponent
# ---------------------------------------------------------------------------

def get_team_matchups(display_name: str) -> dict:
    """
    Returns a per-opponent H2H table across ALL BlackGold seasons.

    For each opponent:
      - overall W-L-T record
      - average points for per game (all-time)
      - average points against per game (all-time)
      - point differential (avg_pf - avg_pa)
      - last-5 results (chronological, most recent last)
    """
    from config import LEAGUE_CONFIG

    manager_data = _get_manager_data(display_name)
    if not manager_data:
        raise Exception(f"Manager '{display_name}' not found.")

    seasons_data = get_all_seasons()
    blackgold_league_keys = {s["league_key"] for s in seasons_data.get("seasons", [])}

    # opponent_name -> accumulator dict
    opponents: dict[str, dict] = {}

    for season in _get_seasons_for_manager(display_name):
        year = season["year"]
        league_key = season["league_key"]
        team_key = season["team_key"]

        if league_key not in blackgold_league_keys:
            continue

        try:
            query = get_query(league_key)
            team_map = _get_all_team_map(query)

            raw = query.get_team_matchups(_team_id_from_key(team_key))
            matchups_dict = _convert_to_dict(raw)

            if isinstance(matchups_dict, dict):
                matchups_raw = matchups_dict.get("matchups", [])
            elif isinstance(matchups_dict, list):
                matchups_raw = matchups_dict
            else:
                matchups_raw = []

            for m in matchups_raw:
                matchup = m.get("matchup", m) if isinstance(m, dict) else {}
                teams = matchup.get("teams", [])
                if isinstance(teams, dict):
                    teams = list(teams.values())

                my_pts = None
                opp_pts = None
                opp_team_key = None

                for tw in teams:
                    t = tw.get("team", tw) if isinstance(tw, dict) else {}
                    tk = t.get("team_key")
                    pts = _extract_points(t)
                    if tk == team_key:
                        my_pts = pts
                    else:
                        opp_pts = pts
                        opp_team_key = tk

                if not opp_team_key:
                    continue

                winner_key = matchup.get("winner_team_key")
                is_tied = bool(int(matchup.get("is_tied", 0) or 0))
                opp_name = _resolve_opponent_name(opp_team_key, team_map)

                if is_tied:
                    result = "T"
                elif winner_key == team_key:
                    result = "W"
                else:
                    result = "L"

                if opp_name not in opponents:
                    opponents[opp_name] = {
                        "wins": 0, "losses": 0, "ties": 0,
                        "total_pf": 0.0, "total_pa": 0.0,
                        "games": 0,
                        # Store (year, week, result) tuples for last-5 logic
                        "_history": [],
                    }

                acc = opponents[opp_name]
                if result == "W":
                    acc["wins"] += 1
                elif result == "L":
                    acc["losses"] += 1
                else:
                    acc["ties"] += 1

                acc["games"] += 1
                acc["total_pf"] += my_pts or 0
                acc["total_pa"] += opp_pts or 0
                acc["_history"].append({
                    "year": year,
                    "week": int(matchup.get("week") or 0),
                    "result": result,
                    "my_points": my_pts,
                    "opponent_points": opp_pts,
                })

        except Exception:
            continue  # skip broken seasons silently

    # Build final per-opponent rows
    rows = []
    for opp_name, acc in opponents.items():
        g = acc["games"]
        wins = acc["wins"]
        losses = acc["losses"]
        ties = acc["ties"]
        avg_pf = round(acc["total_pf"] / g, 2) if g else 0.0
        avg_pa = round(acc["total_pa"] / g, 2) if g else 0.0
        record_str = f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}"

        # Sort history chronologically and take last 5
        history_sorted = sorted(acc["_history"], key=lambda x: (x["year"], x["week"]))
        last_5 = [h["result"] for h in history_sorted[-5:]]

        rows.append({
            "opponent_name": opp_name,
            "record": record_str,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "games_played": g,
            "avg_points_for": avg_pf,
            "avg_points_against": avg_pa,
            "point_differential": round(avg_pf - avg_pa, 2),
            "last_5": last_5,  # e.g. ["W","L","W","W","L"]
        })

    # Sort by games played desc, then opponent name alpha
    rows.sort(key=lambda r: (-r["games_played"], r["opponent_name"]))

    return {
        "display_name": manager_data["display_name"],
        "league": LEAGUE_CONFIG["name"],
        "opponents": rows,
        "total_opponents": len(rows),
    }


# ---------------------------------------------------------------------------
# /teams/{name}/transactions  — Career transaction summary (replaces /trades)
# ---------------------------------------------------------------------------

def get_team_transactions(display_name: str) -> dict:
    """
    Career transaction summary across all BlackGold seasons.

    All-time and last-5 summaries for:
      - total trades, avg trades per season
      - total moves (adds/drops), avg moves per season
      - total FAAB spent, avg FAAB per season (FAAB seasons only)

    Per-season table: year, team_name, trades, moves, faab_spent, faab_available.
    """
    import datetime
    from config import LEAGUE_CONFIG

    manager_data = _get_manager_data(display_name)
    if not manager_data:
        raise Exception(f"Manager '{display_name}' not found.")

    seasons_data = get_all_seasons()
    blackgold_league_keys = {s["league_key"] for s in seasons_data.get("seasons", [])}

    rows = []

    for season in _get_seasons_for_manager(display_name):
        year = season["year"]
        league_key = season["league_key"]
        team_key = season["team_key"]

        if league_key not in blackgold_league_keys:
            continue

        try:
            query = get_query(league_key)

            # FAAB balance lives in team data
            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)
            teams_list = _extract_teams_list(standings_dict)
            t = _find_team_in_standings(teams_list, team_key)

            # number_of_moves and number_of_trades come from the team object
            num_moves = int(t.get("number_of_moves") or 0) if t else 0
            num_trades = int(t.get("number_of_trades") or 0) if t else 0

            # FAAB: auction_budget_total and auction_budget_spent on team object
            faab_total = t.get("auction_budget_total") if t else None
            faab_spent = t.get("auction_budget_spent") if t else None
            uses_faab = faab_total is not None and int(faab_total) > 0

            rows.append({
                "year": year,
                "team_name": t.get("name") if t else None,
                "trades": num_trades,
                "moves": num_moves,
                "uses_faab": uses_faab,
                "faab_budget": int(faab_total) if uses_faab else None,
                "faab_spent": int(faab_spent) if uses_faab and faab_spent is not None else None,
                "logo_url": _extract_logo_url(t) if t else None,
            })

        except Exception as e:
            rows.append({"year": year, "error": str(e)})

    # Newest first
    rows.sort(key=lambda r: r.get("year", 0), reverse=True)

    def _summarize_tx(subset):
        valid = [r for r in subset if "error" not in r]
        if not valid:
            return {}
        n = len(valid)
        total_trades = sum(r["trades"] for r in valid)
        total_moves = sum(r["moves"] for r in valid)
        faab_rows = [r for r in valid if r.get("uses_faab") and r.get("faab_spent") is not None]
        total_faab = sum(r["faab_spent"] for r in faab_rows)
        return {
            "seasons": n,
            "total_trades": total_trades,
            "avg_trades_per_season": round(total_trades / n, 2),
            "total_moves": total_moves,
            "avg_moves_per_season": round(total_moves / n, 2),
            "faab_seasons": len(faab_rows),
            "total_faab_spent": total_faab if faab_rows else None,
            "avg_faab_per_season": round(total_faab / len(faab_rows), 2) if faab_rows else None,
        }

    valid_rows = [r for r in rows if "error" not in r]
    last_5 = valid_rows[:5]

    return {
        "display_name": manager_data["display_name"],
        "league": LEAGUE_CONFIG["name"],
        "all_time": _summarize_tx(valid_rows),
        "last_5_seasons": _summarize_tx(last_5),
        "seasons": rows,
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
    raw_matchups = query.get_team_matchups(_team_id_from_key(team_key1))
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