"""
routes/fantasy/views.py
========================
Frontend-facing read endpoints for the BlackGold fantasy league.
Reads from pre-built JSON files (managers.json, results.json, matchups.json).
No Yahoo API calls — fast, cacheable responses.

URL prefix: /fantasy  (mounted in main.py)

Endpoints
---------
GET /fantasy/home                          — homepage summary
GET /fantasy/{name}/overview               — manager career overview
GET /fantasy/{name}/results                — detailed season-by-season results
GET /fantasy/{name}/matchups               — head-to-head record vs all opponents
"""

from fastapi import APIRouter, HTTPException, Query
import os, json

router = APIRouter(prefix="/fantasy", tags=["Fantasy Views"])


# ---------------------------------------------------------------------------
# Era definitions — used by /matchups toggle
# ---------------------------------------------------------------------------
ERAS = {
    "all_time":    {"label": "All-Time",      "start": 2007, "end": 9999},
    "darkness":    {"label": "Darkness Age",  "start": 2007, "end": 2011},
    "sam_era":     {"label": "Sam Era",        "start": 2009, "end": 2018},
    "frank_era":   {"label": "Frank Era",      "start": 2012, "end": 9999},
    "jordan_era":  {"label": "Jordan Era",     "start": 2019, "end": 9999},
    "auction_era": {"label": "Auction Era",    "start": 2023, "end": 9999},
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _data_path(filename: str) -> str:
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "fantasy",
    )
    return os.path.join(base, filename)


def _load(filename: str) -> dict:
    path = _data_path(filename)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        raw = json.load(f)
    # Unwrap legacy double-wrapped shape {"total_seasons":N,"years":[...],"data":{...}}
    if isinstance(raw, dict) and "data" in raw and "total_seasons" in raw:
        raw = raw["data"]
        if isinstance(raw, dict) and "data" in raw and "total_seasons" in raw:
            raw = raw["data"]
    return raw if isinstance(raw, dict) else {}


def _year_keyed(data: dict) -> dict:
    """Return only integer-keyed entries sorted descending."""
    return dict(sorted(
        {k: v for k, v in data.items() if str(k).isdigit()}.items(),
        key=lambda x: int(x[0]), reverse=True,
    ))


def _finished_seasons(results: dict) -> dict:
    """Return only seasons where is_finished = true."""
    return {yr: s for yr, s in results.items() if s.get("is_finished")}


def _get_manager_data(results: dict, name: str) -> dict:
    """
    Return {year: manager_entry} for a given manager_id across all seasons.
    manager_entry comes from results[year]["managers"][name].
    """
    out = {}
    for yr, season in results.items():
        mgrs = season.get("managers", {})
        if name in mgrs:
            out[yr] = mgrs[name]
    return out


def _all_manager_ids(results: dict) -> set:
    ids = set()
    for season in results.values():
        ids.update(season.get("managers", {}).keys())
    return ids


def _display_name(manager_id: str, results: dict) -> str:
    """Best-effort display name from results data."""
    for season in results.values():
        m = season.get("managers", {}).get(manager_id, {})
        if m.get("display_name"):
            return m["display_name"]
    return manager_id.title()


# ===========================================================================
# GET /fantasy/home
# ===========================================================================

