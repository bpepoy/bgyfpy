from services.yahoo_service import get_query
from services.fantasy.league_service import (
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
# Shared era / stats helpers
# ---------------------------------------------------------------------------

def _summarize_rows(rows: list) -> dict:
    """
    Aggregate season rows into a stats summary block.
    Rows must already be pre-filtered (valid, no error keys).
    """
    if not rows:
        return {}
    total_wins   = sum(r["wins"]        for r in rows)
    total_losses = sum(r["losses"]      for r in rows)
    total_ties   = sum(r["ties"]        for r in rows)
    total_games  = sum(r["games_played"]for r in rows)
    total_pf     = sum(r["points_for"]  for r in rows)
    total_pa     = sum(r["points_against"] for r in rows)
    finish_vals  = [r["effective_finish"] for r in rows if r.get("effective_finish") is not None]
    rank_vals    = [r["points_rank"]      for r in rows if r.get("points_rank")      is not None]
    record_str   = (
        f"{total_wins}-{total_losses}-{total_ties}"
        if total_ties else f"{total_wins}-{total_losses}"
    )
    return {
        "seasons":                    len(rows),
        "record":                     record_str,
        "win_pct":                    round(total_wins / total_games, 4) if total_games else None,
        "avg_finish":                 round(sum(finish_vals) / len(finish_vals), 2) if finish_vals else None,
        "avg_points_per_game":        round(total_pf / total_games, 2)  if total_games else None,
        "avg_points_against_per_game":round(total_pa / total_games, 2)  if total_games else None,
        "avg_points_rank":            round(sum(rank_vals) / len(rank_vals), 2) if rank_vals else None,
    }


def _build_era_summaries(valid_rows: list) -> dict:
    """
    Build a summary block for every defined era, keyed by era slug.
    Skips eras where the manager played 0 seasons.
    valid_rows must already exclude error rows; each row must have a "year" key.
    """
    from config import get_league_eras
    eras = get_league_eras()
    result = {}
    for slug, era in eras.items():
        if slug == "overall":
            continue  # overall is already surfaced as all_time
        start = era["start_year"]
        end   = era["end_year"]   # None = present
        subset = [
            r for r in valid_rows
            if r["year"] >= start and (end is None or r["year"] <= end)
        ]
        if not subset:
            continue  # manager didn't play in this era — omit key entirely
        summary = _summarize_rows(subset)
        summary["era_name"]    = era["display_name"]
        summary["description"] = era["description"]
        result[slug] = summary
    return result



def _split_record_by_type(matchup_history: list) -> dict:
    """
    Given a list of matchup dicts (each with is_playoffs, is_consolation,
    result W/L/T, my_points, opponent_points), return a dict with:
      regular_season: {wins, losses, ties, games}
      playoffs:       {wins, losses, ties, games}
    """
    rs = {"wins": 0, "losses": 0, "ties": 0, "games": 0}
    pl = {"wins": 0, "losses": 0, "ties": 0, "games": 0}

    for m in matchup_history:
        bucket = pl if m.get("is_playoffs") else rs
        r = m.get("result", "")
        bucket["games"] += 1
        if r == "W":   bucket["wins"]   += 1
        elif r == "L": bucket["losses"] += 1
        else:          bucket["ties"]   += 1

    def _fmt(b):
        rec = f"{b['wins']}-{b['losses']}-{b['ties']}" if b["ties"] else f"{b['wins']}-{b['losses']}"
        return {
            "record": rec,
            "wins": b["wins"], "losses": b["losses"], "ties": b["ties"],
            "games": b["games"],
            "win_pct": round(b["wins"] / b["games"], 4) if b["games"] else None,
        }

    return {"regular_season": _fmt(rs), "playoffs": _fmt(pl)}


def _fetch_matchup_history(display_name: str, blackgold_league_keys: set) -> list:
    """
    Fetch ALL matchups across all seasons for a manager.
    Returns a flat list of matchup dicts:
      {year, week, is_playoffs, is_consolation, result, my_points, opp_points,
       opp_team_key, opp_name}

    Used by overview and matchups to avoid duplicate API calls when both
    reg/playoff split AND H2H data are needed.
    """
    all_matchups = []

    for season in _get_seasons_for_manager(display_name):
        year      = season["year"]
        league_key = season["league_key"]
        team_key   = season["team_key"]

        if league_key not in blackgold_league_keys:
            continue

        try:
            query    = get_query(league_key)
            team_map = _get_all_team_map(query)
            raw      = query.get_team_matchups(_team_id_from_key(team_key))
            md       = _convert_to_dict(raw)

            matchups_raw = md.get("matchups", []) if isinstance(md, dict) else (md if isinstance(md, list) else [])

            for m in matchups_raw:
                matchup     = m.get("matchup", m) if isinstance(m, dict) else {}
                teams       = matchup.get("teams", [])
                if isinstance(teams, dict):
                    teams = list(teams.values())

                my_pts = opp_pts = opp_team_key = None

                for tw in teams:
                    t  = tw.get("team", tw) if isinstance(tw, dict) else {}
                    tk = t.get("team_key")
                    pts = t.get("points")
                    pts = float(pts) if pts is not None else _extract_points(t)
                    if tk == team_key:
                        my_pts = pts
                    else:
                        opp_pts      = pts
                        opp_team_key = tk

                if not opp_team_key:
                    continue

                winner_key = matchup.get("winner_team_key")
                is_tied    = bool(int(matchup.get("is_tied",       0) or 0))
                is_playoff = bool(int(matchup.get("is_playoffs",   0) or 0))
                is_consol  = bool(int(matchup.get("is_consolation",0) or 0))
                result     = "T" if is_tied else ("W" if winner_key == team_key else "L")

                all_matchups.append({
                    "year":            year,
                    "week":            int(matchup.get("week") or 0),
                    "is_playoffs":     is_playoff,
                    "is_consolation":  is_consol,
                    "result":          result,
                    "my_points":       my_pts,
                    "opp_points":      opp_pts,
                    "opp_team_key":    opp_team_key,
                    "opp_name":        _resolve_opponent_name(opp_team_key, team_map),
                })

        except Exception:
            continue

    return all_matchups

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
    from config import LEAGUE_CONFIG, get_player_history_season

    manager_data = _get_manager_data(display_name)
    if not manager_data:
        raise Exception(
            f"Manager '{display_name}' not found. "
            f"Call /teams/managers to see valid names."
        )

    seasons_data = get_all_seasons()
    blackgold_league_keys = {s["league_key"] for s in seasons_data.get("seasons", [])}

    # Fetch all matchups once — used for reg/playoff split AND best/worst week
    all_matchups = _fetch_matchup_history(display_name, blackgold_league_keys)
    record_split = _split_record_by_type(all_matchups)

    # Best and worst single-week scores (from matchup data, free)
    scored_weeks = [m for m in all_matchups if m["my_points"] is not None and m["my_points"] > 0]
    best_week  = max(scored_weeks, key=lambda m: m["my_points"], default=None)
    worst_week = min(scored_weeks, key=lambda m: m["my_points"], default=None)

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
    avg_points_per_game   = round(total_points_for / total_games,    2) if total_games    else 0.0
    avg_points_against_per_season = round(total_points_against / seasons_played, 2) if seasons_played else 0.0
    avg_points_against_per_game   = round(total_points_against / total_games,    2) if total_games    else 0.0
    avg_points_rank = round(sum(points_ranks)     / len(points_ranks),     2) if points_ranks     else None
    avg_finish      = round(sum(finish_positions) / len(finish_positions), 2) if finish_positions  else None
    record_str = f"{total_wins}-{total_losses}-{total_ties}" if total_ties else f"{total_wins}-{total_losses}"

    # Best / worst season by avg PPG (derived from season_history)
    valid_history = [h for h in season_history if "error" not in h and h.get("avg_points_per_game")]
    best_ppg_season  = max(valid_history, key=lambda h: h["avg_points_per_game"], default=None)
    worst_ppg_season = min(valid_history, key=lambda h: h["avg_points_per_game"], default=None)

    def _ppg_season_ref(h):
        if not h:
            return None
        return {"year": h["year"], "team_name": h.get("team_name"), "avg_points_per_game": h["avg_points_per_game"]}

    # Reg season vs playoff record (from pre-fetched matchup history)
    era_summaries = _build_era_summaries([h for h in season_history if "error" not in h])

    # Per-season seeded player data
    manager_id = manager_data["manager_id"]

    # Aggregate career top players from seeded data
    career_top_by_pos = _career_top_players_from_seed(manager_id, valid_history)
    career_frequent   = _career_frequent_players_from_seed(manager_id, valid_history)

    return {
        "display_name": manager_data["display_name"],
        "manager_id":   manager_id,
        "league":       LEAGUE_CONFIG["name"],

        # Core career stats
        "seasons_played":       seasons_played,
        "championships":        championships,
        "last_place_finishes":  last_place_finishes,
        "playoff_appearances":  playoff_appearances,

        # Record split
        "regular_season_record": record_split["regular_season"],
        "playoff_record":        record_split["playoffs"],
        "total_record":          record_str,
        "total_wins":   total_wins,
        "total_losses": total_losses,
        "total_ties":   total_ties,
        "total_games":  total_games,
        "best_record_season":  best_record_season,
        "worst_record_season": worst_record_season,

        # Points
        "total_points_for":               round(total_points_for,    2),
        "total_points_against":           round(total_points_against, 2),
        "avg_points_per_season":          avg_points_per_season,
        "avg_points_per_game":            avg_points_per_game,
        "avg_points_against_per_season":  avg_points_against_per_season,
        "avg_points_against_per_game":    avg_points_against_per_game,
        "best_ppg_season":                _ppg_season_ref(best_ppg_season),
        "worst_ppg_season":               _ppg_season_ref(worst_ppg_season),

        # Single-week extremes (free from matchup data)
        "best_week":  {"year": best_week["year"],  "week": best_week["week"],  "points": best_week["my_points"]}  if best_week  else None,
        "worst_week": {"year": worst_week["year"], "week": worst_week["week"], "points": worst_week["my_points"]} if worst_week else None,

        # Rankings
        "avg_points_rank": avg_points_rank,
        "avg_finish":      avg_finish,

        # Career top players (from seeded config data)
        "career_top_players": career_top_by_pos,
        "frequent_players":   career_frequent,

        # Eras + full season-by-season breakdown
        "eras":           era_summaries,
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
    from config import LEAGUE_CONFIG, get_player_history_season

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

            # Fetch matchups for this season to get reg/playoff split
            season_matchups = []
            try:
                team_map = _get_all_team_map(query)
                raw_m = query.get_team_matchups(_team_id_from_key(team_key))
                md    = _convert_to_dict(raw_m)
                matchups_raw = md.get("matchups", []) if isinstance(md, dict) else (md if isinstance(md, list) else [])
                for m in matchups_raw:
                    matchup = m.get("matchup", m) if isinstance(m, dict) else {}
                    teams_m = matchup.get("teams", [])
                    if isinstance(teams_m, dict): teams_m = list(teams_m.values())
                    my_pts_m = opp_pts_m = opp_tk = None
                    for tw in teams_m:
                        tm = tw.get("team", tw) if isinstance(tw, dict) else {}
                        tk2 = tm.get("team_key")
                        pts = tm.get("points")
                        pts = float(pts) if pts is not None else _extract_points(tm)
                        if tk2 == team_key: my_pts_m = pts
                        else: opp_pts_m = pts; opp_tk = tk2
                    if not opp_tk: continue
                    winner_key = matchup.get("winner_team_key")
                    is_tied    = bool(int(matchup.get("is_tied", 0) or 0))
                    is_playoff = bool(int(matchup.get("is_playoffs", 0) or 0))
                    result_m   = "T" if is_tied else ("W" if winner_key == team_key else "L")
                    season_matchups.append({"year": year, "week": int(matchup.get("week") or 0),
                                            "is_playoffs": is_playoff, "result": result_m,
                                            "my_points": my_pts_m, "opp_points": opp_pts_m})
            except Exception:
                pass

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
                "_matchups": season_matchups,  # stripped before final return
            })

        except Exception as e:
            rows.append({"year": year, "error": str(e)})

    # Newest first
    rows.sort(key=lambda r: r.get("year", 0), reverse=True)

    valid_rows = [r for r in rows if "error" not in r]
    last_5 = valid_rows[:5]

    # Reg season vs playoff split from matchup history (already fetched above per season)
    # We stored per-season matchup buckets on each row during the loop
    all_matchups_flat = []
    for r in valid_rows:
        all_matchups_flat.extend(r.pop("_matchups", []))

    record_split = _split_record_by_type(all_matchups_flat)

    # Enrich each season row with seeded player data
    manager_id = manager_data["manager_id"]
    for r in rows:
        if "error" in r:
            continue
        yr = r["year"]
        seed = get_player_history_season(manager_id, yr)
        r["top_starters"]        = seed.get("top_starters")
        r["starter_points_total"]= seed.get("starter_points_total")
        # Reg/playoff split per season
        season_matchups = [m for m in all_matchups_flat if m["year"] == yr]
        split = _split_record_by_type(season_matchups)
        r["regular_season_record"] = split["regular_season"]
        r["playoff_record"]        = split["playoffs"]

    return {
        "display_name": manager_data["display_name"],
        "league": LEAGUE_CONFIG["name"],
        "regular_season_record": record_split["regular_season"],
        "playoff_record":        record_split["playoffs"],
        "all_time":              _summarize_rows(valid_rows),
        "last_5_seasons":        _summarize_rows(last_5),
        "eras":                  _build_era_summaries(valid_rows),
        "seasons":               rows,
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
                # YFPY returns matchup objects directly in the list (no "matchup" wrapper)
                # but defensively handle both shapes
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

                    # YFPY flattens points to t["points"] in the matchup response.
                    # Fall back to team_points.total for older seasons.
                    pts = t.get("points")
                    if pts is None:
                        pts = _extract_points(t)
                    else:
                        pts = float(pts)

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
                        "rs_wins": 0, "rs_losses": 0, "rs_ties": 0,
                        "pl_wins": 0, "pl_losses": 0, "pl_ties": 0,
                        "_history": [],
                    }

                acc      = opponents[opp_name]
                week_num = int(matchup.get("week") or 0)
                is_pl    = bool(int(matchup.get("is_playoffs",   0) or 0))
                is_con   = bool(int(matchup.get("is_consolation",0) or 0))

                if result == "W":   acc["wins"]   += 1
                elif result == "L": acc["losses"] += 1
                else:               acc["ties"]   += 1

                if is_pl:
                    if result == "W":   acc["pl_wins"]   += 1
                    elif result == "L": acc["pl_losses"] += 1
                    else:               acc["pl_ties"]   += 1
                else:
                    if result == "W":   acc["rs_wins"]   += 1
                    elif result == "L": acc["rs_losses"] += 1
                    else:               acc["rs_ties"]   += 1

                acc["games"]    += 1
                acc["total_pf"] += my_pts or 0
                acc["total_pa"] += opp_pts or 0
                acc["_history"].append({
                    "year":             year,
                    "week":             week_num,
                    "is_playoffs":      is_pl,
                    "is_consolation":   is_con,
                    "result":           result,
                    "my_points":        my_pts,
                    "opponent_points":  opp_pts,
                    "margin":           round((my_pts or 0) - (opp_pts or 0), 2),
                })

        except Exception as e:
            # Surface the error in the response for easier debugging
            opponents[f"__error_{year}__"] = {
                "wins": 0, "losses": 0, "ties": 0,
                "total_pf": 0.0, "total_pa": 0.0,
                "games": 0, "_history": [], "_error": str(e),
            }
            continue

    # Build final per-opponent rows
    rows = []
    season_errors = {}
    from config import get_league_eras

    for opp_name, acc in opponents.items():
        if opp_name.startswith("__error_"):
            season_errors[opp_name] = acc.get("_error")
            continue

        g      = acc["games"]
        wins   = acc["wins"];   losses = acc["losses"];   ties = acc["ties"]
        avg_pf = round(acc["total_pf"] / g, 2) if g else 0.0
        avg_pa = round(acc["total_pa"] / g, 2) if g else 0.0

        def _rec(w, l, t, gm):
            rec = f"{w}-{l}-{t}" if t else f"{w}-{l}"
            return {"record": rec, "wins": w, "losses": l, "ties": t, "games": gm,
                    "win_pct": round(w / gm, 4) if gm else None}

        record_str = f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}"

        # Sort history chronologically
        history_sorted = sorted(acc["_history"], key=lambda x: (x["year"], x["week"]))
        last_5_results = [h["result"] for h in history_sorted[-5:]]
        last_5_detail  = [{"year": h["year"], "week": h["week"], "result": h["result"],
                           "my_points": h["my_points"], "opponent_points": h["opponent_points"]}
                          for h in history_sorted[-5:]]

        # Margins
        margins = [h["margin"] for h in history_sorted if h["my_points"] is not None]
        best_margin_entry  = max(history_sorted, key=lambda h: h["margin"],  default=None) if margins else None
        worst_margin_entry = min(history_sorted, key=lambda h: h["margin"],  default=None) if margins else None
        closest_win_entry  = min([h for h in history_sorted if h["result"] == "W"],
                                  key=lambda h: h["margin"], default=None)
        closest_loss_entry = max([h for h in history_sorted if h["result"] == "L"],
                                  key=lambda h: h["margin"], default=None)

        def _margin_ref(h):
            if not h: return None
            return {"year": h["year"], "week": h["week"], "margin": h["margin"],
                    "my_points": h["my_points"], "opponent_points": h["opponent_points"]}

        # Era breakdowns
        eras = get_league_eras()
        era_records = {}
        for slug, era in eras.items():
            if slug == "overall": continue
            start = era["start_year"]; end = era["end_year"]
            era_h = [h for h in history_sorted
                     if h["year"] >= start and (end is None or h["year"] <= end)]
            if not era_h: continue
            rs_h = [h for h in era_h if not h["is_playoffs"]]
            pl_h = [h for h in era_h if h["is_playoffs"]]
            def _count(lst):
                w = sum(1 for h in lst if h["result"]=="W")
                l = sum(1 for h in lst if h["result"]=="L")
                t = sum(1 for h in lst if h["result"]=="T")
                return _rec(w, l, t, len(lst))
            era_records[slug] = {
                "era_name":       era["display_name"],
                "overall":        _count(era_h),
                "regular_season": _count(rs_h),
                "playoffs":       _count(pl_h),
            }

        rows.append({
            "opponent_name":     opp_name,
            "record":            record_str,
            "wins":              wins,
            "losses":            losses,
            "ties":              ties,
            "games_played":      g,
            "avg_points_for":    avg_pf,
            "avg_points_against":avg_pa,
            "point_differential":round(avg_pf - avg_pa, 2),
            "regular_season":    _rec(acc["rs_wins"], acc["rs_losses"], acc["rs_ties"],
                                      acc["rs_wins"]+acc["rs_losses"]+acc["rs_ties"]),
            "playoffs":          _rec(acc["pl_wins"], acc["pl_losses"], acc["pl_ties"],
                                      acc["pl_wins"]+acc["pl_losses"]+acc["pl_ties"]),
            "last_5":            last_5_results,
            "last_5_detail":     last_5_detail,
            "biggest_win":       _margin_ref(best_margin_entry),
            "biggest_loss":      _margin_ref(worst_margin_entry),
            "closest_win":       _margin_ref(closest_win_entry),
            "closest_loss":      _margin_ref(closest_loss_entry),
            "eras":              era_records,
        })

    # Sort by games played desc, then opponent name alpha
    rows.sort(key=lambda r: (-r["games_played"], r["opponent_name"]))

    return {
        "display_name":   manager_data["display_name"],
        "league":         LEAGUE_CONFIG["name"],
        "opponents":      rows,
        "total_opponents":len(rows),
        "season_errors":  season_errors if season_errors else None,
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

            # Check league settings for FAAB flag
            settings_raw = query.get_league_settings()
            settings_dict = _convert_to_dict(settings_raw)
            uses_faab = bool(int(settings_dict.get("uses_faab") or 0))

            # Team object has faab_balance (remaining), not spent
            standings_raw = query.get_league_standings()
            standings_dict = _convert_to_dict(standings_raw)
            teams_list = _extract_teams_list(standings_dict)
            t = _find_team_in_standings(teams_list, team_key)

            num_moves = int(t.get("number_of_moves") or 0) if t else 0
            num_trades = int(t.get("number_of_trades") or 0) if t else 0

            faab_balance = None
            faab_spent = None
            faab_budget = None
            if uses_faab and t:
                # Prefer auction_budget fields if present on team object
                raw_total = t.get("auction_budget_total")
                raw_spent = t.get("auction_budget_spent")
                raw_balance = t.get("faab_balance")

                if raw_total is not None and int(raw_total) > 0:
                    faab_budget = int(raw_total)
                    faab_spent = int(raw_spent) if raw_spent is not None else None
                    faab_balance = (faab_budget - faab_spent) if faab_spent is not None else (int(raw_balance) if raw_balance is not None else None)
                elif raw_balance is not None:
                    # Older seasons: only balance available, use settings budget
                    faab_balance = int(raw_balance)
                    faab_budget = int(settings_dict.get("faab_budget") or 0) or None
                    faab_spent = (faab_budget - faab_balance) if faab_budget else None

            rows.append({
                "year": year,
                "team_name": t.get("name") if t else None,
                "trades": num_trades,
                "moves": num_moves,
                "uses_faab": uses_faab,
                "faab_budget": faab_budget,
                "faab_balance": faab_balance,
                "faab_spent": faab_spent,
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
    from services.fantasy.league_service import get_league_key_for_season
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
    from services.fantasy.league_service import get_league_key_for_season
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

# ---------------------------------------------------------------------------
# Seed helpers — read from PLAYER_HISTORY_MANUAL in config
# ---------------------------------------------------------------------------

def _career_top_players_from_seed(manager_id: str, valid_history: list) -> dict:
    """
    Aggregate career-best starter per position across all seeded seasons.
    Returns {"QB": {name, team_name, year, total_points, weeks_started}, ...}
    """
    from config import get_player_history_season
    POSITIONS = ["QB", "WR", "RB", "TE"]
    best: dict = {}

    for row in valid_history:
        yr   = row["year"]
        seed = get_player_history_season(manager_id, yr)
        top  = seed.get("top_starters") or {}
        for pos in POSITIONS:
            p = top.get(pos)
            if not p:
                continue
            pts = p.get("total_points", 0)
            if pos not in best or pts > best[pos]["total_points"]:
                best[pos] = {**p, "year": yr, "position": pos}

    return best


def _career_frequent_players_from_seed(manager_id: str, valid_history: list) -> list:
    """
    Aggregate most-frequent players across all seeded seasons.
    Returns top 10 by total weeks_on_roster.
    """
    from config import get_player_history_season
    player_totals: dict = {}

    for row in valid_history:
        yr   = row["year"]
        seed = get_player_history_season(manager_id, yr)
        freq = seed.get("frequent_players") or []
        for p in freq:
            name = p.get("name")
            if not name:
                continue
            if name not in player_totals:
                player_totals[name] = {
                    "name":            name,
                    "position":        p.get("position"),
                    "weeks_on_roster": 0,
                    "weeks_as_starter":0,
                    "total_points":    0.0,
                    "seasons":         [],
                }
            player_totals[name]["weeks_on_roster"]  += p.get("weeks_on_roster",  0)
            player_totals[name]["weeks_as_starter"] += p.get("weeks_as_starter", 0)
            player_totals[name]["total_points"]     += p.get("total_points",     0.0)
            player_totals[name]["seasons"].append(yr)

    ranked = sorted(player_totals.values(), key=lambda x: x["weeks_on_roster"], reverse=True)
    return ranked[:10]


# ---------------------------------------------------------------------------
# /teams/{name}/players  — Simplified player history per season
# ---------------------------------------------------------------------------

def get_team_players(display_name: str) -> dict:
    """
    Per-season player roster for a manager.

    For each season returns players ordered by total points (desc):
      - name, position, total_points
      - weeks_on_roster, weeks_as_starter
      - season-by-season breakdown (from seeded config data)

    Data source: PLAYER_HISTORY_MANUAL in config.py (seeded after each season).
    Falls back to live API fetch for current/unseeded seasons.
    """
    from config import LEAGUE_CONFIG, get_player_history

    manager_data = _get_manager_data(display_name)
    if not manager_data:
        raise Exception(f"Manager '{display_name}' not found.")

    manager_id    = manager_data["manager_id"]
    seeded_data   = get_player_history(manager_id)
    seasons_data  = get_all_seasons()
    blackgold_keys= {s["league_key"] for s in seasons_data.get("seasons", [])}

    seasons_out = []

    for season in _get_seasons_for_manager(display_name):
        year       = season["year"]
        league_key = season["league_key"]
        team_key   = season["team_key"]

        if league_key not in blackgold_keys:
            continue

        seed = seeded_data.get(year, {})

        if seed.get("players"):
            # Fast path: use hardcoded data
            players = _players_from_seed(seed["players"])
            source  = "seeded"
        else:
            # Live fetch fallback (current/unseeded season only)
            players = _fetch_players_live(league_key, team_key)
            source  = "live" if players else None

        seasons_out.append({
            "year":       year,
            "team_name":  None,   # enriched below if we have seed data
            "source":     source,
            "players":    players,
        })

    seasons_out.sort(key=lambda r: r["year"], reverse=True)

    return {
        "display_name": manager_data["display_name"],
        "manager_id":   manager_id,
        "league":       LEAGUE_CONFIG["name"],
        "seasons":      seasons_out,
    }


def _players_from_seed(players_dict: dict) -> list:
    """Convert seeded players dict to sorted list (most points first)."""
    result = []
    for player_key, p in players_dict.items():
        result.append({
            "player_key":       player_key,
            "name":             p.get("name"),
            "position":         p.get("position"),
            "total_points":     p.get("total_points"),
            "weeks_on_roster":  p.get("weeks_on_roster"),
            "weeks_as_starter": p.get("weeks_as_starter"),
            "acquired_type":    p.get("acquired_type"),
            "acquired_detail":  p.get("acquired_detail"),
        })
    result.sort(key=lambda x: (x.get("total_points") or 0), reverse=True)
    return result


def _fetch_players_live(league_key: str, team_key: str) -> list:
    """
    Live fallback: fetch rostered players + season stats for unseeded seasons.
    Returns list sorted by total_points desc, or empty list on failure.
    """
    try:
        query   = get_query(league_key)
        team_id = _team_id_from_key(team_key)

        roster_raw  = query.get_team_roster_player_stats_by_season(team_id)
        roster_dict = _convert_to_dict(roster_raw)

        players = []
        raw_list = roster_dict if isinstance(roster_dict, list) else \
                   roster_dict.get("players", [])

        for item in raw_list:
            p    = item.get("player", item) if isinstance(item, dict) else {}
            name = p.get("full_name") or p.get("name")
            pos  = (p.get("display_position") or p.get("primary_position") or "")
            pos  = str(pos).split(",")[0].strip()
            pts_raw = (p.get("player_points_total") or p.get("points_total")
                       or p.get("total_points") or 0)
            try:
                pts = float(pts_raw)
            except (TypeError, ValueError):
                pts = 0.0

            if not name:
                continue

            players.append({
                "player_key":       p.get("player_key"),
                "name":             name,
                "position":         pos,
                "total_points":     pts,
                "weeks_on_roster":  None,  # not available from season stats call
                "weeks_as_starter": None,
                "acquired_type":    None,
                "acquired_detail":  None,
            })

        players.sort(key=lambda x: (x.get("total_points") or 0), reverse=True)
        return players

    except Exception:
        return []


# ---------------------------------------------------------------------------
# GET /league/seed?year=YYYY — Admin endpoint data builder
# ---------------------------------------------------------------------------

def build_season_seed(year: int) -> dict:
    """
    Builds the full PLAYER_HISTORY_MANUAL config block for all managers
    for a given season. Run once after each season ends.

    Fetches for every active manager that season:
      - Weekly rosters (to count weeks_on_roster / weeks_as_starter)
      - Season player stats (total points)
      - Draft results (acquisition info)
      - Transaction log (trade/waiver acquisition info)

    Returns a dict ready to paste into PLAYER_HISTORY_MANUAL in config.py.
    """
    from config import MANAGER_IDENTITY_MAP
    from services.fantasy.league_service import get_league_key_for_season

    league_key = get_league_key_for_season(str(year))
    query      = get_query(league_key)

    # Get all teams for this season
    team_map = _get_all_team_map(query)

    # Get playoff start week from settings
    try:
        settings_raw = query.get_league_settings()
        settings_dict = _convert_to_dict(settings_raw)
        playoff_start = int(settings_dict.get("playoff_start_week") or 15)
        end_week      = int(settings_dict.get("end_week") or 17)
    except Exception:
        playoff_start = 15
        end_week      = 17

    # Build acquisition map from draft results
    acq_map = _build_acquisition_map(query, league_key)

    result = {}

    for team_key, team_dict in team_map.items():
        identity = get_manager_identity(team_key=team_key)
        if not identity:
            continue

        manager_id   = identity["manager_id"]
        team_id      = _team_id_from_key(team_key)
        team_name    = team_dict.get("name", "")

        # --- Weekly roster scan ---
        # player_key -> {weeks_on_roster, weeks_as_starter, points_by_week}
        player_weekly: dict = {}

        for week in range(1, end_week + 1):
            try:
                roster_raw  = query.get_team_roster_by_week(team_id, week)
                roster_dict = _convert_to_dict(roster_raw)
                players_raw = _extract_roster_players(roster_dict)

                for p in players_raw:
                    pk       = p.get("player_key") or p.get("player_id")
                    pname    = p.get("full_name") or p.get("name")
                    pos_raw  = p.get("display_position") or p.get("primary_position") or ""
                    pos      = str(pos_raw).split(",")[0].strip()
                    slot     = p.get("selected_position") or p.get("starting_status") or ""
                    is_start = str(slot).upper() not in ("BN", "IR", "BENCH", "")

                    # Try to get points for this player this week
                    pts_raw = (p.get("player_points") or p.get("points") or
                               p.get("player_points_total") or 0)
                    try:
                        pts = float(pts_raw)
                    except (TypeError, ValueError):
                        pts = 0.0

                    if not pk or not pname:
                        continue

                    if pk not in player_weekly:
                        player_weekly[pk] = {
                            "name":             pname,
                            "position":         pos,
                            "weeks_on_roster":  0,
                            "weeks_as_starter": 0,
                            "total_points":     0.0,
                        }

                    player_weekly[pk]["weeks_on_roster"]  += 1
                    if is_start:
                        player_weekly[pk]["weeks_as_starter"] += 1
                    player_weekly[pk]["total_points"] += pts

            except Exception:
                continue

        # --- Top starters by position ---
        POSITIONS = ["QB", "WR", "RB", "TE"]
        top_starters = {}
        for pos in POSITIONS:
            candidates = [
                (pk, d) for pk, d in player_weekly.items()
                if d["position"] == pos and d["weeks_as_starter"] > 0
            ]
            if candidates:
                best_pk, best_d = max(candidates, key=lambda x: x[1]["total_points"])
                top_starters[pos] = {
                    "name":          best_d["name"],
                    "team_name":     team_name,
                    "total_points":  round(best_d["total_points"], 2),
                    "weeks_started": best_d["weeks_as_starter"],
                }

        # --- Frequent players top 10 ---
        frequent = sorted(
            player_weekly.values(),
            key=lambda d: d["weeks_on_roster"],
            reverse=True
        )[:10]
        frequent_out = [
            {
                "name":             d["name"],
                "position":         d["position"],
                "weeks_on_roster":  d["weeks_on_roster"],
                "weeks_as_starter": d["weeks_as_starter"],
                "total_points":     round(d["total_points"], 2),
            }
            for d in frequent
        ]

        # --- Starter points total ---
        starter_pts = sum(
            d["total_points"] for d in player_weekly.values()
            if d["weeks_as_starter"] > 0
        )

        # --- Players dict (all players, acquisition info merged) ---
        players_out = {}
        for pk, d in player_weekly.items():
            acq = acq_map.get(team_key, {}).get(pk, {})
            players_out[pk] = {
                "name":             d["name"],
                "position":         d["position"],
                "total_points":     round(d["total_points"], 2),
                "weeks_on_roster":  d["weeks_on_roster"],
                "weeks_as_starter": d["weeks_as_starter"],
                "acquired_type":    acq.get("type"),
                "acquired_detail":  acq.get("detail"),
            }

        result[manager_id] = {
            year: {
                "top_starters":         top_starters,
                "frequent_players":     frequent_out,
                "starter_points_total": round(starter_pts, 2),
                "players":              players_out,
            }
        }

    return result


def _build_acquisition_map(query, league_key: str) -> dict:
    """
    Returns {team_key: {player_key: {type, detail}}}
    Merges draft picks + transactions.
    """
    acq: dict = {}

    # Draft results
    try:
        draft_raw  = query.get_league_draft_results()
        draft_dict = _convert_to_dict(draft_raw)
        picks      = draft_dict if isinstance(draft_dict, list) else draft_dict.get("draft_results", [])

        for item in picks:
            p    = item.get("draft_result", item) if isinstance(item, dict) else {}
            tk   = p.get("team_key")
            pk   = p.get("player_key")
            pick = p.get("pick")
            rnd  = p.get("round")
            if not tk or not pk:
                continue
            if tk not in acq:
                acq[tk] = {}
            detail = f"Pick {rnd}.{str(pick).zfill(2)}" if rnd and pick else f"Pick #{pick}"
            acq[tk][pk] = {"type": "draft", "detail": detail}

    except Exception:
        pass

    # Transactions (adds = waiver/FA, trades)
    try:
        trans_raw  = query.get_league_transactions()
        trans_dict = _convert_to_dict(trans_raw)
        trans_list = trans_dict if isinstance(trans_dict, list) else trans_dict.get("transactions", [])

        for item in trans_list:
            tx   = item.get("transaction", item) if isinstance(item, dict) else {}
            ttype = tx.get("type", "")  # "add", "trade", "drop"
            faab  = tx.get("faab_bid")

            players_raw = tx.get("players", [])
            if isinstance(players_raw, dict):
                players_raw = [players_raw]

            for pw in players_raw:
                pp   = pw.get("player", pw) if isinstance(pw, dict) else {}
                pk   = pp.get("player_key")
                td   = pp.get("transaction_data", {})
                if isinstance(td, list):
                    td = td[0] if td else {}
                dest_type = td.get("destination_type", "")
                dest_team = td.get("destination_team_key", "")
                src_team  = td.get("source_team_key", "")

                if not pk or not dest_team:
                    continue
                if dest_team not in acq:
                    acq[dest_team] = {}
                # Don't overwrite a draft pick entry
                if pk in acq.get(dest_team, {}):
                    continue

                if ttype == "trade":
                    identity = get_manager_identity(team_key=src_team)
                    from_name = identity["display_name"] if identity else src_team
                    acq[dest_team][pk] = {"type": "trade", "detail": f"From: {from_name}"}
                elif ttype in ("add", "waiver", "freeagent"):
                    if faab:
                        acq[dest_team][pk] = {"type": "waiver", "detail": f"${faab} FAAB"}
                    else:
                        acq[dest_team][pk] = {"type": "waiver", "detail": "Free agent"}

    except Exception:
        pass

    return acq


def _extract_roster_players(roster_dict) -> list:
    """Normalize YFPY roster response to flat list of player dicts."""
    if isinstance(roster_dict, list):
        return [(item.get("player", item) if isinstance(item, dict) else {}) for item in roster_dict]
    if isinstance(roster_dict, dict):
        raw = roster_dict.get("players") or roster_dict.get("roster", {})
        if isinstance(raw, list):
            return [(item.get("player", item) if isinstance(item, dict) else {}) for item in raw]
        if isinstance(raw, dict):
            inner = raw.get("players", [])
            if isinstance(inner, list):
                return [(item.get("player", item) if isinstance(item, dict) else {}) for item in inner]
    return []