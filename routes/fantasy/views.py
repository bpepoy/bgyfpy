"""
routes/fantasy/views.py
========================
Frontend-facing read endpoints for the BlackGold fantasy league.
Reads from pre-built JSON files (managers.json, results.json, matchups.json).
No Yahoo API calls — fast, cacheable responses.

URL prefix: /fantasy  (mounted in main.py)

BRD sections: /fantasy/{name}, /fantasy/league, /fantasy/season, /fantasy/teams

Endpoints
---------
GET /fantasy/league/home                  — homepage summary
GET /fantasy/{name}/overview               — manager career overview
GET /fantasy/{name}/results                — detailed season-by-season results
GET /fantasy/teams/matchups/{name}         — head-to-head record vs all opponents
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

@router.get("/teams/matchups/{name}")
def teams_matchups(
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

@router.get("/teams/matchups/{name1}/vs/{name2}")
def teams_matchups_vs(
    name1: str,
    name2: str,
    era: str = Query(default="all_time", description=(
        "Era filter: all_time | darkness | sam_era | frank_era | jordan_era | auction_era"
    )),
):
    """
    Full head-to-head history between two managers.

    Returns:
      - Regular season W-L-T, avg PF/PA/projected, avg diff
      - Playoff W-L-T (true playoffs only, no consolation)
      - Current streak (consecutive W/L/T from most recent matchup)
      - Last 5 matchup record
      - All matchups newest to oldest with winner, points, projected, diff
      - Per-matchup player breakdown (starters + bench) when rosters and
        player_stats are available — frontend shows collapsed, expands on tap
    """
    matchups_data = _year_keyed(_load("matchups.json"))
    results       = _year_keyed(_load("results.json"))
    rosters       = _load("rosters.json")
    player_stats  = _load("player_stats.json")
    player_info   = _load("player_info.json")

    if not matchups_data:
        raise HTTPException(status_code=404, detail="matchups.json not found.")

    era_def = ERAS.get(era)
    if not era_def:
        raise HTTPException(status_code=400, detail=f"Unknown era '{era}'. Valid: {list(ERAS.keys())}")

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

    rs_totals    = _acc()
    pl_totals    = _acc()
    all_matchups = []

    # ── position sort order for player breakdown ──────────────────────────────
    POS_ORDER = {"QB": 0, "WR": 1, "RB": 2, "TE": 3, "FLEX": 4, "W/R/T": 4,
                 "K": 5, "DEF": 6, "D/ST": 6, "BN": 7, "IR": 8, "IR+": 8}

    def _player_breakdown(yr: str, wk_num: int, mid: str) -> list | None:
        """Return starters-first player list with week pts. None if data unavailable."""
        wk_key    = f"week_{wk_num}"
        yr_roster = rosters.get(yr, {})
        yr_stats  = player_stats.get(yr, {})
        yr_info   = (player_info.get(yr, {}) or {}).get("players", {})

        team_roster = yr_roster.get(wk_key, {}).get(mid, {})
        slots       = team_roster.get("players", [])
        if not slots:
            return None

        wk_stats = yr_stats.get(wk_key, {})
        out      = []
        for slot in slots:
            if not isinstance(slot, dict): continue
            pk  = slot.get("player_key") or ""
            pi  = yr_info.get(pk, {})
            sp  = slot.get("selected_position") or ""
            pts_raw = wk_stats.get(pk)
            pts = float(pts_raw.get("fantasy_points") or 0) if isinstance(pts_raw, dict) else 0.0
            out.append({
                "player_key":        pk,
                "name":              pi.get("name") or pk,
                "position":          pi.get("position") or sp,
                "selected_position": sp,
                "nfl_team":          pi.get("nfl_team"),
                "is_starting":       slot.get("is_starting", False),
                "is_on_bench":       slot.get("is_on_bench", False),
                "week_pts":          round(pts, 2),
            })

        out.sort(key=lambda p: (
            POS_ORDER.get(p["selected_position"], 5),
            -p["week_pts"],
        ))
        return out if out else None

    for yr in sorted(matchups_data.keys(), reverse=True):
        if not (era_def["start"] <= int(yr) <= era_def["end"]):
            continue
        season = matchups_data[yr]

        for week_obj in reversed(season.get("weeks", [])):
            wk_num = week_obj.get("week", 0)
            for matchup in week_obj.get("matchups", []):
                teams = matchup.get("teams", [])
                if len(teams) != 2: continue

                t1 = next((t for t in teams if t.get("manager_id") == name1), None)
                t2 = next((t for t in teams if t.get("manager_id") == name2), None)
                if not t1 or not t2: continue

                is_playoffs    = matchup.get("is_playoffs", False)
                is_consolation = matchup.get("is_consolation", False)
                is_tied        = matchup.get("is_tied", False)

                if is_consolation: continue

                is_true_playoff = is_playoffs and not is_consolation
                bucket          = pl_totals if is_true_playoff else rs_totals

                pts1  = t1.get("points", 0)    or 0
                pts2  = t2.get("points", 0)    or 0
                proj1 = t1.get("projected", 0) or 0
                proj2 = t2.get("projected", 0) or 0

                bucket["games"]  += 1
                bucket["pf_sum"]  = round(bucket["pf_sum"] + pts1, 2)
                bucket["pa_sum"]  = round(bucket["pa_sum"] + pts2, 2)
                if proj1 or proj2:
                    bucket["proj_pf_sum"]  = round(bucket["proj_pf_sum"] + proj1, 2)
                    bucket["proj_pa_sum"]  = round(bucket["proj_pa_sum"] + proj2, 2)
                    bucket["proj_weeks"]  += 1

                if is_tied:        bucket["ties"]   += 1
                elif t1.get("is_winner"): bucket["wins"]  += 1
                else:              bucket["losses"] += 1

                winner_name = None if is_tied else (display1 if t1.get("is_winner") else display2)

                # Player breakdown — included in response, frontend collapses by default
                bd1 = _player_breakdown(yr, wk_num, name1)
                bd2 = _player_breakdown(yr, wk_num, name2)

                all_matchups.append({
                    "year":            int(yr),
                    "week":            wk_num,
                    "week_start":      matchup.get("week_start"),
                    "week_end":        matchup.get("week_end"),
                    "is_playoffs":     is_playoffs,
                    "is_tied":         is_tied,
                    "winner":          winner_name,
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
                    "point_diff":        round(pts1 - pts2, 2),
                    "projected_diff":    round(proj1 - proj2, 2) if (proj1 or proj2) else None,
                    "players_available": bd1 is not None and bd2 is not None,
                    "player_breakdown":  {name1: bd1, name2: bd2} if (bd1 or bd2) else None,
                })

    def _fmt(acc: dict) -> dict:
        g  = acc["games"]
        pw = acc["proj_weeks"]
        return {
            "wins":             acc["wins"],
            "losses":           acc["losses"],
            "ties":             acc["ties"],
            "games":            g,
            "win_pct":          round(acc["wins"] / g, 4) if g else None,
            "avg_pf":           round(acc["pf_sum"] / g, 2) if g else None,
            "avg_pa":           round(acc["pa_sum"] / g, 2) if g else None,
            "avg_diff":         round((acc["pf_sum"] - acc["pa_sum"]) / g, 2) if g else None,
            "total_pf":         acc["pf_sum"],
            "total_pa":         acc["pa_sum"],
            "avg_projected_pf": round(acc["proj_pf_sum"] / pw, 2) if pw else None,
            "avg_projected_pa": round(acc["proj_pa_sum"] / pw, 2) if pw else None,
        }

    # ── streak: walk newest-first until result changes ────────────────────────
    streak = {"type": None, "count": 0}
    for m in all_matchups:
        result = ("W" if m[name1]["is_winner"] else
                  ("T" if m["is_tied"] else "L"))
        if streak["type"] is None:
            streak = {"type": result, "count": 1}
        elif result == streak["type"]:
            streak["count"] += 1
        else:
            break

    # ── last 5 ───────────────────────────────────────────────────────────────
    last5        = all_matchups[:5]
    last5_wins   = sum(1 for m in last5 if m[name1]["is_winner"])
    last5_losses = sum(1 for m in last5 if m[name2]["is_winner"])
    last5_ties   = sum(1 for m in last5 if m["is_tied"])

    return {
        "manager_1":      {"manager_id": name1, "display_name": display1},
        "manager_2":      {"manager_id": name2, "display_name": display2},
        "era":            era,
        "era_label":      era_def["label"],
        "available_eras": {k: v["label"] for k, v in ERAS.items()},
        "total_matchups": len(all_matchups),
        "regular_season": _fmt(rs_totals),
        "playoffs":       _fmt(pl_totals),
        "current_streak": streak,
        "last_5": {
            "wins": last5_wins, "losses": last5_losses, "ties": last5_ties,
            "matchups": last5,
        },
        "all_matchups":   all_matchups,
        "_data_coverage": {
            "player_breakdown_note": "player_breakdown included per matchup when rosters.json + player_stats.json available. Frontend starts collapsed — no extra API call needed.",
        },
    }




# ===========================================================================
# GET /fantasy/teams/matchups  — league-wide H2H grid
# ===========================================================================

@router.get("/teams/matchups")
def teams_matchups_grid(
    era: str = Query(default="all_time", description=(
        "Era filter: all_time | darkness | sam_era | frank_era | jordan_era | auction_era"
    )),
):
    """
    League-wide head-to-head grid — every manager vs every other manager.

    Returns a 10×10 matrix of RS and playoff records suitable for rendering
    as a table. Each cell is manager_row's record vs manager_col.

    grid[row_manager][col_manager] = {
        regular_season: {wins, losses, ties, games, avg_pf, avg_pa, avg_diff},
        playoffs:       {wins, losses, ties, games},
        combined:       {wins, losses, ties, games, record_str}
    }

    Diagonal (self vs self) is null.
    managers list gives the display order for row/column headers.
    """
    matchups_data = _year_keyed(_load("matchups.json"))
    results       = _year_keyed(_load("results.json"))

    if not matchups_data:
        raise HTTPException(status_code=404, detail="matchups.json not found.")

    era_def = ERAS.get(era)
    if not era_def:
        raise HTTPException(status_code=400, detail=f"Unknown era '{era}'. Valid: {list(ERAS.keys())}")

    all_ids = sorted(_all_manager_ids(results))

    def _acc():
        return {"wins": 0, "losses": 0, "ties": 0, "games": 0,
                "pf_sum": 0.0, "pa_sum": 0.0}

    # grid[row_id][col_id] = {rs: acc, pl: acc}
    grid: dict = {
        mid: {opp: {"rs": _acc(), "pl": _acc()}
              for opp in all_ids if opp != mid}
        for mid in all_ids
    }

    for yr, season in matchups_data.items():
        if not (era_def["start"] <= int(yr) <= era_def["end"]):
            continue
        for week_obj in season.get("weeks", []):
            for matchup in week_obj.get("matchups", []):
                teams = matchup.get("teams", [])
                if len(teams) != 2: continue

                is_consolation = matchup.get("is_consolation", False)
                if is_consolation: continue

                is_playoffs = matchup.get("is_playoffs", False)
                is_tied     = matchup.get("is_tied", False)
                t0, t1      = teams[0], teams[1]
                m0 = t0.get("manager_id") or ""
                m1 = t1.get("manager_id") or ""
                if not m0 or not m1: continue
                if m0 not in grid or m1 not in grid[m0]: continue

                bucket_key = "pl" if is_playoffs else "rs"
                pts0 = float(t0.get("points") or 0)
                pts1 = float(t1.get("points") or 0)

                # Update both directions
                for my_id, opp_id, my_pts, opp_pts, is_winner in [
                    (m0, m1, pts0, pts1, t0.get("is_winner", False)),
                    (m1, m0, pts1, pts0, t1.get("is_winner", False)),
                ]:
                    if opp_id not in grid.get(my_id, {}): continue
                    b = grid[my_id][opp_id][bucket_key]
                    b["games"]  += 1
                    b["pf_sum"]  = round(b["pf_sum"] + my_pts,  2)
                    b["pa_sum"]  = round(b["pa_sum"] + opp_pts, 2)
                    if is_tied:    b["ties"]   += 1
                    elif is_winner: b["wins"]  += 1
                    else:           b["losses"] += 1

    def _fmt_rs(acc: dict) -> dict:
        g = acc["games"]
        return {
            "wins":    acc["wins"],
            "losses":  acc["losses"],
            "ties":    acc["ties"],
            "games":   g,
            "win_pct": round(acc["wins"] / g, 4) if g else None,
            "avg_pf":  round(acc["pf_sum"] / g, 2) if g else None,
            "avg_pa":  round(acc["pa_sum"] / g, 2) if g else None,
            "avg_diff":round((acc["pf_sum"] - acc["pa_sum"]) / g, 2) if g else None,
        }

    def _fmt_pl(acc: dict) -> dict:
        g = acc["games"]
        return {"wins": acc["wins"], "losses": acc["losses"],
                "ties": acc["ties"], "games": g}

    # Build formatted grid + row totals
    formatted_grid: dict = {}
    row_totals:     dict = {}

    for mid in all_ids:
        formatted_grid[mid] = {}
        rs_tot = _acc()
        pl_tot = _acc()

        for opp_id in all_ids:
            if opp_id == mid:
                formatted_grid[mid][opp_id] = None  # diagonal
                continue
            cell     = grid[mid][opp_id]
            rs, pl   = cell["rs"], cell["pl"]
            comb_w   = rs["wins"]   + pl["wins"]
            comb_l   = rs["losses"] + pl["losses"]
            comb_t   = rs["ties"]   + pl["ties"]
            comb_g   = rs["games"]  + pl["games"]

            formatted_grid[mid][opp_id] = {
                "regular_season": _fmt_rs(rs),
                "playoffs":       _fmt_pl(pl),
                "combined": {
                    "wins": comb_w, "losses": comb_l, "ties": comb_t,
                    "games": comb_g,
                    "record_str": f"{comb_w}-{comb_l}" + (f"-{comb_t}" if comb_t else ""),
                },
            }

            # Accumulate row totals (RS only for PF/PA, both for W-L)
            for field in ("wins","losses","ties","games"):
                rs_tot[field] += rs[field]
                pl_tot[field] += pl[field]
            rs_tot["pf_sum"]  = round(rs_tot["pf_sum"] + rs["pf_sum"],  2)
            rs_tot["pa_sum"]  = round(rs_tot["pa_sum"] + rs["pa_sum"],  2)

        row_totals[mid] = {
            "regular_season": _fmt_rs(rs_tot),
            "playoffs":       _fmt_pl(pl_tot),
            "combined_wins":  rs_tot["wins"]   + pl_tot["wins"],
            "combined_losses":rs_tot["losses"] + pl_tot["losses"],
            "combined_ties":  rs_tot["ties"]   + pl_tot["ties"],
        }

    # Manager list sorted by all-time wins desc for natural table ordering
    managers_sorted = sorted(
        all_ids,
        key=lambda mid: -(row_totals[mid]["combined_wins"]),
    )

    managers_meta = [
        {"manager_id": mid, "display_name": _display_name(mid, results)}
        for mid in managers_sorted
    ]

    return {
        "era":            era,
        "era_label":      era_def["label"],
        "era_years":      f"{era_def['start']}–present" if era_def['end'] == 9999 else f"{era_def['start']}–{era_def['end']}",
        "available_eras": {k: v["label"] for k, v in ERAS.items()},
        "managers":       managers_meta,
        "grid":           formatted_grid,
        "row_totals":     row_totals,
        "note":           "grid[row][col] = row manager's record vs col manager. Diagonal is null.",
    }

@router.get("/league/managers")
def league_managers():
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

@router.get("/league/seasons")
def league_seasons():
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


# ===========================================================================
# GET /fantasy/league/rules
# ===========================================================================

@router.get("/league/rules")
def league_rules():
    """
    Returns the most recent season's scoring rules and league settings.

    Pulls from rules.json — the latest year with populated stat_categories.
    Useful for displaying scoring settings in the app (how many points per
    passing yard, touchdown, reception etc.)

    Returns:
        year, draft_type, num_teams, uses_faab, faab_budget,
        playoff_teams, playoff_start_week, end_week, trade_deadline,
        roster_positions, stat_categories (with points_per_unit)
    """
    rules = _load("rules.json")
    if not rules:
        raise HTTPException(status_code=404, detail="rules.json not found.")

    rules_yr = _year_keyed(rules)
    if not rules_yr:
        raise HTTPException(status_code=404, detail="No season data in rules.json.")

    # Use most recent year that has stat_categories populated
    latest_yr = None
    latest    = None
    for yr, s in rules_yr.items():
        if s.get("stat_categories"):
            latest_yr = yr
            latest    = s
            break

    if not latest:
        latest_yr, latest = next(iter(rules_yr.items()))

    # Split stat_categories into scoring (has points_per_unit) and display-only
    all_cats  = latest.get("stat_categories", [])
    scoring   = [c for c in all_cats if c.get("points_per_unit") is not None]
    display   = [c for c in all_cats if c.get("points_per_unit") is None and c.get("enabled")]

    # Group scoring stats by position type for easier frontend rendering
    by_pos: dict = {}
    for c in scoring:
        pt = c.get("position_type") or "O"
        by_pos.setdefault(pt, []).append(c)

    return {
        "year":              int(latest_yr),
        "draft_type":        latest.get("draft_type"),
        "num_teams":         latest.get("num_teams"),
        "uses_faab":         latest.get("uses_faab"),
        "faab_budget":       latest.get("faab_budget"),
        "playoff_teams":     latest.get("playoff_teams"),
        "playoff_start_week":latest.get("playoff_start_week"),
        "end_week":          latest.get("end_week"),
        "trade_deadline":    latest.get("trade_deadline"),
        "roster_positions":  latest.get("roster_positions", []),
        "scoring_by_position_type": by_pos,
        "scoring_stats":     scoring,
        "display_only_stats":display,
        "total_scoring_stats":len(scoring),
    }


# ===========================================================================
# GET /fantasy/league/history
# ===========================================================================

@router.get("/league/history")
def league_history():
    """
    Full season-by-season history of the BlackGold fantasy league.

    For each completed season returns:
      - year, num_teams
      - champion        (rank 1 — display_name, manager_id, record, points_for)
      - last_place      (rank == num_teams)
      - best_record     (most wins; points_for as tiebreak)
      - punishment      (from punishment.json)
      - top_scorers     (top QB/RB/WR/TE by total season fantasy points)
                        NOTE: ranked among rostered players only (player_stats
                        covers only players who appeared on a league roster)
      - draft_round_1   (snake: pick + player + team per slot;
                         auction: each team's highest-cost pick)
      - draft_grades    (each pick's season total pts + position rank
                         e.g. WR10 = 10th-most points among rostered WRs)

    Seasons missing player_stats or drafts return those fields as null
    with a note explaining what's missing — partial data is always returned.

    Sorted newest → oldest.
    """
    results      = _load("results.json")
    punishment   = _load("punishment.json")
    drafts       = _load("drafts.json")
    player_stats = _load("player_stats.json")
    player_info  = _load("player_info.json")
    rosters      = _load("rosters.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    finished = _finished_seasons(_year_keyed(results))
    history  = []

    for yr, season in finished.items():

        # ── helpers ──────────────────────────────────────────────────────────
        managers   = season.get("managers", {})
        num_teams  = len(managers)

        def _mgr_entry(mid: str, m: dict) -> dict:
            """Build a manager summary from results.json manager dict."""
            rs = m.get("regular_season", {})
            po = m.get("playoff", {})
            # final_rank: playoff rank if available, else regular season rank
            final_rank = (
                po.get("rank") or po.get("seed") or
                rs.get("rank") or m.get("rank")
            )
            return {
                "manager_id":   mid,
                "display_name": m.get("display_name") or mid.title(),
                "team_name":    m.get("team_name"),
                "wins":         rs.get("wins"),
                "losses":       rs.get("losses"),
                "ties":         rs.get("ties", 0),
                "points_for":   rs.get("points_for"),
                "final_rank":   final_rank,
            }

        mgr_list = [(mid, m) for mid, m in managers.items()]

        # ── champion ─────────────────────────────────────────────────────────
        champion   = None
        last_place = None
        best_rec   = None

        # Sort by final_rank for champion / last place
        def _final_rank(item):
            mid, m = item
            rs = m.get("regular_season", {})
            po = m.get("playoff", {})
            return po.get("rank") or po.get("seed") or rs.get("rank") or 99

        rank_sorted = sorted(mgr_list, key=_final_rank)
        if rank_sorted:
            champion   = _mgr_entry(*rank_sorted[0])
            last_place = _mgr_entry(*rank_sorted[-1])

        # ── best regular-season record ────────────────────────────────────────
        def _rec_sort(item):
            mid, m = item
            rs = m.get("regular_season", {})
            return (-(rs.get("wins") or 0), -(rs.get("points_for") or 0))

        rec_sorted = sorted(mgr_list, key=_rec_sort)
        if rec_sorted:
            best_rec = _mgr_entry(*rec_sorted[0])

        # ── punishment ────────────────────────────────────────────────────────
        pun_entry   = punishment.get(str(yr), {})
        punishment_text = pun_entry.get("punishment") if isinstance(pun_entry, dict) else None

        # ── player_stats for this year ────────────────────────────────────────
        yr_stats   = player_stats.get(str(yr), {})
        yr_info    = (player_info.get(str(yr), {}) or {}).get("players", {})
        yr_rosters = rosters.get(str(yr), {})

        # Sum fantasy_points per player_key across all weeks
        player_season_pts: dict = {}   # player_key → total_pts
        if yr_stats:
            for wk_key, wk_data in yr_stats.items():
                if not isinstance(wk_data, dict):
                    continue
                for pk, pdata in wk_data.items():
                    if not isinstance(pdata, dict):
                        continue
                    fp = pdata.get("fantasy_points") or 0
                    try:
                        player_season_pts[pk] = player_season_pts.get(pk, 0) + float(fp)
                    except (TypeError, ValueError):
                        pass

        # Build position → sorted [(player_key, pts, name)] for ranking
        pos_groups: dict = {}
        for pk, pts in player_season_pts.items():
            if pts <= 0:
                continue
            pi = yr_info.get(pk, {})
            pos = pi.get("position") or ""
            # Normalise flex positions to primary
            primary = pos.split("/")[0].strip() if "/" in pos else pos
            if primary not in pos_groups:
                pos_groups[primary] = []
            pos_groups[primary].append({
                "player_key": pk,
                "name":       pi.get("name") or pk,
                "position":   primary,
                "total_pts":  round(pts, 2),
            })

        for pos in pos_groups:
            pos_groups[pos].sort(key=lambda x: -x["total_pts"])

        def _top_scorer(position: str) -> dict | None:
            """Top scorer at a position. Checks exact pos and common aliases."""
            for p in [position]:
                group = pos_groups.get(p, [])
                if group:
                    top = group[0]
                    return {
                        "player_key": top["player_key"],
                        "name":       top["name"],
                        "total_pts":  top["total_pts"],
                        "position":   position,
                    }
            return None

        # ── roster owner lookup ───────────────────────────────────────────────
        # Find who owned each player_key at season end (last available week)
        # Returns {player_key: {manager_id, display_name}}
        owner_map: dict = {}
        if yr_rosters:
            week_keys = sorted(
                [k for k in yr_rosters.keys() if k.startswith("week_")],
                key=lambda x: int(x.split("_")[1])
            )
            if week_keys:
                last_week = yr_rosters[week_keys[-1]]
                for mid, team in last_week.items():
                    if not isinstance(team, dict): continue
                    for slot in team.get("players", []):
                        pk = slot.get("player_key") if isinstance(slot, dict) else None
                        if pk:
                            owner_map[pk] = {
                                "manager_id":   mid,
                                "display_name": team.get("display_name") or mid.title(),
                            }

        def _with_owner(scorer: dict | None) -> dict | None:
            if not scorer: return None
            owner = owner_map.get(scorer["player_key"])
            return {**scorer, "owner": owner}

        top_scorers = None
        if yr_stats and yr_info:
            top_scorers = {
                "QB": _with_owner(_top_scorer("QB")),
                "RB": _with_owner(_top_scorer("RB")),
                "WR": _with_owner(_top_scorer("WR")),
                "TE": _with_owner(_top_scorer("TE")),
            }

        # ── draft key picks (consolidated round_1 + grades) ──────────────────
        yr_draft    = drafts.get(str(yr), {})
        draft_picks = yr_draft.get("picks", [])
        draft_type  = yr_draft.get("draft_type", "snake")

        draft_key_picks = None
        has_draft_data  = bool(draft_picks)
        has_stats_data  = bool(player_season_pts)

        if has_draft_data:
            # Identify the 10 key picks:
            # Snake → round 1 picks sorted by pick order
            # Auction → highest-cost pick per team sorted by cost desc
            if draft_type == "snake":
                key_picks = sorted(
                    [p for p in draft_picks if (p.get("round") or 0) == 1],
                    key=lambda x: x.get("overall_pick") or 99,
                )
            else:
                team_top: dict = {}
                for p in draft_picks:
                    mid  = p.get("manager_id") or ""
                    cost = p.get("cost") or 0
                    if not mid: continue
                    if mid not in team_top or cost > (team_top[mid].get("cost") or 0):
                        team_top[mid] = p
                key_picks = sorted(team_top.values(), key=lambda x: -(x.get("cost") or 0))

            graded = []
            for p in key_picks:
                pk       = p.get("player_key") or ""
                pts      = round(player_season_pts.get(pk, 0), 2) if has_stats_data else None
                pos_raw  = p.get("position") or (yr_info.get(pk, {}).get("position") or "")
                position = pos_raw.split("/")[0].strip() if "/" in pos_raw else pos_raw

                pos_rank  = None
                pos_label = None
                if pts is not None and pts > 0:
                    group = pos_groups.get(position, [])
                    for i, g in enumerate(group):
                        if g["player_key"] == pk:
                            pos_rank  = i + 1
                            pos_label = f"{position}{pos_rank}"
                            break

                entry_pick: dict = {
                    "manager_id":   p.get("manager_id"),
                    "display_name": p.get("display_name"),
                    "player_key":   pk or None,
                    "player_name":  p.get("player_name"),
                    "position":     position or None,
                    "nfl_team":     p.get("nfl_team"),
                    "season_pts":   pts,
                    "pos_rank":     pos_rank,
                    "pos_label":    pos_label,
                }
                # Snake picks have pick number; auction picks have cost
                if draft_type == "snake":
                    entry_pick["pick"] = p.get("overall_pick")
                else:
                    entry_pick["cost"] = p.get("cost")

                graded.append(entry_pick)

            draft_key_picks = {
                "type":  draft_type,
                "note":  ("Round 1 picks" if draft_type == "snake"
                          else "Highest-cost pick per team"),
                "stats_available": has_stats_data,
                "picks": graded,
            }

        # ── assemble ──────────────────────────────────────────────────────────
        entry = {
            "year":            int(yr),
            "num_teams":       num_teams,
            "champion":        champion,
            "last_place":      last_place,
            "best_record":     best_rec,
            "punishment":      punishment_text,
            "top_scorers":     top_scorers,
            "draft_key_picks": draft_key_picks,
            "_data_coverage": {
                "has_results":          True,
                "has_punishment":       punishment_text is not None,
                "has_player_stats":     has_stats_data,
                "has_player_info":      bool(yr_info),
                "has_rosters":          bool(yr_rosters),
                "has_draft":            has_draft_data,
                "draft_grades_available": draft_key_picks is not None and has_stats_data,
            },
        }
        history.append(entry)

    history.sort(key=lambda x: -x["year"])

    return {
        "total_seasons":      len(history),
        "seasons_with_grades":sum(1 for h in history if h.get("draft_key_picks") and h["draft_key_picks"].get("stats_available")),
        "seasons_with_stats": sum(1 for h in history if h["top_scorers"]),
        "history":            history,
    }


# ===========================================================================
# GET /fantasy/season/standings
# ===========================================================================

@router.get("/season/standings")
def season_standings(year: int = Query(default=None, description="Season year e.g. 2025. Omit for all seasons.")):
    """
    Regular season standings for one or all seasons.

    Per manager per season returns:
      - wins, losses, ties, rank
      - points_for (total + per-game average)
      - points_against (total + per-game average)
      - projected_points (total + per-game average — summed from matchups.json)

    Projected points are summed from weekly matchup data across regular season
    weeks only (is_playoffs=false). If matchups.json is unavailable for a year
    the projected fields return null.

    Query params:
      year=2025   → single season
      (omit)      → all finished seasons, newest first
    """
    results  = _load("results.json")
    matchups = _load("matchups.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    finished = _finished_seasons(_year_keyed(results))
    if not finished:
        raise HTTPException(status_code=404, detail="No finished seasons found.")

    target = {str(year): finished[str(year)]} if year else finished
    if year and str(year) not in finished:
        raise HTTPException(status_code=404, detail=f"Season {year} not found or not finished.")

    seasons_out = []

    for yr, season in target.items():
        managers      = season.get("managers", {})
        num_teams     = len(managers)

        # ── projected points from matchups.json ──────────────────────────────
        # Sum projected across all regular season weeks per manager
        proj_by_mgr: dict = {}   # manager_id → total projected pts
        yr_matchups = matchups.get(str(yr), {})
        playoff_start = yr_matchups.get("playoff_start") or 99

        for wk_entry in yr_matchups.get("weeks", []):
            if wk_entry.get("week", 99) >= playoff_start:
                continue   # skip playoff weeks
            for m in wk_entry.get("matchups", []):
                if m.get("is_playoffs"):
                    continue
                for team in m.get("teams", []):
                    mid  = team.get("manager_id") or ""
                    proj = team.get("projected") or 0
                    if mid:
                        proj_by_mgr[mid] = round(proj_by_mgr.get(mid, 0) + proj, 2)

        # ── build standings rows ──────────────────────────────────────────────
        rows = []
        for mid, m in managers.items():
            rs = m.get("regular_season", {})

            wins   = rs.get("wins")   or 0
            losses = rs.get("losses") or 0
            ties   = rs.get("ties")   or 0
            games  = wins + losses + (ties or 0)

            pf     = rs.get("points_for")     or 0
            pa     = rs.get("points_against") or 0
            proj   = proj_by_mgr.get(mid)

            # playoff_seed = regular season finish rank (1-10)
            # This is the stable ordering unaffected by consolation bracket results
            playoff_seed = rs.get("rank")

            rows.append({
                "playoff_seed":     playoff_seed,    # sort key — reg season rank
                "manager_id":       mid,
                "display_name":     m.get("display_name") or mid.title(),
                "team_name":        m.get("team_name"),
                "wins":             wins,
                "losses":           losses,
                "ties":             ties,
                "games_played":     games,
                "points_for":       round(pf, 2),
                "points_for_avg":   round(pf / games, 2) if games else None,
                "points_against":   round(pa, 2),
                "points_against_avg": round(pa / games, 2) if games else None,
                "projected_total":  round(proj, 2) if proj is not None else None,
                "projected_avg":    round(proj / games, 2) if (proj is not None and games) else None,
                "made_playoffs":    bool(playoff_seed and playoff_seed <= 4),
            })

        # Sort by regular season rank (playoff seed) — stable, unaffected by consolation
        rows.sort(key=lambda x: (x.get("playoff_seed") or 99))

        seasons_out.append({
            "year":              int(yr),
            "num_teams":         num_teams,
            "has_projected":     bool(proj_by_mgr),
            "standings":         rows,
        })

    seasons_out.sort(key=lambda x: -x["year"])

    if year:
        return seasons_out[0]

    return {
        "total_seasons": len(seasons_out),
        "seasons":       seasons_out,
    }


# ===========================================================================
# GET /fantasy/season/playoffs
# ===========================================================================

@router.get("/season/playoffs")
def season_playoffs(year: int = Query(default=None, description="Season year e.g. 2025. Omit for most recent finished season.")):
    """
    Full playoff picture for a season — bracket, results, and champion roster.

    Returns:
      bracket:
        - semifinal matchups (seed 1v4, 2v3) with points
        - championship matchup + 3rd place matchup
        - each matchup optionally expanded with per-player points

      champion_roster:
        - every player on the champion's roster during the last playoff week
        - playoff_pts per player (sum across all playoff weeks)
        - total_pts for the roster
        - sorted starters first then bench, by points desc within each group

    The expandable matchup UX works like this:
      Backend returns full player breakdown for EVERY matchup right now.
      Frontend starts all matchups collapsed (showing just team + score).
      Tapping a matchup card toggles expanded=true showing the player rows.
      Zero additional API calls needed — all data is already in the response.

    Playoff week detection: uses matchups.json is_playoffs flag.
    Seedings: from results.json regular_season.rank.
    """
    results      = _load("results.json")
    matchups_raw = _load("matchups.json")
    rosters      = _load("rosters.json")
    player_stats = _load("player_stats.json")
    player_info  = _load("player_info.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    finished = _finished_seasons(_year_keyed(results))
    if not finished:
        raise HTTPException(status_code=404, detail="No finished seasons found.")

    # Default to most recent finished season
    yr = str(year) if year else next(iter(finished))
    if yr not in finished:
        raise HTTPException(status_code=404, detail=f"Season {yr} not found or not finished.")

    season   = finished[yr]
    managers = season.get("managers", {})

    # ── seedings from regular season rank ────────────────────────────────────
    seed_map: dict = {}   # manager_id → seed (regular season rank)
    for mid, m in managers.items():
        rs = m.get("regular_season", {})
        seed = rs.get("rank")
        if seed:
            seed_map[mid] = seed

    def _team_info(mid: str) -> dict:
        m = managers.get(mid, {})
        return {
            "manager_id":   mid,
            "display_name": m.get("display_name") or mid.title(),
            "team_name":    m.get("team_name"),
            "seed":         seed_map.get(mid),
            "final_rank":   (m.get("playoff") or {}).get("rank") or seed_map.get(mid),
        }

    # ── playoff weeks from matchups.json ─────────────────────────────────────
    yr_matchups  = matchups_raw.get(yr, {})
    all_weeks    = yr_matchups.get("weeks", [])
    playoff_start = yr_matchups.get("playoff_start") or 99

    playoff_weeks = [
        w for w in all_weeks
        if w.get("week", 0) >= playoff_start
    ]
    playoff_week_nums = sorted(w["week"] for w in playoff_weeks)
    last_playoff_week = playoff_week_nums[-1] if playoff_week_nums else None

    # ── player stats for playoff weeks only ──────────────────────────────────
    yr_stats   = player_stats.get(yr, {})
    yr_info    = (player_info.get(yr, {}) or {}).get("players", {})

    playoff_pts: dict = {}  # player_key → total pts across playoff weeks
    for wk_num in playoff_week_nums:
        wk_data = yr_stats.get(f"week_{wk_num}", {})
        for pk, pd in wk_data.items():
            fp = float(pd.get("fantasy_points") or 0) if isinstance(pd, dict) else 0
            playoff_pts[pk] = round(playoff_pts.get(pk, 0) + fp, 2)

    # ── per-team roster breakdown for a given week ───────────────────────────
    def _team_players(mid: str, week_num: int) -> list:
        """Players + points for a manager in a specific week."""
        wk_key    = f"week_{week_num}"
        yr_roster = rosters.get(yr, {})
        wk_roster = yr_roster.get(wk_key, {})
        team_slots = wk_roster.get(mid, {}).get("players", [])
        if not team_slots:
            return []

        players_out = []
        for slot in team_slots:
            if not isinstance(slot, dict): continue
            pk  = slot.get("player_key") or ""
            pi  = yr_info.get(pk, {})
            wk_pts = float(
                (yr_stats.get(wk_key, {}).get(pk) or {}).get("fantasy_points") or 0
            ) if isinstance(yr_stats.get(wk_key, {}).get(pk), dict) else 0

            players_out.append({
                "player_key":        pk,
                "name":              pi.get("name") or pk,
                "position":          pi.get("position") or slot.get("selected_position"),
                "nfl_team":          pi.get("nfl_team"),
                "selected_position": slot.get("selected_position"),
                "is_starting":       slot.get("is_starting", False),
                "is_on_bench":       slot.get("is_on_bench", False),
                "is_on_ir":          slot.get("is_on_ir", False),
                "week_pts":          round(wk_pts, 2),
            })

        # Starters first (sorted by pts desc), then bench, then IR
        players_out.sort(key=lambda p: (
            0 if p["is_starting"] else (1 if p["is_on_bench"] else 2),
            -p["week_pts"],
        ))
        return players_out

    # ── build matchup objects ─────────────────────────────────────────────────
    def _build_matchup(m: dict, week_num: int) -> dict:
        teams = m.get("teams", [])
        teams_out = []
        for t in teams:
            mid      = t.get("manager_id") or ""
            ti       = _team_info(mid)
            players  = _team_players(mid, week_num)
            teams_out.append({
                **ti,
                "points":    t.get("points"),
                "projected": t.get("projected"),
                "is_winner": t.get("is_winner", False),
                "players":   players,   # full detail — frontend collapses by default
            })
        # Sort so winner appears first
        teams_out.sort(key=lambda t: 0 if t["is_winner"] else 1)
        return {
            "week":           week_num,
            "week_start":     m.get("week_start"),
            "week_end":       m.get("week_end"),
            "is_consolation": m.get("is_consolation", False),
            "winner_manager": m.get("winner_manager"),
            "teams":          teams_out,
        }

    # ── playoff teams (seeds 1-4 only) ───────────────────────────────────────
    playoff_manager_ids = {mid for mid, seed in seed_map.items() if seed <= 4}

    def _is_playoff_matchup(m: dict) -> bool:
        """True only if BOTH teams in the matchup are seeds 1-4."""
        teams = m.get("teams", [])
        return (
            m.get("is_playoffs", False)
            and not m.get("is_consolation", False)
            and all(t.get("manager_id") in playoff_manager_ids for t in teams)
        )

    # ── assemble bracket by week ──────────────────────────────────────────────
    bracket_weeks = []
    for wk_entry in sorted(playoff_weeks, key=lambda w: w["week"]):
        wk_num      = wk_entry["week"]
        wk_matchups = wk_entry.get("matchups", [])
        is_final_wk = (wk_num == last_playoff_week)

        championship = None
        third_place  = None
        semifinals   = []

        for m in wk_matchups:
            if not _is_playoff_matchup(m):
                continue   # skip consolation and non-seed-1-4 games entirely
            built = _build_matchup(m, wk_num)
            if is_final_wk:
                # Determine championship vs 3rd place by seedings of the teams
                team_seeds = [seed_map.get(t.get("manager_id") or "", 99) for t in m.get("teams", [])]
                min_seed   = min(team_seeds) if team_seeds else 99
                if min_seed <= 2:
                    championship = built
                else:
                    third_place  = built
            else:
                semifinals.append(built)

        # Sort semifinals so 1v4 comes before 2v3
        semifinals.sort(key=lambda s: min(
            seed_map.get(t.get("manager_id") or "", 99)
            for t in s.get("teams", [])
        ))

        bracket_weeks.append({
            "week":         wk_num,
            "is_final_week":is_final_wk,
            "championship": championship,
            "third_place":  third_place,
            "semifinals":   semifinals,
        })

    # ── champion roster (all playoff weeks combined) ──────────────────────────
    # Champion = seed 1 who won the championship (final_rank 1 from playoff obj,
    # falling back to the team with regular_season.rank=1 if playoff rank unavailable)
    champion_mid = None
    for mid, m in managers.items():
        po   = m.get("playoff", {})
        rs   = m.get("regular_season", {})
        rank = po.get("rank") or po.get("seed")
        # Prefer playoff.rank=1; fall back to regular_season.rank=1 only if no playoff data
        if rank == 1 and mid in playoff_manager_ids:
            champion_mid = mid
            break
    if not champion_mid:
        # Fallback: highest seed (seed 1) — will be wrong if they lost but better than nothing
        for mid, seed in seed_map.items():
            if seed == 1:
                champion_mid = mid
                break

    champion_roster = None
    if champion_mid and last_playoff_week:
        yr_roster  = rosters.get(yr, {})
        last_wk    = yr_roster.get(f"week_{last_playoff_week}", {})
        champ_team = last_wk.get(champion_mid, {})
        slots      = champ_team.get("players", [])

        roster_players = []
        for slot in slots:
            if not isinstance(slot, dict): continue
            pk  = slot.get("player_key") or ""
            pi  = yr_info.get(pk, {})
            pp  = round(playoff_pts.get(pk, 0), 2)
            roster_players.append({
                "player_key":        pk,
                "name":              pi.get("name") or pk,
                "position":          pi.get("position") or slot.get("selected_position"),
                "nfl_team":          pi.get("nfl_team"),
                "selected_position": slot.get("selected_position"),
                "is_starting":       slot.get("is_starting", False),
                "is_on_bench":       slot.get("is_on_bench", False),
                "playoff_pts":       pp,
            })

        roster_players.sort(key=lambda p: (
            0 if p["is_starting"] else 1,
            -p["playoff_pts"],
        ))

        champ_info = _team_info(champion_mid)
        champion_roster = {
            **champ_info,
            "total_playoff_pts": round(sum(p["playoff_pts"] for p in roster_players), 2),
            "playoff_weeks":     playoff_week_nums,
            "players":           roster_players,
            "note":              f"Roster from week {last_playoff_week}. playoff_pts = sum across all playoff weeks.",
        }

    return {
        "year":             int(yr),
        "playoff_weeks":    playoff_week_nums,
        "num_playoff_teams": len(playoff_manager_ids),
        "bracket":          bracket_weeks,
        "champion_roster":  champion_roster,
        "_data_coverage": {
            "has_matchups":    bool(yr_matchups),
            "has_rosters":     bool(rosters.get(yr)),
            "has_player_stats":bool(yr_stats),
            "has_player_info": bool(yr_info),
            "player_detail_available": bool(yr_stats and yr_info and rosters.get(yr)),
        },
    }


# ===========================================================================
# GET /fantasy/league/records
# ===========================================================================

@router.get("/league/records")
def league_records():
    """
    Hall of Records — all-time bests and worsts across 19 seasons.

    franchise_records: championships, last place, wins, playoff/finals appearances,
                       playoff wins
    scoring_records:   split by era (2012-2018 with K / 2019+ without K),
                       highest/lowest PF avg per season, highest/lowest single game,
                       highest/lowest PA avg per season
    draft_records:     highest auction cost, most frequent player+manager combo
    transaction_records: highest FAAB bid, most trades in a season, most moves in a season
    playoff_records:   highest PF avg in playoffs, highest single playoff game
    championship_roster_records: top 5 players most frequently on title teams
    position_records:  best single week + best season per position (QB/RB/WR/TE/K/DEF)
    """
    results      = _load("results.json")
    matchups_raw = _load("matchups.json")
    player_stats = _load("player_stats.json")
    player_info  = _load("player_info.json")
    drafts       = _load("drafts.json")
    transactions = _load("transactions.json")
    rosters      = _load("rosters.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    finished     = _finished_seasons(_year_keyed(results))
    all_managers = _all_manager_ids(results)

    SCORING_START_YEAR = 2012   # pre-2012 had broken scoring settings
    ERA1_END           = 2018   # 2007-2018: K included
    ERA2_START         = 2019   # 2019+: no K

    # ── per-manager accumulators ──────────────────────────────────────────────
    champ_count:   dict = {m: 0 for m in all_managers}
    last_count:    dict = {m: 0 for m in all_managers}
    win_total:     dict = {m: 0 for m in all_managers}
    playoff_count: dict = {m: 0 for m in all_managers}
    finals_count:  dict = {m: 0 for m in all_managers}
    playoff_wins:  dict = {m: 0 for m in all_managers}
    season_avgs:   dict = {m: [] for m in all_managers}
    season_pa:     dict = {m: [] for m in all_managers}

    for yr, season in finished.items():
        managers  = season.get("managers", {})
        num_teams = len(managers)

        for mid, m in managers.items():
            if mid not in champ_count:
                for d in [champ_count, last_count, win_total, playoff_count,
                          finals_count, playoff_wins]:
                    d[mid] = 0
                season_avgs[mid] = []
                season_pa[mid]   = []

            rs         = m.get("regular_season", {})
            po         = m.get("playoff", {})
            seed       = rs.get("rank") or 99
            final_rank = po.get("rank") or seed

            if final_rank == 1:             champ_count[mid]  += 1
            if final_rank == num_teams:     last_count[mid]   += 1
            win_total[mid]  += rs.get("wins") or 0
            if seed <= 4:                   playoff_count[mid] += 1

            wins  = rs.get("wins")   or 0
            losses= rs.get("losses") or 0
            ties  = rs.get("ties")   or 0
            games = wins + losses + ties
            pf    = rs.get("points_for")     or 0
            pa    = rs.get("points_against") or 0

            if games >= 10 and pf > 0 and int(yr) >= SCORING_START_YEAR:
                season_avgs[mid].append({"avg": round(pf/games,2), "year": int(yr),
                                         "total": round(pf,2), "games": games})
            if games >= 10 and pa > 0 and int(yr) >= SCORING_START_YEAR:
                season_pa[mid].append({"avg": round(pa/games,2), "year": int(yr),
                                       "total": round(pa,2), "games": games})

        # finals detection: championship game = last playoff week, both teams seed <= 2
        yr_mu         = matchups_raw.get(yr, {})
        all_wks       = yr_mu.get("weeks", [])
        playoff_start = yr_mu.get("playoff_start")
        if not playoff_start:
            yr_rules      = (_load("rules.json") or {}).get(yr, {})
            playoff_start = yr_rules.get("playoff_start_week")
        playoff_start = int(playoff_start) if playoff_start else 99

        playoff_wks = [w for w in all_wks if w.get("week", 0) >= playoff_start]
        seed_map_yr = {
            mid: (managers.get(mid,{}).get("regular_season") or {}).get("rank") or 99
            for mid in managers
        }

        if playoff_wks:
            last_wk = max(playoff_wks, key=lambda w: w["week"])
            for m in last_wk.get("matchups", []):
                teams      = m.get("teams", [])
                if len(teams) != 2: continue
                team_seeds = [seed_map_yr.get(t.get("manager_id") or "", 99) for t in teams]
                if max(team_seeds) <= 2:
                    for t in teams:
                        tmid = t.get("manager_id") or ""
                        if tmid and tmid in finals_count:
                            finals_count[tmid] += 1

            # playoff wins (seeds 1-4 games only)
            playoff_mids = {mid for mid, s in seed_map_yr.items() if s <= 4}
            for wk_entry in playoff_wks:
                for m in wk_entry.get("matchups", []):
                    teams = m.get("teams", [])
                    if not all(t.get("manager_id") in playoff_mids for t in teams):
                        continue
                    for t in teams:
                        if t.get("is_winner"):
                            wmid = t.get("manager_id") or ""
                            if wmid and wmid in playoff_wins:
                                playoff_wins[wmid] += 1

    # ── helper: holders ───────────────────────────────────────────────────────
    def _holders(count_dict: dict) -> dict:
        if not count_dict: return {"count": 0, "holders": []}
        max_val = max(count_dict.values())
        if max_val == 0: return {"count": 0, "holders": []}
        holders = sorted(
            [{"manager_id": mid, "display_name": _display_name(mid, results)}
             for mid, cnt in count_dict.items() if cnt == max_val],
            key=lambda x: x["display_name"]
        )
        return {"count": max_val, "holders": holders}

    franchise = {
        "most_championships":       _holders(champ_count),
        "most_last_place":          _holders(last_count),
        "most_wins":                _holders(win_total),
        "most_playoff_appearances": _holders(playoff_count),
        "most_finals_appearances":  _holders(finals_count),
        "most_playoff_wins":        _holders(playoff_wins),
    }

    # ── scoring records — era split ───────────────────────────────────────────
    def _season_avgs_flat(start_yr: int, end_yr: int) -> list:
        out = []
        for mid, avgs in season_avgs.items():
            dn = _display_name(mid, results)
            for e in avgs:
                if start_yr <= e["year"] <= end_yr:
                    out.append({"manager_id": mid, "display_name": dn, **e})
        return out

    def _season_pa_flat(start_yr: int, end_yr: int) -> list:
        out = []
        for mid, avgs in season_pa.items():
            dn = _display_name(mid, results)
            for e in avgs:
                if start_yr <= e["year"] <= end_yr:
                    out.append({"manager_id": mid, "display_name": dn, **e})
        return out

    def _score_block(start_yr: int, end_yr: int, all_scores: list) -> dict:
        avgs  = _season_avgs_flat(start_yr, end_yr)
        pas   = _season_pa_flat(start_yr, end_yr)
        era_scores = [s for s in all_scores if start_yr <= s["year"] <= end_yr]
        rs_scores  = [s for s in era_scores if not s["is_playoffs"] and s["points"] > 50]

        def _best(lst, key, reverse=True):
            if not lst: return None
            val = (max if reverse else min)(x[key] for x in lst)
            return [x for x in lst if x[key] == val]

        return {
            "highest_pf_season_avg": _best(avgs, "avg"),
            "lowest_pf_season_avg":  _best(avgs, "avg", reverse=False),
            "highest_pa_season_avg": _best(pas,  "avg"),
            "lowest_pa_season_avg":  _best(pas,  "avg", reverse=False),
            "highest_single_game":   _best(era_scores, "points"),
            "lowest_single_game":    _best(rs_scores,  "points", reverse=False),
        }

    # Build flat scores list (all seasons, 2012+)
    all_scores_flat: list = []
    for yr, yr_mu in matchups_raw.items():
        if yr not in finished or int(yr) < SCORING_START_YEAR:
            continue
        ps = yr_mu.get("playoff_start") or 99
        for wk_entry in yr_mu.get("weeks", []):
            wk_num = wk_entry.get("week", 0)
            is_po  = wk_num >= ps
            for m in wk_entry.get("matchups", []):
                for t in m.get("teams", []):
                    try: pts = float(t.get("points") or 0)
                    except: continue
                    if pts <= 0: continue
                    all_scores_flat.append({
                        "manager_id":   t.get("manager_id"),
                        "display_name": t.get("display_name"),
                        "team_name":    t.get("team_name"),
                        "year":         int(yr),
                        "week":         wk_num,
                        "points":       round(pts, 2),
                        "is_playoffs":  is_po,
                    })

    scoring_records = {
        "era_with_kicker_2012_2018":  _score_block(SCORING_START_YEAR, ERA1_END, all_scores_flat),
        "era_without_kicker_2019_present": _score_block(ERA2_START, 9999, all_scores_flat),
    }

    # ── draft records ─────────────────────────────────────────────────────────
    highest_auction_cost = None
    draft_combos: dict   = {}   # (manager_id, player_key) → {count, player_name, display_name, years}

    for yr, yr_draft in drafts.items():
        if yr not in finished: continue
        picks      = yr_draft.get("picks", [])
        draft_type = yr_draft.get("draft_type", "snake")

        for p in picks:
            pk  = p.get("player_key") or ""
            mid = p.get("manager_id") or ""
            pos = p.get("position") or ""

            # Skip DEF and K for combo tracking
            if pos in ("DEF", "D/ST", "K") or pk.startswith("461.p.100"):
                continue

            # Highest auction cost
            if draft_type == "auction":
                cost = p.get("cost")
                if cost is not None:
                    try: cost = int(cost)
                    except: cost = None
                if cost:
                    if highest_auction_cost is None or cost > highest_auction_cost["cost"]:
                        highest_auction_cost = {
                            "manager_id":   mid,
                            "display_name": p.get("display_name") or _display_name(mid, results),
                            "player_key":   pk,
                            "player_name":  p.get("player_name"),
                            "position":     pos,
                            "nfl_team":     p.get("nfl_team"),
                            "cost":         cost,
                            "year":         int(yr),
                        }

            # Draft combos
            if pk and mid:
                key = (mid, pk)
                if key not in draft_combos:
                    draft_combos[key] = {
                        "manager_id":   mid,
                        "display_name": p.get("display_name") or _display_name(mid, results),
                        "player_key":   pk,
                        "player_name":  p.get("player_name"),
                        "position":     pos,
                        "nfl_team":     p.get("nfl_team"),
                        "count":        0,
                        "years":        [],
                    }
                draft_combos[key]["count"] += 1
                draft_combos[key]["years"].append(int(yr))

    # Top 5 most frequent combos (min 2 times drafted)
    top_combos = sorted(
        [v for v in draft_combos.values() if v["count"] >= 2],
        key=lambda x: (-x["count"], x["player_name"] or "")
    )[:5]

    draft_records = {
        "highest_auction_cost":          highest_auction_cost,
        "most_frequent_player_manager":  top_combos,
    }

    # ── transaction records ───────────────────────────────────────────────────
    highest_faab:   dict | None = None
    most_trades_season:  dict | None = None
    most_moves_season:   dict | None = None

    for yr, yr_tx in transactions.items():
        if yr not in finished: continue
        trades = yr_tx.get("trades", [])
        moves  = yr_tx.get("moves",  [])

        # FAAB bids
        for move in moves:
            for added in move.get("added", []):
                bid = added.get("waiver_bid")
                if bid is None: continue
                try: bid = int(bid)
                except: continue
                if bid <= 0: continue
                if highest_faab is None or bid > highest_faab["bid"]:
                    mid = move.get("manager_id") or ""
                    highest_faab = {
                        "manager_id":   mid,
                        "display_name": _display_name(mid, results),
                        "player_key":   added.get("player_key"),
                        "player_name":  added.get("name"),
                        "position":     added.get("position"),
                        "bid":          bid,
                        "year":         int(yr),
                    }

        # Trades per team this season
        trade_counts: dict = {}
        for trade in trades:
            for role in ("trader_manager", "tradee_manager"):
                mid = trade.get(role) or ""
                if mid:
                    trade_counts[mid] = trade_counts.get(mid, 0) + 1
        if trade_counts:
            max_trades = max(trade_counts.values())
            if most_trades_season is None or max_trades > most_trades_season["trades"]:
                holders = [
                    {"manager_id": mid, "display_name": _display_name(mid, results)}
                    for mid, cnt in trade_counts.items() if cnt == max_trades
                ]
                most_trades_season = {
                    "trades":  max_trades,
                    "year":    int(yr),
                    "holders": holders,
                }

        # Moves per team this season
        move_counts: dict = {}
        for move in moves:
            mid = move.get("manager_id") or ""
            if mid:
                move_counts[mid] = move_counts.get(mid, 0) + 1
        if move_counts:
            max_moves = max(move_counts.values())
            if most_moves_season is None or max_moves > most_moves_season["moves"]:
                holders = [
                    {"manager_id": mid, "display_name": _display_name(mid, results)}
                    for mid, cnt in move_counts.items() if cnt == max_moves
                ]
                most_moves_season = {
                    "moves":   max_moves,
                    "year":    int(yr),
                    "holders": holders,
                }

    transaction_records = {
        "highest_faab_bid":        highest_faab,
        "most_trades_in_a_season": most_trades_season,
        "most_moves_in_a_season":  most_moves_season,
    }

    # ── playoff records ───────────────────────────────────────────────────────
    playoff_scores_flat: list = []
    playoff_team_pts:    dict = {}  # (manager_id, yr) → {pts, games}

    for yr, yr_mu in matchups_raw.items():
        if yr not in finished: continue
        ps = yr_mu.get("playoff_start")
        if not ps:
            yr_rules = (_load("rules.json") or {}).get(yr, {})
            ps = yr_rules.get("playoff_start_week")
        ps = int(ps) if ps else 99

        yr_results  = finished[yr]
        yr_managers = yr_results.get("managers", {})
        seed_map_yr = {
            mid: (yr_managers.get(mid,{}).get("regular_season") or {}).get("rank") or 99
            for mid in yr_managers
        }
        playoff_mids = {mid for mid, s in seed_map_yr.items() if s <= 4}

        for wk_entry in yr_mu.get("weeks", []):
            wk_num = wk_entry.get("week", 0)
            if wk_num < ps: continue
            for m in wk_entry.get("matchups", []):
                teams = m.get("teams", [])
                if not all(t.get("manager_id") in playoff_mids for t in teams):
                    continue
                for t in teams:
                    try: pts = float(t.get("points") or 0)
                    except: continue
                    if pts <= 0: continue
                    mid = t.get("manager_id") or ""
                    playoff_scores_flat.append({
                        "manager_id":   mid,
                        "display_name": t.get("display_name"),
                        "team_name":    t.get("team_name"),
                        "year":         int(yr),
                        "week":         wk_num,
                        "points":       round(pts, 2),
                    })
                    key = (mid, yr)
                    if key not in playoff_team_pts:
                        playoff_team_pts[key] = {"pts": 0.0, "games": 0,
                                                  "manager_id": mid,
                                                  "display_name": t.get("display_name"),
                                                  "year": int(yr)}
                    playoff_team_pts[key]["pts"]   += pts
                    playoff_team_pts[key]["games"]  += 1

    # Highest single game in playoffs
    highest_playoff_game = None
    if playoff_scores_flat:
        max_pts = max(x["points"] for x in playoff_scores_flat)
        highest_playoff_game = [x for x in playoff_scores_flat if x["points"] == max_pts]

    # Highest PF avg in a single playoff run
    highest_playoff_avg = None
    if playoff_team_pts:
        playoff_avgs = [
            {**v, "avg": round(v["pts"] / v["games"], 2)}
            for v in playoff_team_pts.values()
            if v["games"] >= 2   # must have played at least 2 playoff games
        ]
        if playoff_avgs:
            max_avg = max(x["avg"] for x in playoff_avgs)
            highest_playoff_avg = [x for x in playoff_avgs if x["avg"] == max_avg]

    playoff_records = {
        "highest_pf_avg_playoff_run": highest_playoff_avg,
        "highest_single_playoff_game": highest_playoff_game,
    }

    # ── championship roster records ───────────────────────────────────────────
    champ_roster_counts: dict = {}   # player_key → {name, position, nfl_team, count, years}

    for yr, season in finished.items():
        managers = season.get("managers", {})

        # Find champion manager_id
        champion_mid = None
        for mid, m in managers.items():
            po = m.get("playoff", {})
            rs = m.get("regular_season", {})
            if (po.get("rank") or rs.get("rank")) == 1:
                champion_mid = mid
                break

        if not champion_mid: continue

        # Get their roster from last available playoff week
        yr_roster = rosters.get(yr, {})
        if not yr_roster: continue

        ps = matchups_raw.get(yr, {}).get("playoff_start")
        if not ps:
            yr_rules = (_load("rules.json") or {}).get(yr, {})
            ps = yr_rules.get("playoff_start_week")
        ps = int(ps) if ps else 99

        playoff_wk_keys = sorted(
            [k for k in yr_roster.get(champion_mid, {}).keys()
             if k.startswith("week_") and int(k.split("_")[1]) >= ps],
            key=lambda x: int(x.split("_")[1])
        ) if isinstance(yr_roster.get(champion_mid), dict) else []

        # Use last playoff week roster if available, else scan all weeks
        champ_week = None
        if playoff_wk_keys:
            champ_week = playoff_wk_keys[-1]
        else:
            all_wk_keys = sorted(
                [k for k in yr_roster.keys() if k.startswith("week_")],
                key=lambda x: int(x.split("_")[1])
            )
            if all_wk_keys:
                champ_week = all_wk_keys[-1]

        if not champ_week: continue

        # yr_roster is structured as {week_key: {manager_id: {players: [...]}}}
        week_data  = yr_roster.get(champ_week, {})
        team_data  = week_data.get(champion_mid, {})
        slots      = team_data.get("players", [])
        yr_info    = (player_info.get(yr, {}) or {}).get("players", {})

        for slot in slots:
            if not isinstance(slot, dict): continue
            pk  = slot.get("player_key") or ""
            if not pk: continue
            pos = slot.get("selected_position") or ""
            # Skip bench, IR, DEF, K for this record
            if pos in ("BN", "IR", "IR+", "K", "DEF", "D/ST"): continue
            pi  = yr_info.get(pk, {})
            name = pi.get("name") or pk
            position = pi.get("position") or pos

            if pk not in champ_roster_counts:
                champ_roster_counts[pk] = {
                    "player_key": pk,
                    "name":       name,
                    "position":   position,
                    "nfl_team":   pi.get("nfl_team"),
                    "count":      0,
                    "years":      [],
                }
            champ_roster_counts[pk]["count"] += 1
            champ_roster_counts[pk]["years"].append(int(yr))

    top_champ_players = sorted(
        champ_roster_counts.values(),
        key=lambda x: (-x["count"], x["name"])
    )[:5]

    championship_roster_records = {
        "top_5_championship_players": top_champ_players,
        "note": "Starters only (excludes BN/IR/K/DEF). Limited to seasons where rosters.json is available.",
    }

    # ── position records ──────────────────────────────────────────────────────
    pos_records: dict = {}
    pos_season:  dict = {}
    years_with_stats: list = []

    for yr, yr_stats in player_stats.items():
        if yr not in finished or not yr_stats: continue
        years_with_stats.append(int(yr))
        yr_info   = (player_info.get(yr, {}) or {}).get("players", {})
        ps        = matchups_raw.get(yr, {}).get("playoff_start") or 99
        player_season_totals: dict = {}

        for wk_key in sorted([k for k in yr_stats if k.startswith("week_")],
                              key=lambda x: int(x.split("_")[1])):
            wk_num = int(wk_key.split("_")[1])
            rs_only = wk_num < ps
            for pk, pd in yr_stats[wk_key].items():
                if not isinstance(pd, dict): continue
                try: fp = float(pd.get("fantasy_points") or 0)
                except: continue
                if fp <= 0: continue
                pi      = yr_info.get(pk, {})
                pos_raw = pi.get("position") or ""
                pos     = pos_raw.split("/")[0].strip() if "/" in pos_raw else pos_raw
                if not pos: continue
                if pos in ("DEF", "D/ST"): pos = "DEF"
                name = pi.get("name") or pk

                if rs_only:
                    cur = pos_records.get(pos)
                    if cur is None or fp > cur["points"]:
                        pos_records[pos] = {"player_key": pk, "name": name,
                                            "position": pos, "nfl_team": pi.get("nfl_team"),
                                            "year": int(yr), "week": wk_num,
                                            "points": round(fp, 2)}
                    if pk not in player_season_totals:
                        player_season_totals[pk] = {"pts": 0.0, "weeks": 0,
                                                     "pos": pos, "name": name,
                                                     "nfl_team": pi.get("nfl_team")}
                    player_season_totals[pk]["pts"]   += fp
                    player_season_totals[pk]["weeks"]  += 1

        for pk, totals in player_season_totals.items():
            pos  = totals["pos"]
            pts  = round(totals["pts"], 2)
            wks  = totals["weeks"]
            avg  = round(pts / wks, 2) if wks else 0
            cur  = pos_season.get(pos)
            if cur is None or pts > cur["season_total"]:
                pos_season[pos] = {"player_key": pk, "name": totals["name"],
                                   "position": pos, "nfl_team": totals["nfl_team"],
                                   "year": int(yr), "season_total": pts,
                                   "weeks_played": wks, "season_avg": avg}

    pos_order = ["QB", "RB", "WR", "TE", "K", "DEF"]
    position_records = {
        pos: {"best_week": pos_records.get(pos), "best_season": pos_season.get(pos)}
        for pos in pos_order
    }

    return {
        "franchise_records":           franchise,
        "scoring_records":             scoring_records,
        "draft_records":               draft_records,
        "transaction_records":         transaction_records,
        "playoff_records":             playoff_records,
        "championship_roster_records": championship_roster_records,
        "position_records":            position_records,
        "_data_coverage": {
            "total_seasons":              len(finished),
            "scoring_records_eras":       {
                "era_with_kicker":    f"{SCORING_START_YEAR}–{ERA1_END}",
                "era_without_kicker": f"{ERA2_START}–present",
            },
            "seasons_in_player_stats":    len(years_with_stats),
            "player_stats_years":         sorted(years_with_stats, reverse=True),
            "championship_roster_seasons":sorted(
                [int(yr) for yr in rosters if yr in finished], reverse=True
            ),
            "notes": [
                f"scoring_records restricted to {SCORING_START_YEAR}+ (broken early scoring)",
                "position_records only covers seasons where player_stats.json is available",
                "championship_roster_records limited to seasons where rosters.json is available",
                "position season averages exclude bye weeks (only weeks fp > 0 counted)",
            ],
        },
    }