@router.get("/home")
def fantasy_home():
    """
    Homepage summary for the BlackGold app.

    Returns:
      - total seasons (completed + in-progress)
      - latest champion (rank=1 in most recent finished season)
      - latest last place (rank=10 in most recent finished season)
      - all-time champions list
      - all-time last place list
      - active managers (appeared in last 3 seasons)
    """
    results  = _year_keyed(_load("results.json"))
    managers = _year_keyed(_load("managers.json"))

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found or empty.")

    total_seasons    = len(results)
    finished         = _finished_seasons(results)
    finished_years   = sorted(finished.keys(), reverse=True)
    latest_yr        = finished_years[0] if finished_years else None

    # Champion + last place per finished season
    champions   = []
    last_places = []

    for yr in sorted(finished.keys(), reverse=True):
        season = finished[yr]
        mgrs   = season.get("managers", {})
        for mid, m in mgrs.items():
            rs = m.get("regular_season", {})
            rank = rs.get("rank")
            if rank == 1:
                champions.append({
                    "year":         int(yr),
                    "manager_id":   mid,
                    "display_name": m.get("display_name") or mid.title(),
                    "team_name":    m.get("team_name"),
                    "logo_url":     m.get("logo_url"),
                    "wins":         rs.get("wins"),
                    "losses":       rs.get("losses"),
                    "points_for":   rs.get("points_for"),
                })
            if rank == 10:
                last_places.append({
                    "year":         int(yr),
                    "manager_id":   mid,
                    "display_name": m.get("display_name") or mid.title(),
                    "team_name":    m.get("team_name"),
                    "logo_url":     m.get("logo_url"),
                    "wins":         rs.get("wins"),
                    "losses":       rs.get("losses"),
                    "points_for":   rs.get("points_for"),
                })

    # Latest champion / last place
    latest_champion  = champions[0]  if champions  else None
    latest_last      = last_places[0] if last_places else None

    # Championship counts
    champ_counts = {}
    for c in champions:
        mid = c["manager_id"]
        champ_counts[mid] = champ_counts.get(mid, 0) + 1

    last_counts = {}
    for l in last_places:
        mid = l["manager_id"]
        last_counts[mid] = last_counts.get(mid, 0) + 1

    # Active managers: appeared in any of the last 3 seasons
    recent_years   = sorted(results.keys(), reverse=True)[:3]
    active_managers = set()
    for yr in recent_years:
        active_managers.update(results[yr].get("managers", {}).keys())

    return {
        "league_name":      "BlackGold",
        "total_seasons":    total_seasons,
        "finished_seasons": len(finished),
        "years_active":     f"2007–{max(results.keys())}",
        "latest_champion":  latest_champion,
        "latest_last_place": latest_last,
        "all_time_champions": champions,
        "all_time_last_places": last_places,
        "championship_counts": sorted(
            [{"manager_id": k, "display_name": _display_name(k, results), "count": v}
             for k, v in champ_counts.items()],
            key=lambda x: x["count"], reverse=True,
        ),
        "last_place_counts": sorted(
            [{"manager_id": k, "display_name": _display_name(k, results), "count": v}
             for k, v in last_counts.items()],
            key=lambda x: x["count"], reverse=True,
        ),
        "active_managers": sorted(active_managers),
        "footer": "BlackGold is built by LL_hubl0t 2026",
    }


# ===========================================================================
# GET /fantasy/{name}/overview
# ===========================================================================

