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
from routes.fantasy.league import PAYOUT_POSITION_ROTATION, get_payout_position
import os, json

router = APIRouter(prefix="/fantasy", tags=["Fantasy Views"])


# ---------------------------------------------------------------------------
# Era definitions — used by /matchups toggle
# ---------------------------------------------------------------------------
ERAS = {
    "all_time":    {"label": "Overall",     "start": 2007, "end": 9999},
    "darkness":    {"label": "Raphi Era",   "start": 2007, "end": 2011},
    "sam_era":     {"label": "Sam Era",     "start": 2009, "end": 2018},
    "frank_era":   {"label": "Frank Era",   "start": 2012, "end": 9999},
    "jordan_era":  {"label": "Jordan Era",  "start": 2019, "end": 9999},
    "auction_era": {"label": "Auction Era", "start": 2023, "end": 9999},
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
    # Unwrap /download endpoint wrapper: {"total_seasons":N, "years":[...], "data":{...}}
    # Detect wrapper by: has "data" key AND no top-level digit keys
    if isinstance(raw, dict) and "data" in raw and not any(str(k).isdigit() for k in raw):
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

    # ── position breakdown averages ──────────────────────────────────────────
    # For each position: avg points for name1 vs name2 across all RS matchups
    # where player breakdown is available
    pos_order   = ["QB","RB","WR","TE","K","DEF"]
    pos_pts1:   dict = {p: [] for p in pos_order}
    pos_pts2:   dict = {p: [] for p in pos_order}

    for m in all_matchups:
        if m.get("is_playoffs"): continue
        bd = m.get("player_breakdown")
        if not bd: continue
        for pos in pos_order:
            # Sum starter points at each position for each manager
            def _pos_pts(slots, pos_key):
                if not slots: return None
                starters = [s for s in slots if s.get("is_starting") and
                            (s.get("selected_position") == pos_key or
                             s.get("position","").startswith(pos_key))]
                return round(sum(s.get("week_pts", 0) for s in starters), 2) if starters else None

            p1 = _pos_pts(bd.get(name1), pos)
            p2 = _pos_pts(bd.get(name2), pos)
            if p1 is not None: pos_pts1[pos].append(p1)
            if p2 is not None: pos_pts2[pos].append(p2)

    avg_pf_by_position = {}
    for pos in pos_order:
        avg1 = round(sum(pos_pts1[pos]) / len(pos_pts1[pos]), 2) if pos_pts1[pos] else None
        avg2 = round(sum(pos_pts2[pos]) / len(pos_pts2[pos]), 2) if pos_pts2[pos] else None
        diff = round(avg1 - avg2, 2) if (avg1 is not None and avg2 is not None) else None
        avg_pf_by_position[pos] = {
            name1: avg1,
            name2: avg2,
            "diff": diff,
            "advantage": name1 if (diff and diff > 0) else (name2 if (diff and diff < 0) else "even"),
        }

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
        "avg_pf_by_position": avg_pf_by_position,
        "all_matchups":   all_matchups,
        "_data_coverage": {
            "player_breakdown_note": "player_breakdown included per matchup when rosters.json + player_stats.json available.",
            "position_breakdown_note": "avg_pf_by_position only covers matchups where player_breakdown is available (regular season only).",
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

    # ── payout schedule for current/next season ──────────────────────────────
    # Prize structure — league constants (2023 auction era onward)
    ENTRY_FEE         = 200   # $ per member per season
    NUM_TEAMS         = latest.get("num_teams") or 10
    TOTAL_POT         = ENTRY_FEE * NUM_TEAMS   # $2000

    # Season prizes
    PRIZE_CHAMPION    = 700
    PRIZE_2ND         = 200
    PRIZE_3RD         = 100
    PRIZE_RS_1SEED    = 200   # regular season #1 seed
    PRIZE_RS_HIGHPTS  = 200   # regular season highest total points

    # Weekly prizes ($40/week × 15 regular season weeks = $600)
    WEEKLY_POS_POT    = 20    # $ to highest starter at rotating position
    WEEKLY_TOTAL_POT  = 20    # $ to team with highest total points
    WEEKLY_REG_WEEKS  = 15    # regular season weeks

    season_prizes_total = PRIZE_CHAMPION + PRIZE_2ND + PRIZE_3RD + PRIZE_RS_1SEED + PRIZE_RS_HIGHPTS
    weekly_prizes_total = (WEEKLY_POS_POT + WEEKLY_TOTAL_POT) * WEEKLY_REG_WEEKS

    # Build weekly payout schedule for the current/latest season
    end_wk        = latest.get("end_week") or 17
    playoff_start = latest.get("playoff_start_week") or 16
    yr_int        = int(latest_yr)

    weekly_schedule = []
    for wk in range(1, end_wk + 1):
        is_po = wk >= playoff_start
        pos   = get_payout_position(yr_int, wk) if not is_po else None
        entry: dict = {
            "week":       wk,
            "is_playoffs":is_po,
        }
        if is_po:
            entry["note"] = "Playoff week — no weekly payout"
        else:
            entry["position_payout"]  = pos
            entry["position_pot"]     = WEEKLY_POS_POT
            entry["total_points_pot"] = WEEKLY_TOTAL_POT
            entry["total_pot"]        = WEEKLY_POS_POT + WEEKLY_TOTAL_POT
            entry["note"]             = f"${WEEKLY_POS_POT} to highest {pos} starter · ${WEEKLY_TOTAL_POT} to highest team total"
        weekly_schedule.append(entry)

    return {
        "year":              int(latest_yr),
        "draft_type":        latest.get("draft_type"),
        "num_teams":         NUM_TEAMS,
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
        "payout_rules": {
            "entry_fee":    ENTRY_FEE,
            "total_pot":    TOTAL_POT,
            "pot_breakdown": {
                "season_prizes":  season_prizes_total,
                "weekly_prizes":  weekly_prizes_total,
                "total_accounted":season_prizes_total + weekly_prizes_total,
            },
            "season_prizes": {
                "champion":                  PRIZE_CHAMPION,
                "2nd_place":                 PRIZE_2ND,
                "3rd_place":                 PRIZE_3RD,
                "regular_season_1st_seed":   PRIZE_RS_1SEED,
                "regular_season_high_points":PRIZE_RS_HIGHPTS,
                "note": "Regular season prizes awarded at end of regular season. Playoff prizes after championship.",
            },
            "weekly_prizes": {
                "position_high_score":  WEEKLY_POS_POT,
                "total_high_score":     WEEKLY_TOTAL_POT,
                "total_per_week":       WEEKLY_POS_POT + WEEKLY_TOTAL_POT,
                "regular_season_weeks": WEEKLY_REG_WEEKS,
                "total_weekly_pot":     weekly_prizes_total,
                "note": "Ties split pot evenly. Position rotates each week per PAYOUT_POSITION_ROTATION (2023+).",
            },
            "weekly_schedule":        weekly_schedule,
            "position_rotation_note": "Randomized 5-position cycle per season (QB/WR/RB/TE/DEF). Seed=42, covers 2023-2062.",
        },
    }


# ===========================================================================
# GET /fantasy/league/history
# ===========================================================================

@router.get("/league/history")
def league_history():
    """
    Full season-by-season history of the BlackGold fantasy league.

    For each completed season returns:
      - champion, last_place, best_record, best_pf_avg
      - punishment
      - top_scorers (QB/RB/WR/TE): total pts, avg pts, owner, draft context
      - draft_key_picks: draft_rank (order drafted at position) +
                         pos_label (end-of-season points rank at position)
      - most_rostered_nfl_team: NFL team most frequently on league rosters

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

        managers  = season.get("managers", {})
        num_teams = len(managers)
        mgr_list  = [(mid, m) for mid, m in managers.items()]

        # ── manager entry helper ──────────────────────────────────────────────
        def _mgr_entry(mid: str, m: dict) -> dict:
            rs = m.get("regular_season", {})
            po = m.get("playoffs", {}) or m.get("playoff", {})
            return {
                "manager_id":   mid,
                "display_name": m.get("display_name") or mid.title(),
                "team_name":    m.get("team_name"),
                "wins":         rs.get("wins"),
                "losses":       rs.get("losses"),
                "ties":         rs.get("ties", 0),
                "points_for":   rs.get("points_for"),
                "avg_points_for": rs.get("avg_points_for"),
            }

        # ── champion — use playoffs.finish == 1 ──────────────────────────────
        champion   = None
        last_place = None
        for mid, m in mgr_list:
            po = m.get("playoffs", {}) or m.get("playoff", {})
            rs = m.get("regular_season", {})
            finish = po.get("finish") if po.get("made_playoffs") else None
            if finish == 1:
                champion = _mgr_entry(mid, m)
            if finish == 3 or (not champion and rs.get("rank") == num_teams):
                pass  # third place not last place

        # last place = lowest regular season rank among non-playoff teams
        non_playoff = [(mid, m) for mid, m in mgr_list
                       if not (m.get("playoffs") or m.get("playoff", {})).get("made_playoffs")]
        if non_playoff:
            last_mid, last_m = max(non_playoff,
                key=lambda x: x[1].get("regular_season", {}).get("rank") or 0)
            last_place = _mgr_entry(last_mid, last_m)
        elif mgr_list:
            # fallback: sort by regular_season.rank descending
            sorted_by_rank = sorted(mgr_list,
                key=lambda x: x[1].get("regular_season", {}).get("rank") or 0,
                reverse=True)
            last_place = _mgr_entry(*sorted_by_rank[0])

        # ── best regular-season record ────────────────────────────────────────
        rec_sorted = sorted(mgr_list,
            key=lambda x: (-(x[1].get("regular_season", {}).get("wins") or 0),
                           -(x[1].get("regular_season", {}).get("points_for") or 0)))
        best_rec = _mgr_entry(*rec_sorted[0]) if rec_sorted else None

        # ── top PF average ────────────────────────────────────────────────────
        avg_sorted = sorted(mgr_list,
            key=lambda x: -(x[1].get("regular_season", {}).get("avg_points_for") or 0))
        best_pf_avg = _mgr_entry(*avg_sorted[0]) if avg_sorted else None

        # ── punishment ────────────────────────────────────────────────────────
        pun_entry       = punishment.get(str(yr), {})
        punishment_text = pun_entry.get("punishment") if isinstance(pun_entry, dict) else None

        # ── player stats aggregation ──────────────────────────────────────────
        yr_stats   = player_stats.get(str(yr), {})
        yr_info    = (player_info.get(str(yr), {}) or {}).get("players", {})
        yr_rosters = rosters.get(str(yr), {})
        yr_draft   = drafts.get(str(yr), {})
        draft_picks= yr_draft.get("picks", [])
        draft_type = yr_draft.get("draft_type", "snake")

        # Sum fantasy_points per player across ALL weeks (regular season + playoffs)
        player_season_pts: dict = {}
        if yr_stats:
            for wk_key, wk_data in yr_stats.items():
                if not isinstance(wk_data, dict): continue
                for pk, pdata in wk_data.items():
                    if not isinstance(pdata, dict): continue
                    fp = pdata.get("fantasy_points") or 0
                    try:
                        player_season_pts[pk] = player_season_pts.get(pk, 0) + float(fp)
                    except (TypeError, ValueError):
                        pass

        # Position groups sorted by points — for end-of-season ranking
        pos_groups: dict = {}
        for pk, pts in player_season_pts.items():
            if pts <= 0: continue
            pi      = yr_info.get(pk, {})
            pos_raw = pi.get("position") or ""
            primary = pos_raw.split("/")[0].strip() if "/" in pos_raw else pos_raw
            if not primary: continue
            pos_groups.setdefault(primary, []).append({
                "player_key": pk,
                "name":       pi.get("name") or pk,
                "position":   primary,
                "total_pts":  round(pts, 2),
            })
        for pos in pos_groups:
            pos_groups[pos].sort(key=lambda x: -x["total_pts"])

        # Draft position rank by position — "how many QBs were taken before this one"
        # e.g. if this player was the 3rd QB drafted overall → draft_rank = QB3
        draft_pos_rank: dict = {}   # player_key → draft_rank label
        pos_draft_counter: dict = {}  # position → count drafted so far
        for p in sorted(draft_picks, key=lambda x: x.get("overall_pick") or 999):
            pk      = p.get("player_key") or ""
            pos_raw = p.get("position") or (yr_info.get(pk, {}).get("position") or "")
            pos     = pos_raw.split("/")[0].strip() if "/" in pos_raw else pos_raw
            if not pos or not pk: continue
            pos_draft_counter[pos] = pos_draft_counter.get(pos, 0) + 1
            draft_pos_rank[pk] = f"{pos}{pos_draft_counter[pos]}"

        # ── owner map (last available week) ──────────────────────────────────
        owner_map: dict = {}
        if yr_rosters:
            wk_keys = sorted([k for k in yr_rosters.keys() if k.startswith("week_")],
                             key=lambda x: int(x.split("_")[1]))
            if wk_keys:
                last_wk = yr_rosters[wk_keys[-1]]
                for mid, team in last_wk.items():
                    if not isinstance(team, dict): continue
                    for slot in team.get("players", []):
                        pk = slot.get("player_key") if isinstance(slot, dict) else None
                        if pk:
                            owner_map[pk] = {
                                "manager_id":   mid,
                                "display_name": team.get("display_name") or mid.title(),
                            }

        # ── draft context lookup: pick# or cost for a player_key ─────────────
        draft_context: dict = {}   # player_key → {pick or cost}
        for p in draft_picks:
            pk = p.get("player_key") or ""
            if not pk: continue
            if draft_type == "snake":
                draft_context[pk] = {"pick": p.get("overall_pick"), "round": p.get("round")}
            else:
                draft_context[pk] = {"cost": p.get("cost")}

        # ── top scorers per position with draft context ───────────────────────
        def _top_scorer_full(position: str) -> dict | None:
            group = pos_groups.get(position, [])
            if not group: return None
            top   = group[0]
            pk    = top["player_key"]
            pi    = yr_info.get(pk, {})
            owner = owner_map.get(pk)
            dc    = draft_context.get(pk, {})
            games = num_teams  # approximate — could refine with actual weeks played
            return {
                "player_key":   pk,
                "name":         top["name"],
                "position":     position,
                "nfl_team":     pi.get("nfl_team"),
                "total_pts":    top["total_pts"],
                "owner":        owner,
                "draft_context":dc,   # {pick, round} snake or {cost} auction
            }

        has_stats_data = bool(player_season_pts)
        top_scorers = None
        if has_stats_data and yr_info:
            top_scorers = {
                "QB": _top_scorer_full("QB"),
                "RB": _top_scorer_full("RB"),
                "WR": _top_scorer_full("WR"),
                "TE": _top_scorer_full("TE"),
            }

        # ── draft key picks with both draft_rank and pos_label ───────────────
        draft_key_picks = None
        has_draft_data  = bool(draft_picks)

        if has_draft_data:
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

                # End-of-season rank by points (pos_label)
                pts_rank  = None
                pts_label = None
                if pts is not None and pts > 0:
                    for i, g in enumerate(pos_groups.get(position, [])):
                        if g["player_key"] == pk:
                            pts_rank  = i + 1
                            pts_label = f"{position}{pts_rank}"
                            break

                # Draft rank by position (draft_label)
                draft_label = draft_pos_rank.get(pk)

                entry_pick: dict = {
                    "manager_id":   p.get("manager_id"),
                    "display_name": p.get("display_name"),
                    "player_key":   pk or None,
                    "player_name":  p.get("player_name"),
                    "position":     position or None,
                    "nfl_team":     p.get("nfl_team"),
                    "season_pts":   pts,
                    "draft_label":  draft_label,  # QB3 = 3rd QB taken in draft
                    "pts_label":    pts_label,    # QB3 = 3rd most pts among QBs
                }
                if draft_type == "snake":
                    entry_pick["pick"] = p.get("overall_pick")
                else:
                    entry_pick["cost"] = p.get("cost")

                graded.append(entry_pick)

            draft_key_picks = {
                "type":            draft_type,
                "note":            "Round 1 picks" if draft_type == "snake" else "Highest-cost pick per team",
                "stats_available": has_stats_data,
                "picks":           graded,
            }

        # ── most rostered NFL team — unique players ───────────────────────────
        # Count unique player_keys per NFL team across all weeks/managers
        nfl_team_players: dict = {}   # nfl_team → set of unique player_keys
        most_rostered_nfl_team = None
        if yr_rosters and yr_info:
            for wk_key, wk_data in yr_rosters.items():
                if not isinstance(wk_data, dict): continue
                for mid, team in wk_data.items():
                    if not isinstance(team, dict): continue
                    for slot in team.get("players", []):
                        if not isinstance(slot, dict): continue
                        pk     = slot.get("player_key") or ""
                        pi     = yr_info.get(pk, {})
                        nfl_tm = pi.get("nfl_team") or ""
                        if pk and nfl_tm and nfl_tm not in ("", "None"):
                            if nfl_tm not in nfl_team_players:
                                nfl_team_players[nfl_tm] = set()
                            nfl_team_players[nfl_tm].add(pk)

            if nfl_team_players:
                top_tm = max(nfl_team_players, key=lambda x: len(nfl_team_players[x]))
                most_rostered_nfl_team = {
                    "nfl_team":      top_tm,
                    "unique_players":len(nfl_team_players[top_tm]),
                    "note": "Count of unique players from this NFL team who appeared on any roster",
                }

        # ── assemble ──────────────────────────────────────────────────────────
        entry = {
            "year":                  int(yr),
            "num_teams":             num_teams,
            "champion":              champion,
            "last_place":            last_place,
            "best_record":           best_rec,
            "best_pf_avg":           best_pf_avg,
            "punishment":            punishment_text,
            "top_scorers":           top_scorers,
            "draft_key_picks":       draft_key_picks,
            "most_rostered_nfl_team":most_rostered_nfl_team,
            "_data_coverage": {
                "has_results":           True,
                "has_punishment":        punishment_text is not None,
                "has_player_stats":      has_stats_data,
                "has_player_info":       bool(yr_info),
                "has_rosters":           bool(yr_rosters),
                "has_draft":             has_draft_data,
                "draft_grades_available":draft_key_picks is not None and has_stats_data,
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
def season_standings(year: int = Query(default=None, description="Season year e.g. 2025. Omit for all finished seasons.")):
    """
    Regular season standings.

    No year → all finished seasons newest first.
    year    → that specific season.
    For current/latest (including in-progress) use /season/standings/latest.

    Sort: seeds 1-4 by playoff_seed, seeds 5-10 by wins then points_for.
    """
    results  = _year_keyed(_load("results.json"))
    matchups = _load("matchups.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    finished = _finished_seasons(results)
    if not finished:
        raise HTTPException(status_code=404, detail="No finished seasons found.")

    target = {str(year): finished[str(year)]} if year else finished
    if year and str(year) not in finished:
        raise HTTPException(status_code=404, detail=f"Season {year} not found or not finished.")

    seasons_out = sorted(
        [_build_standings(yr, s, matchups, True) for yr, s in target.items()],
        key=lambda x: -x["year"]
    )

    if year:
        return seasons_out[0]
    return {"total_seasons": len(seasons_out), "seasons": seasons_out}


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
    Hall of Records — all-time bests and worsts across all BlackGold seasons.

    Scoring records split into 3 eras:
      old_scoring_era:   2007-2011
      era_with_kickers:  2012-2018
      era_no_kickers:    2019-present
    """
    results      = _year_keyed(_load("results.json"))
    matchups_raw = _load("matchups.json")
    player_stats = _load("player_stats.json")
    player_info  = _load("player_info.json")
    drafts       = _load("drafts.json")
    transactions = _load("transactions.json")
    rosters      = _load("rosters.json")
    ices_data    = _load("ices.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    finished     = _finished_seasons(results)
    all_managers = _all_manager_ids(results)

    ERAS = {
        "old_scoring_era":   (2007, 2011),
        "era_with_kickers":  (2012, 2019),
        "era_no_kickers":    (2020, 9999),
    }
    FAAB_START       = 2015
    AUCTION_START    = 2023
    REAL_ICES_START  = 2023

    # ── per-manager accumulators ──────────────────────────────────────────────
    champ_count:   dict = {m: 0 for m in all_managers}
    last_count:    dict = {m: 0 for m in all_managers}
    win_total:     dict = {m: 0 for m in all_managers}
    playoff_wins:  dict = {m: 0 for m in all_managers}
    playoff_app:   dict = {m: 0 for m in all_managers}
    finals_app:    dict = {m: 0 for m in all_managers}

    for yr, season in finished.items():
        yr_int   = int(yr)
        managers = season.get("managers", {})
        num_teams= len(managers)

        for mid, m in managers.items():
            if mid not in champ_count:
                for d in [champ_count,last_count,win_total,playoff_wins,playoff_app,finals_app]:
                    d[mid] = 0
            rs  = m.get("regular_season", {})
            po  = m.get("playoffs", {}) or m.get("playoff", {})
            win_total[mid] += rs.get("wins") or 0
            if po.get("made_playoffs"):
                playoff_app[mid]  += 1
                playoff_wins[mid] += po.get("wins") or 0
                finish = po.get("finish")
                if finish == 1:
                    champ_count[mid] += 1
                if finish in (1, 2):
                    finals_app[mid]  += 1
            else:
                # last place: non-playoff manager with highest RS rank
                pass

        # last place per season
        non_po = [(mid, m) for mid, m in managers.items()
                  if not (m.get("playoffs") or m.get("playoff", {})).get("made_playoffs")]
        if non_po:
            worst_mid = max(non_po, key=lambda x: x[1].get("regular_season", {}).get("rank") or 0)[0]
        else:
            worst_mid = max(managers.items(),
                key=lambda x: x[1].get("regular_season", {}).get("rank") or 0)[0]
        if worst_mid not in last_count: last_count[worst_mid] = 0
        last_count[worst_mid] += 1

    def _holders(count_dict: dict, top_n: int = 1) -> list:
        if not count_dict: return []
        max_val = max(count_dict.values())
        if max_val == 0: return []
        return sorted([
            {"manager_id": mid, "display_name": _display_name(mid, results), "count": max_val}
            for mid, cnt in count_dict.items() if cnt == max_val
        ], key=lambda x: x["display_name"])

    franchise_records = {
        "most_championships":       _holders(champ_count),
        "most_last_place":          _holders(last_count),
        "most_regular_season_wins": _holders(win_total),
        "most_playoff_wins":        _holders(playoff_wins),
        "most_playoff_appearances": _holders(playoff_app),
        "most_finals_appearances":  _holders(finals_app),
    }

    # ── scoring records: season averages + weekly highs/lows ─────────────────
    # Build flat list of season avg entries and single-game scores
    season_avgs:   list = []   # {manager_id, display_name, year, avg_pf, avg_pa}
    single_scores: list = []   # {manager_id, display_name, year, week, points, is_playoffs}

    for yr, season in finished.items():
        yr_int   = int(yr)
        managers = season.get("managers", {})
        for mid, m in managers.items():
            rs = m.get("regular_season", {})
            avg_pf = rs.get("avg_points_for")  or (
                rs.get("points_for")  / rs.get("games", 1) if rs.get("games") else None)
            avg_pa = rs.get("avg_points_against") or (
                rs.get("points_against") / rs.get("games", 1) if rs.get("games") else None)
            if avg_pf and rs.get("games", 0) >= 10:
                season_avgs.append({
                    "manager_id":   mid,
                    "display_name": m.get("display_name") or mid.title(),
                    "year":         yr_int,
                    "avg_pf":       round(avg_pf, 2),
                    "avg_pa":       round(avg_pa, 2) if avg_pa else None,
                    "total_pf":     round(rs.get("points_for") or 0, 2),
                    "games":        rs.get("games"),
                })

    for yr, yr_mu in matchups_raw.items():
        if yr not in finished: continue
        yr_int    = int(yr)
        ps        = yr_mu.get("playoff_start") or 99
        yr_season = finished[yr]
        yr_mgrs   = yr_season.get("managers", {})
        # Seeds 1-4 only for playoff records
        seed_1to4 = {
            mid for mid, m in yr_mgrs.items()
            if (m.get("regular_season") or {}).get("rank", 99) <= 4
        }
        for wk_entry in yr_mu.get("weeks", []):
            wk_num = wk_entry.get("week", 0)
            is_po  = wk_num >= ps
            for m in wk_entry.get("matchups", []):
                if is_po and m.get("is_consolation"): continue
                for t in m.get("teams", []):
                    mid = t.get("manager_id") or ""
                    # For playoff weeks, only include seeds 1-4
                    if is_po and mid not in seed_1to4: continue
                    try: pts = float(t.get("points") or 0)
                    except: continue
                    if pts <= 0: continue
                    single_scores.append({
                        "manager_id":   mid,
                        "display_name": t.get("display_name"),
                        "team_name":    t.get("team_name"),
                        "year":         yr_int,
                        "week":         wk_num,
                        "points":       round(pts, 2),
                        "is_playoffs":  is_po,
                    })

    def _era_scoring(start_yr: int, end_yr: int) -> dict:
        sa  = [x for x in season_avgs    if start_yr <= x["year"] <= end_yr]
        ss  = [x for x in single_scores  if start_yr <= x["year"] <= end_yr]
        rs_only = [x for x in ss if not x["is_playoffs"] and x["points"] > 40]
        po_only = [x for x in ss if x["is_playoffs"]]

        def _best(lst, key, rev=True):
            if not lst: return None
            val = (max if rev else min)(x[key] for x in lst)
            return [x for x in lst if x[key] == val]

        return {
            "top_season_pf_avg":    _best(sa,      "avg_pf"),
            "bottom_season_pf_avg": _best(sa,      "avg_pf",   rev=False),
            "top_season_pa_avg":    _best(sa,      "avg_pa"),
            "bottom_season_pa_avg": _best(sa,      "avg_pa",   rev=False),
            "highest_weekly_pf":    _best(rs_only, "points"),
            "lowest_weekly_pf":     _best(rs_only, "points",   rev=False),
            "highest_playoff_pf":   _best(po_only, "points"),
            "lowest_playoff_pf":    _best(po_only, "points",   rev=False),
        }

    scoring_records = {
        era: _era_scoring(start, end)
        for era, (start, end) in ERAS.items()
    }

    # ── position week records + season totals — split by scoring era ─────────
    # ERA_RANGES matches scoring_records split
    POS_ERA_RANGES = {
        "old_scoring_era":   (2007, 2011),
        "era_with_kickers":  (2012, 2019),
        "era_no_kickers":    (2020, 9999),
    }
    POSITIONS_WEEK   = ["QB","WR","RB","TE","K","DEF"]
    POSITIONS_SEASON = ["QB","WR","RB","TE"]   # season totals for skill positions only

    # Accumulators per era
    era_week_records:   dict = {e: {} for e in POS_ERA_RANGES}
    era_season_records: dict = {e: {} for e in POS_ERA_RANGES}
    years_with_stats:   list = []

    for yr, yr_stats in player_stats.items():
        if yr not in finished or not yr_stats: continue
        yr_int   = int(yr)
        years_with_stats.append(yr_int)

        # Determine which era this year belongs to
        yr_era = None
        for era_name, (start, end) in POS_ERA_RANGES.items():
            if start <= yr_int <= end:
                yr_era = era_name
                break
        if not yr_era: continue

        yr_info   = (player_info.get(yr, {}) or {}).get("players", {})
        yr_mu     = matchups_raw.get(yr, {})
        ps        = yr_mu.get("playoff_start") or 99
        yr_roster = rosters.get(yr, {})

        # Build owner map (last available week)
        owner_map: dict = {}
        all_wk_keys = sorted([k for k in yr_stats if k.startswith("week_")],
                              key=lambda x: int(x.split("_")[1]))
        if all_wk_keys and yr_roster:
            last_wk_data = yr_roster.get(all_wk_keys[-1], {})
            for mid, team in last_wk_data.items():
                if not isinstance(team, dict): continue
                for slot in team.get("players", []):
                    pk = slot.get("player_key") if isinstance(slot, dict) else None
                    if pk:
                        owner_map[pk] = {
                            "manager_id":   mid,
                            "display_name": team.get("display_name") or mid.title(),
                        }

        # Season totals per player (regular season only)
        season_totals: dict = {}   # pk → total pts

        for wk_key in all_wk_keys:
            wk_num = int(wk_key.split("_")[1])
            if wk_num >= ps: continue   # regular season only
            wk_data = yr_stats.get(wk_key, {})

            for pk, pd in wk_data.items():
                if not isinstance(pd, dict): continue
                try: fp = float(pd.get("fantasy_points") or 0)
                except: continue
                if fp <= 0: continue

                pi      = yr_info.get(pk, {})
                pos_raw = pi.get("position") or ""
                pos     = pos_raw.split("/")[0].strip() if "/" in pos_raw else pos_raw
                if pos not in POSITIONS_WEEK: continue
                owner   = owner_map.get(pk, {})

                # ── single week record ────────────────────────────────────
                cur = era_week_records[yr_era].get(pos)
                if cur is None or fp > cur["points"]:
                    era_week_records[yr_era][pos] = {
                        "player_key":  pk,
                        "player_name": pi.get("name") or pk,
                        "position":    pos,
                        "nfl_team":    pi.get("nfl_team"),
                        "manager_id":  owner.get("manager_id"),
                        "display_name":owner.get("display_name"),
                        "year":        yr_int,
                        "week":        wk_num,
                        "points":      round(fp, 2),
                    }

                # ── accumulate season total ───────────────────────────────
                if pos in POSITIONS_SEASON:
                    if pk not in season_totals:
                        season_totals[pk] = {"pts": 0.0, "pos": pos,
                                             "name": pi.get("name") or pk,
                                             "nfl_team": pi.get("nfl_team")}
                    season_totals[pk]["pts"] += fp

        # Check season totals against era records
        for pk, info in season_totals.items():
            pos  = info["pos"]
            pts  = round(info["pts"], 2)
            if pts <= 0: continue
            owner = owner_map.get(pk, {})
            cur   = era_season_records[yr_era].get(pos)
            if cur is None or pts > cur["season_pts"]:
                era_season_records[yr_era][pos] = {
                    "player_key":   pk,
                    "player_name":  info["name"],
                    "position":     pos,
                    "nfl_team":     info["nfl_team"],
                    "manager_id":   owner.get("manager_id"),
                    "display_name": owner.get("display_name"),
                    "year":         yr_int,
                    "season_pts":   pts,
                }

    position_records = {
        era: {
            "best_week":   {pos: era_week_records[era].get(pos)
                            for pos in POSITIONS_WEEK},
            "best_season": {pos: era_season_records[era].get(pos)
                            for pos in POSITIONS_SEASON},
        }
        for era in POS_ERA_RANGES
    }

    # ── most drafted player per position (name-matched, top 3 each) ──────────
    draft_by_pos: dict = {}   # position → {player_name: {count, years}}
    for yr, yr_draft in drafts.items():
        for p in yr_draft.get("picks", []):
            nm  = (p.get("player_name") or "").strip()
            pos = (p.get("position") or "").strip()
            if not nm or pos in ("DEF", "D/ST"): continue
            if pos not in draft_by_pos: draft_by_pos[pos] = {}
            if nm not in draft_by_pos[pos]:
                draft_by_pos[pos][nm] = {"count": 0, "years": []}
            draft_by_pos[pos][nm]["count"] += 1
            draft_by_pos[pos][nm]["years"].append(int(yr))

    most_drafted_players = {}
    for pos in ["QB", "WR", "RB", "TE", "K"]:
        pos_data = draft_by_pos.get(pos, {})
        top3 = sorted(pos_data.items(), key=lambda x: -x[1]["count"])[:3]
        most_drafted_players[pos] = [
            {"player_name": nm, "times_drafted": v["count"], "years": sorted(v["years"])}
            for nm, v in top3 if v["count"] >= 2
        ]

    # ── top 5 players on championship teams (name-matched, weighted) ──────────
    # starter=5pts, bench=3pts, IR=1pt; then avg weekly pts from player_stats
    champ_player_scores: dict = {}   # player_name → {weight_pts, stat_pts, games, pos}

    for yr, season in finished.items():
        managers = season.get("managers", {})
        # Championship roster = ONLY the champion (playoff finish == 1)
        champion_mid = None
        for mid, m in managers.items():
            po = m.get("playoffs", {}) or m.get("playoff", {})
            if po.get("made_playoffs") and po.get("finish") == 1:
                champion_mid = mid
                break
        if not champion_mid: continue

        yr_roster  = rosters.get(yr, {})
        yr_stats   = player_stats.get(yr, {})
        yr_info    = (player_info.get(yr, {}) or {}).get("players", {})
        yr_mu      = matchups_raw.get(yr, {})
        ps         = yr_mu.get("playoff_start") or 99

        # Get champion's last available week roster
        wk_keys = sorted([k for k in yr_roster.keys() if k.startswith("week_")],
                          key=lambda x: int(x.split("_")[1]))
        last_wk_key = wk_keys[-1] if wk_keys else None
        if not last_wk_key: continue

        champ_slots = yr_roster.get(last_wk_key, {}).get(champion_mid, {}).get("players", [])

        champ_display = managers.get(champion_mid, {}).get("display_name") or champion_mid.title()

        for slot in champ_slots:
            if not isinstance(slot, dict): continue
            pk  = slot.get("player_key") or ""
            pi  = yr_info.get(pk, {})
            nm  = (pi.get("name") or pk).strip()
            pos = pi.get("position") or slot.get("selected_position") or ""

            # Weight by slot type
            if slot.get("is_starting"):   weight = 5
            elif slot.get("is_on_ir"):     weight = 1
            else:                          weight = 3

            # Season pts for this player
            season_pts = sum(
                float(yr_stats.get(wk_key, {}).get(pk, {}).get("fantasy_points") or 0)
                for wk_key in yr_stats.keys() if wk_key.startswith("week_")
                if isinstance(yr_stats.get(wk_key, {}).get(pk), dict)
            )

            if nm not in champ_player_scores:
                champ_player_scores[nm] = {"weight": 0, "stat_pts": 0.0,
                                            "appearances": [], "position": pos}
            champ_player_scores[nm]["weight"]   += weight
            champ_player_scores[nm]["stat_pts"] += season_pts
            champ_player_scores[nm]["appearances"].append({
                "year":         int(yr),
                "manager_id":   champion_mid,
                "display_name": champ_display,
                "slot_type":    "starter" if slot.get("is_starting") else
                                ("ir" if slot.get("is_on_ir") else "bench"),
                "weight":       weight,
            })

    top5_champ = sorted(champ_player_scores.items(),
                        key=lambda x: -x[1]["weight"])[:5]
    top5_championship_players = [
        {
            "player_name":             nm,
            "position":                v["position"],
            "championship_appearances":len(v["appearances"]),
            "appearances_detail":      v["appearances"],
            "weighted_score":          v["weight"],
            "avg_season_pts":          round(v["stat_pts"] / len(v["appearances"]), 1) if v["appearances"] else None,
            "note": "Weight: starter=5, bench=3, IR=1 per championship appearance",
        }
        for nm, v in top5_champ
    ]

    # ── biggest auction costs (2023+) ─────────────────────────────────────────
    auction_picks: list = []
    for yr, yr_draft in drafts.items():
        if int(yr) < AUCTION_START: continue
        if yr_draft.get("draft_type") != "auction": continue
        for p in yr_draft.get("picks", []):
            cost = p.get("cost")
            if cost:
                try: cost_int = int(cost)
                except: continue
                auction_picks.append({
                    "manager_id":   p.get("manager_id"),
                    "display_name": p.get("display_name"),
                    "player_name":  p.get("player_name"),
                    "position":     p.get("position"),
                    "nfl_team":     p.get("nfl_team"),
                    "cost":         cost_int,
                    "year":         int(yr),
                })
    auction_picks.sort(key=lambda x: -x["cost"])
    biggest_auction_costs = auction_picks[:10]

    # ── biggest FAAB bids (2015+) ─────────────────────────────────────────────
    faab_bids: list = []
    for yr, yr_tx in transactions.items():
        if int(yr) < FAAB_START: continue
        for move in yr_tx.get("moves", []):
            # transactions.json uses "manager" or "manager_id" depending on year
            mid  = move.get("manager_id") or move.get("manager") or ""
            disp = move.get("display_name") or move.get("manager_a_name") or _display_name(mid, results)
            for added in move.get("added", []):
                bid = added.get("waiver_bid")
                if bid is None: continue
                try: bid_int = int(bid)
                except: continue
                if bid_int <= 0: continue
                faab_bids.append({
                    "manager_id":   mid,
                    "display_name": disp,
                    "player_name":  added.get("name"),
                    "position":     added.get("position"),
                    "nfl_team":     added.get("nfl_team"),
                    "bid":          bid_int,
                    "year":         int(yr),
                })
    faab_bids.sort(key=lambda x: -x["bid"])
    biggest_faab_bids = faab_bids[:10]

    # ── least used FAAB (most leftover at season end, 2015+) ─────────────────
    faab_records: list = []
    for yr, yr_tx in transactions.items():
        yr_int = int(yr)
        if yr_int < FAAB_START: continue
        yr_results = finished.get(yr, {})
        managers_r = yr_results.get("managers", {})
        budget     = 200
        # Sum all FAAB spent per manager — handle "manager" or "manager_id" key
        spent: dict = {}
        for move in yr_tx.get("moves", []):
            mid = move.get("manager_id") or move.get("manager") or ""
            if not mid: continue
            for added in move.get("added", []):
                bid = added.get("waiver_bid")
                if bid is not None:
                    try: spent[mid] = spent.get(mid, 0) + int(bid)
                    except: pass
        # Only include managers who appeared in that season
        season_mids = set(managers_r.keys()) | set(spent.keys())
        for mid in season_mids:
            total_spent = spent.get(mid, 0)
            remaining   = budget - total_spent
            if remaining >= 0:
                faab_records.append({
                    "manager_id":   mid,
                    "display_name": _display_name(mid, results),
                    "year":         yr_int,
                    "budget":       budget,
                    "spent":        total_spent,
                    "remaining":    remaining,
                })

    faab_records.sort(key=lambda x: -x["remaining"])
    least_used_faab = faab_records[:5]

    # ── ices records ──────────────────────────────────────────────────────────
    real_ice_counts:   dict = {}   # manager_id → count (2023+, not playoffs)
    theor_ice_counts:  dict = {}   # manager_id → count (all years, not playoffs)
    real_player_ices:  dict = {}   # player_name → count (real, 2023+)
    theor_player_ices: dict = {}   # player_name → count (theoretical, all years)

    for yr, yr_ices in ices_data.items():
        yr_int = int(yr)
        if not isinstance(yr_ices, list): continue
        for ice in yr_ices:
            if ice.get("is_playoffs"): continue
            mid = ice.get("manager_id") or ""
            nm  = (ice.get("player_name") or "").strip()
            # Theoretical — all years
            theor_ice_counts[mid] = theor_ice_counts.get(mid, 0) + 1
            if nm: theor_player_ices[nm] = theor_player_ices.get(nm, 0) + 1
            # Real — 2023+
            if yr_int >= REAL_ICES_START:
                real_ice_counts[mid] = real_ice_counts.get(mid, 0) + 1
                if nm: real_player_ices[nm] = real_player_ices.get(nm, 0) + 1

    def _top_ice_holders(count_dict: dict, n: int = 3) -> list:
        if not count_dict: return []
        return [{"manager_id": mid, "display_name": _display_name(mid, results), "count": cnt}
                for mid, cnt in sorted(count_dict.items(), key=lambda x: -x[1])[:n]]

    def _top_player_ices(count_dict: dict, n: int = 5) -> list:
        return [{"player_name": nm, "ice_count": cnt}
                for nm, cnt in sorted(count_dict.items(), key=lambda x: -x[1])[:n]]

    ice_records = {
        "most_real_ices": {
            "note":    f"Regular season only, {REAL_ICES_START}+",
            "holders": _top_ice_holders(real_ice_counts),
        },
        "most_theoretical_ices": {
            "note":    "Regular season only, all years retroactively applied",
            "holders": _top_ice_holders(theor_ice_counts),
        },
        "player_most_iced": {
            "real": {
                "note":    f"Regular season only, {REAL_ICES_START}+",
                "players": _top_player_ices(real_player_ices),
            },
            "theoretical": {
                "note":    "Regular season only, all years retroactively applied",
                "players": _top_player_ices(theor_player_ices),
            },
        },
    }

    # ── most frequent trade partners ─────────────────────────────────────────
    pair_counts: dict = {}   # frozenset(mid1,mid2) → count
    for yr, yr_tx in transactions.items():
        for trade in yr_tx.get("trades", []):
            m1 = trade.get("manager_a") or trade.get("trader_manager") or ""
            m2 = trade.get("manager_b") or trade.get("tradee_manager") or ""
            if not m1 or not m2: continue
            key = tuple(sorted([m1, m2]))
            pair_counts[key] = pair_counts.get(key, 0) + 1

    top_pairs = sorted(pair_counts.items(), key=lambda x: -x[1])[:5]
    trade_partner_records = [
        {
            "manager_1":    {"manager_id": p[0], "display_name": _display_name(p[0], results)},
            "manager_2":    {"manager_id": p[1], "display_name": _display_name(p[1], results)},
            "total_trades": cnt,
        }
        for p, cnt in top_pairs
    ]

    # ── most traded players (name-matched across seasons) ────────────────
    traded_name_counts: dict = {}   # player_name → {count, positions, years}
    for yr, yr_tx in transactions.items():
        for trade in yr_tx.get("trades", []):
            # Handle both manager_a/b and trader/tradee key formats
            all_players = (
                trade.get("a_received", []) +
                trade.get("b_received", []) +
                trade.get("trader_receives", []) +
                trade.get("tradee_receives", [])
            )
            for p in all_players:
                nm  = (p.get("name") or p.get("player_name") or "").strip()
                pos = p.get("position") or ""
                if not nm or pos in ("DEF", "D/ST", "K"): continue
                if nm not in traded_name_counts:
                    traded_name_counts[nm] = {"count": 0, "position": pos, "years": []}
                traded_name_counts[nm]["count"] += 1
                if int(yr) not in traded_name_counts[nm]["years"]:
                    traded_name_counts[nm]["years"].append(int(yr))

    top_traded = sorted(traded_name_counts.items(), key=lambda x: -x[1]["count"])[:10]
    most_traded_players = [
        {"player_name": nm, "times_in_trades": v["count"],
         "position": v["position"], "years": sorted(v["years"])}
        for nm, v in top_traded if v["count"] >= 2
    ]

    return {
        "franchise_records":         franchise_records,
        "scoring_records":           scoring_records,
        "position_records":          position_records,
        "draft_records": {
            "most_drafted_players":  most_drafted_players,
            "biggest_auction_costs": biggest_auction_costs,
        },
        "transaction_records": {
            "biggest_faab_bids":       biggest_faab_bids,
            "least_used_faab":         least_used_faab,
            "most_frequent_trade_partners": trade_partner_records,
            "most_traded_players":      most_traded_players,
        },
        "ice_records":               ice_records,
        "championship_roster_records": {
            "top_5_players":         top5_championship_players,
            "note": "Weight: starter=5pts, bench=3pts, IR=1pt per championship appearance. Name-matched across seasons.",
        },
        "_data_coverage": {
            "total_seasons":          len(finished),
            "seasons_with_stats":     len(years_with_stats),
            "player_stats_years":     sorted(years_with_stats, reverse=True),
            "auction_records_from":   AUCTION_START,
            "faab_records_from":      FAAB_START,
            "real_ices_from":         REAL_ICES_START,
        },
    }

# ===========================================================================
# GET /fantasy/{name}/matchups
# ===========================================================================

@router.get("/{name}/matchups")
def manager_matchups(
    name: str,
    era: str = Query(default="all_time"),
):
    """
    A manager's record vs every opponent — regular season + playoffs combined.

    For each opponent shows:
      - RS: wins, losses, ties, avg PF, avg PA, avg diff
      - Playoffs: wins, losses, ties
      - Combined W-L-T and record string
      - Last matchup date and result

    Sorted by most games played (longest rivalries first).
    Filterable by era.
    """
    matchups_data = _year_keyed(_load("matchups.json"))
    results       = _year_keyed(_load("results.json"))

    if not matchups_data:
        raise HTTPException(status_code=404, detail="matchups.json not found.")

    era_def = ERAS.get(era)
    if not era_def:
        raise HTTPException(status_code=400, detail=f"Unknown era: {era}")

    all_ids = _all_manager_ids(results)
    if name not in all_ids:
        raise HTTPException(status_code=404, detail=f"Manager '{name}' not found.")

    display = _display_name(name, results)

    # Accumulator per opponent
    def _acc():
        return {
            "rs":  {"w":0,"l":0,"t":0,"g":0,"pf":0.0,"pa":0.0},
            "pl":  {"w":0,"l":0,"t":0,"g":0},
            "last":None,
        }

    opp_map: dict = {}

    for yr, season in matchups_data.items():
        if not (era_def["start"] <= int(yr) <= era_def["end"]):
            continue

        yr_settings = (results.get(yr) or {})
        playoff_start = season.get("playoff_start") or 99

        for wk_entry in season.get("weeks", []):
            wk_num = wk_entry.get("week", 0)
            is_po  = wk_num >= playoff_start

            for m in wk_entry.get("matchups", []):
                if m.get("is_consolation"): continue
                teams = m.get("teams", [])
                if len(teams) != 2: continue

                me  = next((t for t in teams if t.get("manager_id") == name), None)
                opp = next((t for t in teams if t.get("manager_id") != name), None)
                if not me or not opp: continue

                opp_id = opp.get("manager_id") or ""
                if not opp_id: continue
                if opp_id not in opp_map:
                    opp_map[opp_id] = _acc()

                bucket = opp_map[opp_id]["pl"] if is_po else opp_map[opp_id]["rs"]
                pts_me  = float(me.get("points")  or 0)
                pts_opp = float(opp.get("points") or 0)
                tied    = m.get("is_tied", False)

                bucket["g"]  += 1
                bucket["pf"]  = round(bucket["pf"] + pts_me,  2)
                bucket["pa"]  = round(bucket["pa"] + pts_opp, 2)
                if tied:          bucket["t"] += 1
                elif me.get("is_winner"): bucket["w"] += 1
                else:             bucket["l"] += 1

                # Track last matchup
                last = opp_map[opp_id]["last"]
                if last is None or (int(yr), wk_num) > (last["year"], last["week"]):
                    opp_map[opp_id]["last"] = {
                        "year":      int(yr),
                        "week":      wk_num,
                        "is_playoff":is_po,
                        "my_pts":    round(pts_me, 2),
                        "opp_pts":   round(pts_opp, 2),
                        "result":    "W" if me.get("is_winner") else ("T" if tied else "L"),
                    }

    # Format output
    opponents = []
    for opp_id, data in opp_map.items():
        rs, pl = data["rs"], data["pl"]
        cw = rs["w"] + pl["w"]
        cl = rs["l"] + pl["l"]
        ct = rs["t"] + pl["t"]
        cg = rs["g"] + pl["g"]
        opponents.append({
            "manager_id":    opp_id,
            "display_name":  _display_name(opp_id, results),
            "regular_season": {
                "wins":    rs["w"], "losses": rs["l"], "ties": rs["t"],
                "games":   rs["g"],
                "avg_pf":  round(rs["pf"] / rs["g"], 2) if rs["g"] else None,
                "avg_pa":  round(rs["pa"] / rs["g"], 2) if rs["g"] else None,
                "avg_diff":round((rs["pf"] - rs["pa"]) / rs["g"], 2) if rs["g"] else None,
            },
            "playoffs": {
                "wins": pl["w"], "losses": pl["l"],
                "ties": pl["t"], "games": pl["g"],
            },
            "combined": {
                "wins": cw, "losses": cl, "ties": ct, "games": cg,
                "record_str": f"{cw}-{cl}" + (f"-{ct}" if ct else ""),
                "win_pct": round(cw / cg, 4) if cg else None,
            },
            "last_matchup": data["last"],
        })

    # Sort: most combined games first, then by win pct desc
    opponents.sort(key=lambda x: (-x["combined"]["games"],
                                   -(x["combined"]["win_pct"] or 0)))

    # My overall totals across all opponents
    total_rs = {"w": 0, "l": 0, "t": 0, "g": 0, "pf": 0.0, "pa": 0.0}
    total_pl = {"w": 0, "l": 0, "t": 0, "g": 0}
    for o in opponents:
        rs = o["regular_season"]
        pl = o["playoffs"]
        total_rs["w"]  += rs["wins"]
        total_rs["l"]  += rs["losses"]
        total_rs["t"]  += rs["ties"]
        total_rs["g"]  += rs["games"]
        total_rs["pf"]  = round(total_rs["pf"] + (rs["avg_pf"] or 0) * rs["games"], 2)
        total_rs["pa"]  = round(total_rs["pa"] + (rs["avg_pa"] or 0) * rs["games"], 2)
        total_pl["w"]  += pl["wins"]
        total_pl["l"]  += pl["losses"]
        total_pl["t"]  += pl["ties"]
        total_pl["g"]  += pl["games"]

    return {
        "manager_id":     name,
        "display_name":   display,
        "era":            era,
        "era_label":      era_def["label"],
        "available_eras": {k: v["label"] for k, v in ERAS.items()},
        "summary": {
            "regular_season": {
                "wins":    total_rs["w"],
                "losses":  total_rs["l"],
                "ties":    total_rs["t"],
                "games":   total_rs["g"],
                "avg_pf":  round(total_rs["pf"] / total_rs["g"], 2) if total_rs["g"] else None,
                "avg_pa":  round(total_rs["pa"] / total_rs["g"], 2) if total_rs["g"] else None,
                "avg_diff":round((total_rs["pf"] - total_rs["pa"]) / total_rs["g"], 2) if total_rs["g"] else None,
            },
            "playoffs": {
                "wins":   total_pl["w"],
                "losses": total_pl["l"],
                "ties":   total_pl["t"],
                "games":  total_pl["g"],
            },
        },
        "vs_opponents": opponents,
    }


# ===========================================================================
# GET /fantasy/season/standings/{year}  +  update base to show latest/active
# ===========================================================================

@router.get("/season/standings/latest")
def season_standings_latest():
    """
    Standings for the most recent season — finished OR in-progress.
    Used for the default Season > Standings view.
    """
    results  = _year_keyed(_load("results.json"))
    matchups = _load("matchups.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    # Most recent year regardless of is_finished
    latest_yr = next(iter(results))
    season    = results[latest_yr]
    is_finished = season.get("is_finished", False)

    return _build_standings(latest_yr, season, matchups, is_finished)


@router.get("/season/standings/{year}")
def season_standings_by_year(year: int):
    """
    Standings for a specific season year.
    Works for both finished and in-progress seasons.
    """
    results  = _year_keyed(_load("results.json"))
    matchups = _load("matchups.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    yr_str = str(year)
    if yr_str not in results:
        raise HTTPException(status_code=404, detail=f"Season {year} not found.")

    season      = results[yr_str]
    is_finished = season.get("is_finished", False)
    return _build_standings(yr_str, season, matchups, is_finished)


def _build_standings(yr: str, season: dict, matchups_raw: dict, is_finished: bool) -> dict:
    """Shared standings builder used by both /latest and /{year}."""
    managers  = season.get("managers", {})
    num_teams = len(managers)

    # Projected pts from matchups
    yr_matchups   = matchups_raw.get(str(yr), {})
    playoff_start = yr_matchups.get("playoff_start") or 99
    proj_by_mgr: dict = {}
    for wk_entry in yr_matchups.get("weeks", []):
        if wk_entry.get("week", 99) >= playoff_start: continue
        for m in wk_entry.get("matchups", []):
            if m.get("is_playoffs"): continue
            for team in m.get("teams", []):
                mid  = team.get("manager_id") or ""
                proj = team.get("projected") or 0
                if mid:
                    proj_by_mgr[mid] = round(proj_by_mgr.get(mid, 0) + proj, 2)

    rows = []
    for mid, m in managers.items():
        rs   = m.get("regular_season", {})
        wins   = rs.get("wins")   or 0
        losses = rs.get("losses") or 0
        ties   = rs.get("ties")   or 0
        games  = wins + losses + ties
        pf     = rs.get("points_for")     or 0
        pa     = rs.get("points_against") or 0
        proj   = proj_by_mgr.get(mid)
        seed   = rs.get("rank")   # regular season rank = playoff seed

        rows.append({
            "playoff_seed":       seed,
            "manager_id":         mid,
            "display_name":       m.get("display_name") or mid.title(),
            "team_name":          m.get("team_name"),
            "wins":               wins,
            "losses":             losses,
            "ties":               ties,
            "games_played":       games,
            "points_for":         round(pf, 2),
            "points_for_avg":     round(pf / games, 2) if games else None,
            "points_against":     round(pa, 2),
            "points_against_avg": round(pa / games, 2) if games else None,
            "projected_total":    round(proj, 2) if proj is not None else None,
            "projected_avg":      round(proj / games, 2) if (proj is not None and games) else None,
            "made_playoffs":      bool(seed and seed <= 4),
        })

    # Sort:
    #   Seeds 1-4  → by playoff_seed (Yahoo already ranked them correctly)
    #   Seeds 5-10 → by wins desc, then points_for desc (tie breaker)
    #   Unseeded (in-progress season) → wins desc, points_for desc throughout
    playoff_rows = [r for r in rows if r["playoff_seed"] and r["playoff_seed"] <= 4]
    bubble_rows  = [r for r in rows if r["playoff_seed"] and r["playoff_seed"] > 4]
    unseeded     = [r for r in rows if not r["playoff_seed"]]

    playoff_rows.sort(key=lambda x: x["playoff_seed"])
    bubble_rows.sort(key=lambda x: (-x["wins"], -(x["points_for"] or 0)))
    unseeded.sort(key=lambda x: (-x["wins"], -(x["points_for"] or 0)))

    sorted_rows = playoff_rows + bubble_rows + unseeded

    return {
        "year":          int(yr),
        "is_finished":   is_finished,
        "num_teams":     num_teams,
        "has_projected": bool(proj_by_mgr),
        "standings":     sorted_rows,
    }


# ===========================================================================
# GET /fantasy/season/playoffs/{year}
# ===========================================================================

@router.get("/season/playoffs/{year}")
def season_playoffs_by_year(year: int):
    """
    Full playoff picture for a specific season year.
    Same response shape as GET /fantasy/season/playoffs.
    """
    results      = _year_keyed(_load("results.json"))
    matchups_raw = _load("matchups.json")
    rosters      = _load("rosters.json")
    player_stats = _load("player_stats.json")
    player_info  = _load("player_info.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    yr = str(year)
    if yr not in results:
        raise HTTPException(status_code=404, detail=f"Season {year} not found.")

    # Reuse all the logic from season_playoffs but for a specific year
    # by delegating to the existing function with the year param
    return season_playoffs(year=year)


# ===========================================================================
# GET /fantasy/{name}/transactions  — career transaction summary
# ===========================================================================

@router.get("/{name}/transactions")
def manager_transactions(name: str):
    """
    Career transaction summary for a manager across all seasons.

    Returns:
      adds:   total, avg/season, most expensive FAAB add (player + bid)
      drops:  total, avg/season, most costly drop (cross-ref FAAB paid when added)
      trades: total, avg/season, most frequent partner, most frequently traded player
      draft:  avg pick position (snake), avg top-player cost (auction),
              most frequently drafted player
    """
    transactions = _year_keyed(_load("transactions.json"))
    drafts       = _year_keyed(_load("drafts.json"))
    results      = _year_keyed(_load("results.json"))

    if not transactions:
        raise HTTPException(status_code=404, detail="transactions.json not found.")

    all_ids = _all_manager_ids(results)
    if name not in all_ids:
        raise HTTPException(status_code=404, detail=f"Manager '{name}' not found.")

    # ── accumulate across all seasons ─────────────────────────────────────
    total_adds   = 0
    total_drops  = 0
    total_trades = 0
    seasons_with_data = 0

    best_faab_add  = None   # {player_name, bid, year}
    costly_drop    = None   # {player_name, bid_when_added, year}
    trade_partners: dict = {}   # manager_id → count
    traded_players: dict = {}   # player_key → {name, count}

    # For drop cost: build a lookup of what was paid per player per season
    # {year: {player_key: max_bid_paid}}
    faab_paid_lookup: dict = {}

    snake_picks:   list = []   # overall_pick numbers for avg draft pos (snake)
    auction_costs: list = []   # top cost per team per auction season
    drafted_players: dict = {}  # player_key → {name, count}

    for yr, yr_tx in transactions.items():
        moves  = yr_tx.get("moves",  [])
        trades = yr_tx.get("trades", [])
        if not moves and not trades:
            continue
        seasons_with_data += 1

        # Build FAAB lookup for this year
        yr_faab: dict = {}
        for move in moves:
            if move.get("manager_id") != name: continue
            for added in move.get("added", []):
                pk  = added.get("player_key") or ""
                bid = added.get("waiver_bid")
                if pk and bid is not None:
                    try:
                        bid_int = int(bid)
                        if bid_int > yr_faab.get(pk, -1):
                            yr_faab[pk] = bid_int
                    except (TypeError, ValueError):
                        pass
        faab_paid_lookup[yr] = yr_faab

        # Moves
        for move in moves:
            if move.get("manager_id") != name: continue

            # Adds
            for added in move.get("added", []):
                total_adds += 1
                bid = added.get("waiver_bid")
                if bid is not None:
                    try:
                        bid_int = int(bid)
                        if best_faab_add is None or bid_int > best_faab_add["bid"]:
                            best_faab_add = {
                                "player_key":  added.get("player_key"),
                                "player_name": added.get("name"),
                                "position":    added.get("position"),
                                "bid":         bid_int,
                                "year":        int(yr),
                            }
                    except (TypeError, ValueError):
                        pass

            # Drops
            for dropped in move.get("dropped", []):
                total_drops += 1
                pk   = dropped.get("player_key") or ""
                paid = yr_faab.get(pk)
                if paid is not None:
                    if costly_drop is None or paid > costly_drop["bid_when_added"]:
                        costly_drop = {
                            "player_key":      pk,
                            "player_name":     dropped.get("name"),
                            "position":        dropped.get("position"),
                            "bid_when_added":  paid,
                            "year":            int(yr),
                        }

        # Trades
        for trade in trades:
            is_trader = trade.get("trader_manager") == name
            is_tradee = trade.get("tradee_manager") == name
            if not is_trader and not is_tradee: continue

            total_trades += 1
            partner = trade.get("tradee_manager") if is_trader else trade.get("trader_manager")
            if partner:
                trade_partners[partner] = trade_partners.get(partner, 0) + 1

            # Players I received
            received = trade.get("trader_receives" if is_trader else "tradee_receives", [])
            for p in received:
                pk = p.get("player_key") or ""
                nm = p.get("name") or pk
                if pk:
                    if pk not in traded_players:
                        traded_players[pk] = {"name": nm, "count": 0}
                    traded_players[pk]["count"] += 1

            # Players I sent (also counts as "traded")
            sent = trade.get("tradee_receives" if is_trader else "trader_receives", [])
            for p in sent:
                pk = p.get("player_key") or ""
                nm = p.get("name") or pk
                if pk:
                    if pk not in traded_players:
                        traded_players[pk] = {"name": nm, "count": 0}
                    traded_players[pk]["count"] += 1

    # Draft stats
    for yr, yr_draft in drafts.items():
        picks      = yr_draft.get("picks", [])
        draft_type = yr_draft.get("draft_type", "snake")

        my_picks = [p for p in picks if p.get("manager_id") == name]

        for p in my_picks:
            pk = p.get("player_key") or ""
            nm = p.get("player_name") or pk
            if pk:
                if pk not in drafted_players:
                    drafted_players[pk] = {"name": nm, "count": 0}
                drafted_players[pk]["count"] += 1

            if draft_type == "snake":
                pick_num = p.get("overall_pick") or p.get("pick")
                if pick_num:
                    try: snake_picks.append(int(pick_num))
                    except: pass
            else:
                cost = p.get("cost")
                if cost:
                    try: auction_costs.append(int(cost))
                    except: pass

    # Most frequent trade partner
    top_partner = None
    if trade_partners:
        best_mid = max(trade_partners, key=lambda x: trade_partners[x])
        top_partner = {
            "manager_id":   best_mid,
            "display_name": _display_name(best_mid, results),
            "trade_count":  trade_partners[best_mid],
        }

    # Most frequently traded player
    top_traded = None
    if traded_players:
        best_pk = max(traded_players, key=lambda x: traded_players[x]["count"])
        top_traded = {
            "player_key":  best_pk,
            "player_name": traded_players[best_pk]["name"],
            "times_traded":traded_players[best_pk]["count"],
        }

    # Most frequently drafted player
    top_drafted = None
    if drafted_players:
        best_pk = max(drafted_players, key=lambda x: drafted_players[x]["count"])
        top_drafted = {
            "player_key":   best_pk,
            "player_name":  drafted_players[best_pk]["name"],
            "times_drafted":drafted_players[best_pk]["count"],
        }

    n = seasons_with_data or 1
    nd = len(drafts) or 1

    return {
        "manager_id":   name,
        "display_name": _display_name(name, results),
        "seasons_tracked": seasons_with_data,
        "adds": {
            "total":          total_adds,
            "avg_per_season": round(total_adds / n, 1),
            "best_faab_add":  best_faab_add,
        },
        "drops": {
            "total":           total_drops,
            "avg_per_season":  round(total_drops / n, 1),
            "most_costly_drop":costly_drop,
            "note": "most_costly_drop = player dropped who had highest FAAB bid when originally added",
        },
        "trades": {
            "total":               total_trades,
            "avg_per_season":      round(total_trades / n, 1),
            "top_trade_partner":   top_partner,
            "most_traded_player":  top_traded,
        },
        "draft": {
            "avg_pick_snake":      round(sum(snake_picks) / len(snake_picks), 1) if snake_picks else None,
            "avg_top_cost_auction":round(sum(auction_costs) / len(auction_costs), 1) if auction_costs else None,
            "most_drafted_player": top_drafted,
            "snake_seasons":       len(snake_picks),
            "auction_seasons":     len(set(
                yr for yr, yd in drafts.items()
                if yd.get("draft_type") == "auction"
                and any(p.get("manager_id") == name for p in yd.get("picks", []))
            )),
        },
    }


# ===========================================================================
# GET /fantasy/{name}/transactions/{year}  — single season breakdown
# ===========================================================================

@router.get("/{name}/transactions/{year}")
def manager_transactions_year(name: str, year: int):
    """
    Full transaction breakdown for a manager in a specific season.

    Sections:
      adds:   each player added, FAAB bid, source (waivers/free agent), timestamp
              + total adds and most expensive FAAB add
      drops:  each player dropped, what FAAB was paid when added (if known)
              + total drops and most costly drop
      trades: each trade with partner, players sent vs received
              + total trades
      draft:  every pick with cost (auction) or position (snake),
              season_pts and pos_label if player_stats available
              e.g. "WR5" = 5th most points among WRs rostered in league
    """
    transactions = _year_keyed(_load("transactions.json"))
    drafts       = _year_keyed(_load("drafts.json"))
    results      = _year_keyed(_load("results.json"))

    all_ids = _all_manager_ids(results)
    if name not in all_ids:
        raise HTTPException(status_code=404, detail=f"Manager '{name}' not found.")

    yr = str(year)
    yr_tx    = transactions.get(yr, {})
    yr_draft = drafts.get(yr, {})

    moves  = yr_tx.get("moves",  [])
    trades = yr_tx.get("trades", [])

    # ── FAAB lookup for costly-drop cross-reference ───────────────────────
    faab_paid: dict = {}   # player_key → max bid paid this season
    for move in moves:
        if move.get("manager_id") != name: continue
        for added in move.get("added", []):
            pk  = added.get("player_key") or ""
            bid = added.get("waiver_bid")
            if pk and bid is not None:
                try:
                    bid_int = int(bid)
                    if bid_int > faab_paid.get(pk, -1):
                        faab_paid[pk] = bid_int
                except (TypeError, ValueError):
                    pass

    # ── ADDS ─────────────────────────────────────────────────────────────
    adds_list = []
    for move in moves:
        if move.get("manager_id") != name: continue
        ts = move.get("timestamp")
        for added in move.get("added", []):
            bid = added.get("waiver_bid")
            try:   bid_int = int(bid) if bid is not None else None
            except: bid_int = None
            adds_list.append({
                "player_key":  added.get("player_key"),
                "player_name": added.get("name"),
                "position":    added.get("position"),
                "nfl_team":    added.get("nfl_team"),
                "waiver_bid":  bid_int,
                "source_type": added.get("source_type"),
                "timestamp":   ts,
            })

    adds_list.sort(key=lambda x: -(x["waiver_bid"] or 0))
    best_faab = adds_list[0] if adds_list else None

    # ── DROPS ─────────────────────────────────────────────────────────────
    drops_list = []
    for move in moves:
        if move.get("manager_id") != name: continue
        ts = move.get("timestamp")
        for dropped in move.get("dropped", []):
            pk   = dropped.get("player_key") or ""
            paid = faab_paid.get(pk)
            drops_list.append({
                "player_key":     pk,
                "player_name":    dropped.get("name"),
                "position":       dropped.get("position"),
                "nfl_team":       dropped.get("nfl_team"),
                "bid_when_added": paid,
                "timestamp":      ts,
            })

    drops_list.sort(key=lambda x: -(x["bid_when_added"] or 0))
    costly_drop = drops_list[0] if drops_list else None

    # ── TRADES ────────────────────────────────────────────────────────────
    trades_list = []
    for trade in trades:
        is_trader = trade.get("trader_manager") == name
        is_tradee = trade.get("tradee_manager") == name
        if not is_trader and not is_tradee: continue

        partner   = trade.get("tradee_manager") if is_trader else trade.get("trader_manager")
        i_received = trade.get("trader_receives" if is_trader else "tradee_receives", [])
        i_sent     = trade.get("tradee_receives" if is_trader else "trader_receives", [])

        trades_list.append({
            "partner_manager_id":   partner,
            "partner_display_name": _display_name(partner, results),
            "timestamp":            trade.get("timestamp"),
            "i_received":           i_received,
            "i_sent":               i_sent,
        })

    trades_list.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)

    # ── DRAFT ─────────────────────────────────────────────────────────────
    draft_type  = yr_draft.get("draft_type", "snake")
    all_picks   = yr_draft.get("picks", [])
    my_picks    = [p for p in all_picks if p.get("manager_id") == name]
    my_picks.sort(key=lambda x: x.get("overall_pick") or 999)

    draft_summary = None
    if my_picks:
        if draft_type == "snake":
            avg_pick = round(
                sum(p.get("overall_pick") or 0 for p in my_picks) / len(my_picks), 1
            ) if my_picks else None
            draft_summary = {
                "type":           "snake",
                "total_picks":    len(my_picks),
                "avg_pick":       avg_pick,
                "picks":          my_picks,
            }
        else:
            top_pick = max(my_picks, key=lambda x: x.get("cost") or 0)
            total_spent = sum(p.get("cost") or 0 for p in my_picks)
            draft_summary = {
                "type":           "auction",
                "total_picks":    len(my_picks),
                "total_spent":    total_spent,
                "top_pick":       top_pick,
                "picks":          my_picks,
                "note": "pos_label (e.g. WR5) = rank among rostered players at that position. Requires player_stats.",
            }

    return {
        "manager_id":   name,
        "display_name": _display_name(name, results),
        "year":         year,
        "adds": {
            "total":          len(adds_list),
            "best_faab_add":  best_faab,
            "all_adds":       adds_list,
        },
        "drops": {
            "total":           len(drops_list),
            "most_costly_drop":costly_drop,
            "all_drops":       drops_list,
            "note": "bid_when_added = FAAB paid when this player was originally added this season (null if picked up free or unknown)",
        },
        "trades": {
            "total":      len(trades_list),
            "all_trades": trades_list,
        },
        "draft": draft_summary,
    }


# ===========================================================================
# GET /fantasy/teams/overview
# ===========================================================================

@router.get("/teams/overview")
def teams_overview():
    """
    All-managers career overview table.

    Returns every manager who has ever played, with career stats:
      - Total seasons played
      - Regular season W-L-T record
      - Championships, last place finishes
      - Playoff appearances and playoff W-L-T record
      - Profile photo URL placeholder (populated from settings/profile)
    """
    results  = _year_keyed(_load("results.json"))
    managers_json = _load("managers.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    finished     = _finished_seasons(results)
    all_managers = _all_manager_ids(results)

    # Accumulators
    stats: dict = {}
    for mid in all_managers:
        stats[mid] = {
            "manager_id":    mid,
            "display_name":  _display_name(mid, results),
            "photo_url":     None,   # populated from settings/profile when built
            "seasons":       0,
            "rs_wins":       0,
            "rs_losses":     0,
            "rs_ties":       0,
            "championships": 0,
            "last_place":    0,
            "playoff_apps":  0,
            "po_wins":       0,
            "po_losses":     0,
            "po_ties":       0,
        }

    for yr, season in finished.items():
        managers  = season.get("managers", {})
        num_teams = len(managers)

        # Find last place this season
        non_po = [(mid, m) for mid, m in managers.items()
                  if not (m.get("playoffs") or m.get("playoff", {})).get("made_playoffs")]
        last_mid = max(non_po,
            key=lambda x: x[1].get("regular_season", {}).get("rank") or 0)[0] if non_po else None

        for mid, m in managers.items():
            if mid not in stats: continue
            rs = m.get("regular_season", {})
            po = m.get("playoffs", {}) or m.get("playoff", {})

            stats[mid]["seasons"]    += 1
            stats[mid]["rs_wins"]    += rs.get("wins") or 0
            stats[mid]["rs_losses"]  += rs.get("losses") or 0
            stats[mid]["rs_ties"]    += rs.get("ties") or 0

            if po.get("made_playoffs"):
                stats[mid]["playoff_apps"] += 1
                stats[mid]["po_wins"]      += po.get("wins") or 0
                stats[mid]["po_losses"]    += po.get("losses") or 0
                stats[mid]["po_ties"]      += po.get("ties") or 0
                if po.get("finish") == 1:
                    stats[mid]["championships"] += 1

            if mid == last_mid:
                stats[mid]["last_place"] += 1

    # Sort by total wins desc
    overview = sorted(stats.values(), key=lambda x: -x["rs_wins"])
    return {
        "total_managers": len(overview),
        "managers":       overview,
        "_note": "photo_url will be populated once settings/profile is built",
    }


# ===========================================================================
# GET /fantasy/teams/results
# ===========================================================================

@router.get("/teams/results")
def teams_results(
    era: str = Query(default="all_time"),
):
    """
    All-managers results table — scoring stats, standings, ices, winnings.
    Filterable by era.
    """
    results      = _year_keyed(_load("results.json"))
    matchups_raw = _load("matchups.json")
    payouts_data = _load("payouts.json")
    ices_data    = _load("ices.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    era_def = ERAS.get(era)
    if not era_def:
        raise HTTPException(status_code=400, detail=f"Unknown era: {era}")

    finished     = _finished_seasons(results)
    all_managers = _all_manager_ids(results)

    # Accumulators per manager
    def _blank():
        return {
            "rs_wins": 0, "rs_losses": 0, "rs_ties": 0, "rs_games": 0,
            "rs_pf": 0.0, "rs_pa": 0.0, "rs_proj_pf": 0.0,
            "rs_rank_sum": 0, "rs_seasons": 0,
            "po_wins": 0, "po_losses": 0, "po_ties": 0, "po_games": 0,
            "po_pf": 0.0, "po_pa": 0.0, "po_proj_pf": 0.0,
            "weekly_high_total": 0, "weekly_high_pos": 0,
            "ices_rs": 0, "winnings": 0.0,
        }

    acc: dict = {mid: _blank() for mid in all_managers}

    for yr, season in finished.items():
        yr_int = int(yr)
        if not (era_def["start"] <= yr_int <= era_def["end"]): continue
        managers = season.get("managers", {})

        for mid, m in managers.items():
            if mid not in acc: acc[mid] = _blank()
            rs = m.get("regular_season", {})
            po = m.get("playoffs",      {}) or m.get("playoff", {})

            acc[mid]["rs_wins"]    += rs.get("wins")    or 0
            acc[mid]["rs_losses"]  += rs.get("losses")  or 0
            acc[mid]["rs_ties"]    += rs.get("ties")    or 0
            acc[mid]["rs_games"]   += rs.get("games")   or 0
            acc[mid]["rs_pf"]      += rs.get("points_for")        or 0
            acc[mid]["rs_pa"]      += rs.get("points_against")    or 0
            acc[mid]["rs_proj_pf"] += rs.get("projected_points_for") or 0
            acc[mid]["rs_rank_sum"]+= rs.get("rank") or 0
            acc[mid]["rs_seasons"] += 1

            if po.get("made_playoffs"):
                acc[mid]["po_wins"]    += po.get("wins")    or 0
                acc[mid]["po_losses"]  += po.get("losses")  or 0
                acc[mid]["po_ties"]    += po.get("ties")    or 0
                acc[mid]["po_games"]   += po.get("games")   or 0
                acc[mid]["po_pf"]      += po.get("points_for")     or 0
                acc[mid]["po_pa"]      += po.get("points_against") or 0

    # Weekly high scores from payouts.json
    for yr, yr_payouts in payouts_data.items():
        yr_int = int(yr)
        if not (era_def["start"] <= yr_int <= era_def["end"]): continue
        if not isinstance(yr_payouts, dict): continue
        for wk_key, wk_data in yr_payouts.items():
            if not wk_key.startswith("week_") or not isinstance(wk_data, dict): continue
            # Total points payout winners
            tot = wk_data.get("total_points_payout", {})
            for mid in (tot.get("winners") or []):
                if mid in acc: acc[mid]["weekly_high_total"] += 1
            # Position payout winners
            pos_p = wk_data.get("position_payout", {})
            for w in (pos_p.get("winners") or []):
                mid = w.get("manager_id") if isinstance(w, dict) else w
                if mid and mid in acc: acc[mid]["weekly_high_pos"] += 1

    # Ices (regular season only)
    for yr, yr_ices in ices_data.items():
        yr_int = int(yr)
        if not (era_def["start"] <= yr_int <= era_def["end"]): continue
        if not isinstance(yr_ices, list): continue
        for ice in yr_ices:
            if ice.get("is_playoffs"): continue
            mid = ice.get("manager_id") or ""
            if mid in acc: acc[mid]["ices_rs"] += 1

    # Winnings from payouts.json
    for yr, yr_payouts in payouts_data.items():
        yr_int = int(yr)
        if not (era_def["start"] <= yr_int <= era_def["end"]): continue
        if not isinstance(yr_payouts, dict): continue
        # Season payouts
        season_po = yr_payouts.get("season", {})
        for key in ["champion", "runner_up", "third_place",
                    "regular_season_1_seed", "regular_season_high_points"]:
            entry = season_po.get(key, {})
            mid   = entry.get("manager_id") if isinstance(entry, dict) else None
            amt   = entry.get("payout", 0)   if isinstance(entry, dict) else 0
            if mid and mid in acc: acc[mid]["winnings"] += amt or 0
        # Weekly payouts
        for wk_key, wk_data in yr_payouts.items():
            if not wk_key.startswith("week_") or not isinstance(wk_data, dict): continue
            for payout_key in ["total_points_payout", "position_payout"]:
                pd = wk_data.get(payout_key, {})
                if not isinstance(pd, dict): continue
                payout_each = pd.get("payout_each") or 0
                winners = pd.get("winners") or []
                for w in winners:
                    mid = w.get("manager_id") if isinstance(w, dict) else w
                    if mid and mid in acc:
                        acc[mid]["winnings"] += payout_each

    # Format output
    table = []
    for mid in sorted(acc.keys(), key=lambda x: -acc[x]["rs_wins"]):
        a = acc[mid]
        rs_g   = a["rs_games"]   or 1
        rs_s   = a["rs_seasons"] or 1
        po_g   = a["po_games"]   or 1
        table.append({
            "manager_id":          mid,
            "display_name":        _display_name(mid, results),
            "regular_season": {
                "wins": a["rs_wins"], "losses": a["rs_losses"], "ties": a["rs_ties"],
                "games": a["rs_games"],
                "avg_finish":       round(a["rs_rank_sum"] / rs_s, 1) if rs_s else None,
                "avg_pf":           round(a["rs_pf"] / rs_g, 2) if rs_g else None,
                "avg_pa":           round(a["rs_pa"] / rs_g, 2) if rs_g else None,
                "avg_proj_pf":      round(a["rs_proj_pf"] / rs_g, 2) if rs_g else None,
                "proj_vs_actual_diff": round((a["rs_proj_pf"] - a["rs_pf"]) / rs_g, 2) if rs_g else None,
            },
            "playoffs": {
                "wins": a["po_wins"], "losses": a["po_losses"], "ties": a["po_ties"],
                "games": a["po_games"],
                "avg_pf": round(a["po_pf"] / po_g, 2) if a["po_games"] else None,
                "avg_pa": round(a["po_pa"] / po_g, 2) if a["po_games"] else None,
            },
            "weekly_high_total_wins": a["weekly_high_total"],
            "weekly_high_pos_wins":   a["weekly_high_pos"],
            "ices_regular_season":    a["ices_rs"],
            "total_winnings":         round(a["winnings"], 2),
        })

    return {
        "era":            era,
        "era_label":      era_def["label"],
        "available_eras": {k: v["label"] for k, v in ERAS.items()},
        "managers":       table,
    }


# ===========================================================================
# GET /fantasy/teams/transactions
# ===========================================================================

@router.get("/teams/transactions")
def teams_transactions(
    era: str = Query(default="all_time"),
):
    """
    All-managers transaction summary table.
    Filterable by era.
    """
    results      = _year_keyed(_load("results.json"))
    transactions = _load("transactions.json")
    drafts       = _load("drafts.json")

    if not results:
        raise HTTPException(status_code=404, detail="results.json not found.")

    era_def = ERAS.get(era)
    if not era_def:
        raise HTTPException(status_code=400, detail=f"Unknown era: {era}")

    finished     = _finished_seasons(results)
    all_managers = _all_manager_ids(results)

    def _blank():
        return {
            "total_adds": 0, "total_drops": 0, "total_trades": 0,
            "seasons": 0, "best_faab": None,
            "trade_partners": {}, "drafted_players": {},
            "best_auction_bid": None,
        }

    acc: dict = {mid: _blank() for mid in all_managers}

    for yr, yr_tx in transactions.items():
        yr_int = int(yr)
        if not (era_def["start"] <= yr_int <= era_def["end"]): continue
        if yr not in finished: continue

        season_managers = set(finished[yr].get("managers", {}).keys())
        for mid in season_managers:
            if mid not in acc: acc[mid] = _blank()
            acc[mid]["seasons"] += 1

        # Moves
        for move in yr_tx.get("moves", []):
            mid = move.get("manager_id") or move.get("manager") or ""
            if not mid or mid not in acc: continue
            adds   = move.get("added", [])
            drops  = move.get("dropped", [])
            acc[mid]["total_adds"]  += len(adds)
            acc[mid]["total_drops"] += len(drops)
            for added in adds:
                bid = added.get("waiver_bid")
                if bid:
                    try:
                        bid_int = int(bid)
                        if acc[mid]["best_faab"] is None or bid_int > acc[mid]["best_faab"]["bid"]:
                            acc[mid]["best_faab"] = {
                                "player_name": added.get("name"),
                                "bid":         bid_int,
                                "year":        yr_int,
                            }
                    except: pass

        # Trades
        for trade in yr_tx.get("trades", []):
            m1 = trade.get("manager_a") or trade.get("trader_manager") or ""
            m2 = trade.get("manager_b") or trade.get("tradee_manager") or ""
            for mid in [m1, m2]:
                if not mid or mid not in acc: continue
                acc[mid]["total_trades"] += 1
                partner = m2 if mid == m1 else m1
                if partner:
                    acc[mid]["trade_partners"][partner] = \
                        acc[mid]["trade_partners"].get(partner, 0) + 1

        # Drafts
        for pick in drafts.get(yr, {}).get("picks", []):
            mid = pick.get("manager_id") or ""
            if not mid or mid not in acc: continue
            nm   = (pick.get("player_name") or "").strip()
            cost = pick.get("cost")
            if nm:
                acc[mid]["drafted_players"][nm] = \
                    acc[mid]["drafted_players"].get(nm, 0) + 1
            if cost:
                try:
                    cost_int = int(cost)
                    if acc[mid]["best_auction_bid"] is None or \
                       cost_int > acc[mid]["best_auction_bid"]["cost"]:
                        acc[mid]["best_auction_bid"] = {
                            "player_name": nm,
                            "cost":        cost_int,
                            "year":        yr_int,
                        }
                except: pass

    table = []
    for mid in sorted(all_managers):
        a = acc.get(mid, _blank())
        seasons = a["seasons"] or 1
        # Top trade partner
        top_partner = None
        if a["trade_partners"]:
            tp_mid = max(a["trade_partners"], key=lambda x: a["trade_partners"][x])
            top_partner = {
                "manager_id":   tp_mid,
                "display_name": _display_name(tp_mid, results),
                "trades":       a["trade_partners"][tp_mid],
            }
        # Most drafted player
        top_drafted = None
        if a["drafted_players"]:
            td_nm = max(a["drafted_players"], key=lambda x: a["drafted_players"][x])
            top_drafted = {"player_name": td_nm, "count": a["drafted_players"][td_nm]}

        table.append({
            "manager_id":       mid,
            "display_name":     _display_name(mid, results),
            "seasons_tracked":  a["seasons"],
            "total_adds":       a["total_adds"],
            "total_drops":      a["total_drops"],
            "total_moves":      a["total_adds"] + a["total_drops"],
            "avg_moves_per_season": round((a["total_adds"] + a["total_drops"]) / seasons, 1),
            "best_faab_bid":    a["best_faab"],
            "total_trades":     a["total_trades"],
            "avg_trades_per_season": round(a["total_trades"] / seasons, 1),
            "top_trade_partner":top_partner,
            "most_drafted_player": top_drafted,
            "best_auction_bid": a["best_auction_bid"],
        })

    table.sort(key=lambda x: -x["total_moves"])
    return {
        "era":            era,
        "era_label":      era_def["label"],
        "available_eras": {k: v["label"] for k, v in ERAS.items()},
        "managers":       table,
    }