@router.get("/{name}/overview")
def manager_overview(name: str):
    """
    Career overview for one manager.

    Returns:
      - identity (display_name, profile image from most recent managers.json)
      - total seasons played
      - all-time W-L-T record
      - championships and last-place finishes
      - recent seasons summary (last 5)
    """
    results  = _year_keyed(_load("results.json"))
    managers = _year_keyed(_load("managers.json"))

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    manager_seasons = _get_manager_data(results, name)
    if not manager_seasons:
        raise HTTPException(status_code=404, detail=f"Manager '{name}' not found in results.json.")

    # Profile identity — from most recent season entry
    most_recent_entry = manager_seasons[sorted(manager_seasons.keys(), reverse=True)[0]]
    display_name = most_recent_entry.get("display_name") or name.title()
    logo_url     = most_recent_entry.get("logo_url")

    # Also check managers.json for profile image (more stable)
    profile_image = None
    for yr_data in managers.values():
        for mgr in yr_data.get("managers", []):
            if mgr.get("manager_id") == name:
                profile_image = mgr.get("logo_url")
                break
        if profile_image:
            break

    # Career totals (regular season only from standings, finished seasons)
    total_wins = total_losses = total_ties = total_games = 0
    total_pf   = total_pa    = 0.0
    championships = 0
    last_places   = 0
    seasons_played = 0
    playoffs_made  = 0
    avg_finish_sum = 0

    # Playoff career totals (from results.json playoffs block)
    pl_wins = pl_losses = pl_ties = pl_games = 0
    pl_pf   = pl_pa    = 0.0

    season_summaries = []

    for yr in sorted(manager_seasons.keys(), reverse=True):
        m      = manager_seasons[yr]
        rs     = m.get("regular_season", {})
        pl     = m.get("playoffs", {})
        season = results[yr]

        w   = rs.get("wins", 0)   or 0
        l   = rs.get("losses", 0) or 0
        t   = rs.get("ties", 0)   or 0
        pf  = rs.get("points_for", 0) or 0
        pa  = rs.get("points_against", 0) or 0
        rnk = rs.get("rank")
        seed = rs.get("playoff_seed")

        if season.get("is_finished"):
            seasons_played += 1
            total_wins   += w
            total_losses += l
            total_ties   += t
            total_games  += w + l + t
            total_pf     += pf
            total_pa     += pa
            if rnk:
                avg_finish_sum += int(rnk)
            if rnk == 1:
                championships += 1
            if rnk == 10:
                last_places += 1
            if pl.get("made_playoffs"):
                playoffs_made += 1
                pl_wins   += pl.get("wins", 0)   or 0
                pl_losses += pl.get("losses", 0) or 0
                pl_ties   += pl.get("ties", 0)   or 0
                pl_games  += (pl.get("wins", 0) or 0) + (pl.get("losses", 0) or 0) + (pl.get("ties", 0) or 0)
                pl_pf     += pl.get("points_for", 0)     or 0
                pl_pa     += pl.get("points_against", 0) or 0

        season_summaries.append({
            "year":         int(yr),
            "team_name":    m.get("team_name"),
            "is_finished":  season.get("is_finished", False),
            "wins":         w,
            "losses":       l,
            "ties":         t,
            "rank":         rnk,
            "playoff_seed": seed,
            "made_playoffs": pl.get("made_playoffs", False),
            "finish":       pl.get("finish") if pl.get("made_playoffs") else rnk,
            "points_for":   round(pf, 2),
            "points_against": round(pa, 2),
        })

    win_pct = round(total_wins / total_games, 4) if total_games else None

    return {
        "manager_id":        name,
        "display_name":      display_name,
        "logo_url":          logo_url,
        "profile_image":     profile_image or logo_url,
        "seasons_played":    seasons_played,
        "career": {
            "wins":           total_wins,
            "losses":         total_losses,
            "ties":           total_ties,
            "games":          total_games,
            "win_pct":        win_pct,
            "championships":  championships,
            "last_places":    last_places,
            "playoffs_made":  playoffs_made,
            "avg_finish":     round(avg_finish_sum / seasons_played, 2) if seasons_played else None,
            "total_points_for":     round(total_pf, 2),
            "total_points_against": round(total_pa, 2),
            "avg_points_for":       round(total_pf / total_games, 2) if total_games else None,
            "avg_points_against":   round(total_pa / total_games, 2) if total_games else None,
        },
        "career_playoffs": {
            "made_playoffs":  playoffs_made,
            "wins":           pl_wins,
            "losses":         pl_losses,
            "ties":           pl_ties,
            "games":          pl_games,
            "win_pct":        round(pl_wins / pl_games, 4) if pl_games else None,
            "total_points_for":     round(pl_pf, 2),
            "total_points_against": round(pl_pa, 2),
            "avg_points_for":       round(pl_pf / pl_games, 2) if pl_games else None,
            "avg_points_against":   round(pl_pa / pl_games, 2) if pl_games else None,
        },
        "seasons": season_summaries,
    }


# ===========================================================================
# GET /fantasy/{name}/results
# ===========================================================================

@router.get("/{name}/results")
def manager_results(name: str):
    """
    Detailed season-by-season results for one manager.
    Includes overall era totals and per-season breakdown.

    Returns record, points, ranks, and playoff performance.
    """
    results = _year_keyed(_load("results.json"))
    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    manager_seasons = _get_manager_data(results, name)
    if not manager_seasons:
        raise HTTPException(status_code=404, detail=f"Manager '{name}' not found.")

    display_name = _display_name(name, results)

    # Helper: aggregate stats for a set of seasons
    def _aggregate(season_keys: list) -> dict:
        w = l = t = g = 0
        pf = pa = proj_pf = proj_pa = 0.0
        pl_w = pl_l = pl_t = pl_g = 0
        pl_pf = pl_pa = 0.0
        champs = lasts = pl_made = 0
        pf_ranks = []
        pa_ranks = []
        finish_sum = finish_n = 0

        for yr in season_keys:
            if yr not in manager_seasons:
                continue
            m  = manager_seasons[yr]
            rs = m.get("regular_season", {})
            pl = m.get("playoffs", {})
            season = results.get(yr, {})
            if not season.get("is_finished"):
                continue

            w  += rs.get("wins", 0)   or 0
            l  += rs.get("losses", 0) or 0
            t  += rs.get("ties", 0)   or 0
            g  += (rs.get("wins", 0) or 0) + (rs.get("losses", 0) or 0) + (rs.get("ties", 0) or 0)
            pf += rs.get("points_for", 0)     or 0
            pa += rs.get("points_against", 0) or 0
            proj_pf += rs.get("projected_points_for", 0)     or 0
            proj_pa += rs.get("projected_points_against", 0) or 0

            if rs.get("points_for_rank"):
                pf_ranks.append(rs["points_for_rank"])
            if rs.get("points_against_rank"):
                pa_ranks.append(rs["points_against_rank"])
            if rs.get("rank") == 1:
                champs += 1
            if rs.get("rank") == 10:
                lasts += 1
            if pl.get("made_playoffs"):
                pl_made += 1
                pl_w  += pl.get("wins", 0)   or 0
                pl_l  += pl.get("losses", 0) or 0
                pl_t  += pl.get("ties", 0)   or 0
                pl_g  += (pl.get("wins",0) or 0) + (pl.get("losses",0) or 0) + (pl.get("ties",0) or 0)
                pl_pf += pl.get("points_for", 0)     or 0
                pl_pa += pl.get("points_against", 0) or 0
                if pl.get("finish"):
                    finish_sum += pl["finish"]
                    finish_n   += 1

        seasons_n = sum(1 for yr in season_keys if yr in manager_seasons and results.get(yr, {}).get("is_finished"))
        return {
            "seasons_included": seasons_n,
            "regular_season": {
                "wins": w, "losses": l, "ties": t, "games": g,
                "win_pct":           round(w / g, 4) if g else None,
                "championships":     champs,
                "last_places":       lasts,
                "playoffs_made":     pl_made,
                "total_points_for":  round(pf, 2),
                "avg_points_for":    round(pf / g, 2) if g else None,
                "avg_pf_rank":       round(sum(pf_ranks) / len(pf_ranks), 2) if pf_ranks else None,
                "total_points_against": round(pa, 2),
                "avg_points_against":   round(pa / g, 2) if g else None,
                "avg_pa_rank":          round(sum(pa_ranks) / len(pa_ranks), 2) if pa_ranks else None,
            },
            "playoffs": {
                "made_playoffs":     pl_made,
                "wins": pl_w, "losses": pl_l, "ties": pl_t, "games": pl_g,
                "win_pct":           round(pl_w / pl_g, 4) if pl_g else None,
                "avg_finish":        round(finish_sum / finish_n, 2) if finish_n else None,
                "total_points_for":  round(pl_pf, 2),
                "avg_points_for":    round(pl_pf / pl_g, 2) if pl_g else None,
                "total_points_against": round(pl_pa, 2),
                "avg_points_against":   round(pl_pa / pl_g, 2) if pl_g else None,
            },
        }

    all_years = sorted(manager_seasons.keys())

    # Era aggregates
    era_totals = {}
    for era_key, era in ERAS.items():
        era_years = [yr for yr in all_years if era["start"] <= int(yr) <= era["end"]]
        if era_years:
            era_totals[era_key] = {
                "label":   era["label"],
                "years":   f"{era['start']}–{min(era['end'], int(max(era_years)))}",
                **_aggregate(era_years),
            }

    # Per-season detail
    season_detail = []
    for yr in sorted(manager_seasons.keys(), reverse=True):
        m  = manager_seasons[yr]
        rs = m.get("regular_season", {})
        pl = m.get("playoffs", {})
        season_detail.append({
            "year":         int(yr),
            "is_finished":  results[yr].get("is_finished", False),
            "team_name":    m.get("team_name"),
            "logo_url":     m.get("logo_url"),
            "regular_season": rs,
            "playoffs":       pl,
        })

    return {
        "manager_id":   name,
        "display_name": display_name,
        "era_totals":   era_totals,
        "seasons":      season_detail,
    }


# ===========================================================================
# GET /fantasy/{name}/matchups
# ===========================================================================

@router.get("/{name}/matchups")
def manager_matchups(
    name: str,
    era:  str = Query(default="all_time", description=(
        "Era filter: all_time | darkness | sam_era | frank_era | jordan_era | auction_era"
    )),
):
    """
    Head-to-head record for one manager vs all opponents.

    Aggregates from matchups.json. Separates regular season from true playoffs
    (is_playoffs=true AND is_consolation=false).

    Returns per-opponent: W-L-T, avg points for, avg points against, point diff.
    Era filter controls which seasons are included.
    """
    matchups_data = _year_keyed(_load("matchups.json"))
    results       = _year_keyed(_load("results.json"))

    if not matchups_data:
        raise HTTPException(status_code=404, detail="matchups.json not found.")

    era_def = ERAS.get(era)
    if not era_def:
        raise HTTPException(status_code=400, detail=f"Unknown era '{era}'. Valid: {list(ERAS.keys())}")

    display_name = _display_name(name, results)

    # Accumulators: {opponent_id: {rs: {...}, pl: {...}}}
    h2h: dict[str, dict] = {}

    def _acc():
        return {"wins": 0, "losses": 0, "ties": 0, "games": 0,
                "pf_sum": 0.0, "pa_sum": 0.0}

    for yr, season in matchups_data.items():
        if not (era_def["start"] <= int(yr) <= era_def["end"]):
            continue

        for week_obj in season.get("weeks", []):
            for matchup in week_obj.get("matchups", []):
                teams = matchup.get("teams", [])
                if len(teams) != 2:
                    continue

                # Check if our manager is in this matchup
                my_team  = next((t for t in teams if t.get("manager_id") == name), None)
                opp_team = next((t for t in teams if t.get("manager_id") != name), None)
                if not my_team or not opp_team:
                    continue

                is_playoffs    = matchup.get("is_playoffs", False)
                is_consolation = matchup.get("is_consolation", False)
                is_tied        = matchup.get("is_tied", False)

                # Skip consolation bracket entirely — these are loser's playoffs
                # for seeds 5-8 and do not count toward head-to-head records
                if is_consolation:
                    continue

                is_true_playoff = is_playoffs and not is_consolation

                bucket = "playoffs" if is_true_playoff else "regular_season"
                opp_id = opp_team.get("manager_id") or opp_team.get("team_key", "unknown")

                if opp_id not in h2h:
                    h2h[opp_id] = {
                        "regular_season": _acc(),
                        "playoffs":       _acc(),
                        "opponent_display_name": opp_team.get("display_name") or opp_id.title(),
                    }

                b    = h2h[opp_id][bucket]
                my_pts  = my_team.get("points", 0)  or 0
                opp_pts = opp_team.get("points", 0) or 0

                b["games"] += 1
                b["pf_sum"] = round(b["pf_sum"] + my_pts,  2)
                b["pa_sum"] = round(b["pa_sum"] + opp_pts, 2)

                if is_tied:
                    b["ties"]   += 1
                elif my_team.get("is_winner"):
                    b["wins"]   += 1
                else:
                    b["losses"] += 1

    # Format output
    def _fmt(acc: dict) -> dict:
        g = acc["games"]
        return {
            "wins":         acc["wins"],
            "losses":       acc["losses"],
            "ties":         acc["ties"],
            "games":        g,
            "win_pct":      round(acc["wins"] / g, 4) if g else None,
            "avg_pf":       round(acc["pf_sum"] / g, 2) if g else None,
            "avg_pa":       round(acc["pa_sum"] / g, 2) if g else None,
            "avg_diff":     round((acc["pf_sum"] - acc["pa_sum"]) / g, 2) if g else None,
            "total_pf":     acc["pf_sum"],
            "total_pa":     acc["pa_sum"],
        }

    opponents = []
    for opp_id, data in sorted(h2h.items()):
        rs = _fmt(data["regular_season"])
        pl = _fmt(data["playoffs"])
        total_games = rs["games"] + pl["games"]
        total_wins  = data["regular_season"]["wins"] + data["playoffs"]["wins"]
        opponents.append({
            "opponent_id":           opp_id,
            "opponent_display_name": data["opponent_display_name"],
            "combined_record":       f"{total_wins}-{total_games - total_wins - data['regular_season']['ties'] - data['playoffs']['ties']}-{data['regular_season']['ties'] + data['playoffs']['ties']}",
            "regular_season":        rs,
            "playoffs":              pl,
        })

    # Sort by most games played
    opponents.sort(key=lambda x: x["regular_season"]["games"], reverse=True)

    # Overall RS and playoff totals vs everyone
    all_rs = _acc()
    all_pl = _acc()
    for data in h2h.values():
        for field in ("wins","losses","ties","games"):
            all_rs[field] += data["regular_season"][field]
            all_pl[field] += data["playoffs"][field]
        all_rs["pf_sum"] = round(all_rs["pf_sum"] + data["regular_season"]["pf_sum"], 2)
        all_rs["pa_sum"] = round(all_rs["pa_sum"] + data["regular_season"]["pa_sum"], 2)
        all_pl["pf_sum"] = round(all_pl["pf_sum"] + data["playoffs"]["pf_sum"], 2)
        all_pl["pa_sum"] = round(all_pl["pa_sum"] + data["playoffs"]["pa_sum"], 2)

    return {
        "manager_id":     name,
        "display_name":   display_name,
        "era":            era,
        "era_label":      era_def["label"],
        "era_years":      f"{era_def['start']}–present" if era_def['end'] == 9999 else f"{era_def['start']}–{era_def['end']}",
        "available_eras": {k: v["label"] for k, v in ERAS.items()},
        "overall": {
            "regular_season": _fmt(all_rs),
            "playoffs":       _fmt(all_pl),
        },
        "opponents": opponents,
    }


# ===========================================================================
# GET /fantasy/matchups/{name1}/vs/{name2}
# ===========================================================================

@router.get("/matchups/{name1}/vs/{name2}")
def head_to_head(
    name1: str,
    name2: str,
    era: str = Query(default="all_time", description=(
        "Era filter: all_time | darkness | sam_era | frank_era | jordan_era | auction_era"
    )),
):
    """
    Full head-to-head history between two managers.

    Returns:
      - Regular season W-L-T, avg PF/PA, avg diff
      - Playoff W-L-T, avg PF/PA (true playoffs only, no consolation)
      - Last 5 matchup record
      - All matchups newest to oldest with winner, points, projected, diff
    """
    matchups_data = _year_keyed(_load("matchups.json"))
    results       = _year_keyed(_load("results.json"))

    if not matchups_data:
        raise HTTPException(status_code=404, detail="matchups.json not found.")

    era_def = ERAS.get(era)
    if not era_def:
        raise HTTPException(status_code=400, detail=f"Unknown era '{era}'. Valid: {list(ERAS.keys())}")

    # Validate both managers exist
    all_ids = _all_manager_ids(results)
    if name1 not in all_ids:
        raise HTTPException(status_code=404, detail=f"Manager '{name1}' not found.")
    if name2 not in all_ids:
        raise HTTPException(status_code=404, detail=f"Manager '{name2}' not found.")

    display1 = _display_name(name1, results)
    display2 = _display_name(name2, results)

    def _acc():
        return {"wins": 0, "losses": 0, "ties": 0, "games": 0,
                "pf_sum": 0.0, "pa_sum": 0.0,
                "proj_pf_sum": 0.0, "proj_pa_sum": 0.0, "proj_weeks": 0}

    rs_totals = _acc()   # name1's perspective: pf = name1 pts, pa = name2 pts
    pl_totals = _acc()
    all_matchups = []    # every matchup newest→oldest

    for yr in sorted(matchups_data.keys(), reverse=True):
        if not (era_def["start"] <= int(yr) <= era_def["end"]):
            continue
        season = matchups_data[yr]

        # Iterate weeks in reverse so all_matchups ends up newest first
        for week_obj in reversed(season.get("weeks", [])):
            for matchup in week_obj.get("matchups", []):
                teams = matchup.get("teams", [])
                if len(teams) != 2:
                    continue

                t1 = next((t for t in teams if t.get("manager_id") == name1), None)
                t2 = next((t for t in teams if t.get("manager_id") == name2), None)
                if not t1 or not t2:
                    continue  # not a matchup between these two

                is_playoffs    = matchup.get("is_playoffs", False)
                is_consolation = matchup.get("is_consolation", False)
                is_tied        = matchup.get("is_tied", False)

                # Skip consolation games entirely
                if is_consolation:
                    continue

                is_true_playoff = is_playoffs and not is_consolation
                bucket = pl_totals if is_true_playoff else rs_totals

                pts1  = t1.get("points", 0)    or 0
                pts2  = t2.get("points", 0)    or 0
                proj1 = t1.get("projected", 0) or 0
                proj2 = t2.get("projected", 0) or 0

                bucket["games"]   += 1
                bucket["pf_sum"]   = round(bucket["pf_sum"]  + pts1, 2)
                bucket["pa_sum"]   = round(bucket["pa_sum"]  + pts2, 2)

                # Projected may be 0 for older seasons — only count when non-zero
                if proj1 or proj2:
                    bucket["proj_pf_sum"]  = round(bucket["proj_pf_sum"] + proj1, 2)
                    bucket["proj_pa_sum"]  = round(bucket["proj_pa_sum"] + proj2, 2)
                    bucket["proj_weeks"]  += 1

                if is_tied:
                    bucket["ties"]   += 1
                elif t1.get("is_winner"):
                    bucket["wins"]   += 1
                else:
                    bucket["losses"] += 1

                # Determine winner display name
                if is_tied:
                    winner_name = None
                elif t1.get("is_winner"):
                    winner_name = display1
                else:
                    winner_name = display2

                all_matchups.append({
                    "year":           int(yr),
                    "week":           matchup.get("week"),
                    "week_start":     matchup.get("week_start"),
                    "week_end":       matchup.get("week_end"),
                    "is_playoffs":    is_playoffs,
                    "is_tied":        is_tied,
                    "winner":         winner_name,
                    name1: {
                        "manager_id":   name1,
                        "display_name": display1,
                        "team_name":    t1.get("team_name"),
                        "points":       round(pts1, 2),
                        "projected":    round(proj1, 2),
                        "is_winner":    t1.get("is_winner", False),
                    },
                    name2: {
                        "manager_id":   name2,
                        "display_name": display2,
                        "team_name":    t2.get("team_name"),
                        "points":       round(pts2, 2),
                        "projected":    round(proj2, 2),
                        "is_winner":    t2.get("is_winner", False),
                    },
                    "point_diff":     round(pts1 - pts2, 2),
                    "projected_diff": round(proj1 - proj2, 2) if (proj1 or proj2) else None,
                })

    def _fmt(acc: dict) -> dict:
        g  = acc["games"]
        pw = acc["proj_weeks"]
        return {
            "wins":    acc["wins"],
            "losses":  acc["losses"],
            "ties":    acc["ties"],
            "games":   g,
            "win_pct": round(acc["wins"] / g, 4) if g else None,
            "avg_pf":  round(acc["pf_sum"] / g, 2) if g else None,
            "avg_pa":  round(acc["pa_sum"] / g, 2) if g else None,
            "avg_diff":round((acc["pf_sum"] - acc["pa_sum"]) / g, 2) if g else None,
            "total_pf":acc["pf_sum"],
            "total_pa":acc["pa_sum"],
            "avg_projected_pf":  round(acc["proj_pf_sum"] / pw, 2) if pw else None,
            "avg_projected_pa":  round(acc["proj_pa_sum"] / pw, 2) if pw else None,
        }

    # Last 5 matchups record (from all_matchups which is newest-first)
    last5 = all_matchups[:5]
    last5_wins   = sum(1 for m in last5 if m[name1]["is_winner"])
    last5_losses = sum(1 for m in last5 if m[name2]["is_winner"])
    last5_ties   = sum(1 for m in last5 if m["is_tied"])

    return {
        "manager_1":        {"manager_id": name1, "display_name": display1},
        "manager_2":        {"manager_id": name2, "display_name": display2},
        "era":              era,
        "era_label":        era_def["label"],
        "available_eras":   {k: v["label"] for k, v in ERAS.items()},
        "total_matchups":   len(all_matchups),
        "regular_season":   _fmt(rs_totals),
        "playoffs":         _fmt(pl_totals),
        "last_5": {
            "wins":    last5_wins,
            "losses":  last5_losses,
            "ties":    last5_ties,
            "matchups": last5,
        },
        "all_matchups": all_matchups,
    }


# ===========================================================================
# GET /fantasy/managers  — list all known managers
# ===========================================================================

@router.get("/managers")
def list_managers():
    """
    Returns all manager IDs and display names that have appeared in any season.
    Useful for building navigation menus.
    """
    results = _year_keyed(_load("results.json"))
    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    seen: dict[str, dict] = {}
    for yr in sorted(results.keys(), reverse=True):
        season = results[yr]
        for mid, m in season.get("managers", {}).items():
            if mid not in seen:
                seen[mid] = {
                    "manager_id":   mid,
                    "display_name": m.get("display_name") or mid.title(),
                    "logo_url":     m.get("logo_url"),
                    "first_season": int(yr),
                    "last_season":  int(yr),
                }
            else:
                seen[mid]["first_season"] = min(seen[mid]["first_season"], int(yr))

    managers_list = sorted(seen.values(), key=lambda x: x["display_name"])
    return {
        "total_managers": len(managers_list),
        "managers":        managers_list,
    }


# ===========================================================================
# GET /fantasy/seasons — season index
# ===========================================================================

@router.get("/seasons")
def list_seasons():
    """
    Returns all seasons with basic metadata.
    """
    results = _year_keyed(_load("results.json"))
    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    seasons = []
    for yr in sorted(results.keys(), reverse=True):
        season = results[yr]
        mgrs   = season.get("managers", {})
        champion = next(
            ({"manager_id": mid, "display_name": m.get("display_name") or mid.title(), "team_name": m.get("team_name")}
             for mid, m in mgrs.items() if m.get("regular_season", {}).get("rank") == 1),
            None
        )
        last = next(
            ({"manager_id": mid, "display_name": m.get("display_name") or mid.title(), "team_name": m.get("team_name")}
             for mid, m in mgrs.items() if m.get("regular_season", {}).get("rank") == 10),
            None
        )
        seasons.append({
            "year":        int(yr),
            "is_finished": season.get("is_finished", False),
            "num_managers": len(mgrs),
            "champion":    champion,
            "last_place":  last,
        })

    return {"total_seasons": len(seasons), "seasons": seasons}