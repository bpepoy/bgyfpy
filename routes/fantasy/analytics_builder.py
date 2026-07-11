"""
analytics_builder.py
====================
Standalone analytics builder — built incrementally.
Run directly: python analytics_builder.py

Current:
  build_wl_combined()          — actual / theoretical / best ball W-L-T
  build_ice_records()          — real and theoretical ices by manager, position, era, season
  build_championship_players() — weighted roster score across championship teams
  build_top_draft_picks()      — most drafted players (snake R1 + auction top 10)
  build_bar_chart_race()       — cumulative wins by manager by season (all managers)
  build_trade_records()        — trade partners + most traded players, per era
  build_scoring_records()      — top/bottom PF, position records, per era
  build_mgr_records()          — best/worst season, player-mgr combo (KNOWN_MEMBERS only)
  build_faab_auction()         — FAAB + auction records, per era (KNOWN_MEMBERS only)
  build_double_play()          — frequency of playing each opponent twice, per era
"""

import json
import os

# ── config ────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "fantasy")

ERAS = {
    "overall":      (2007, 9999),
    "darkness":     (2007, 2011),
    "sam_era":      (2009, 2018),
    "frank_era":    (2012, 9999),
    "jordan_era":   (2019, 9999),
    "auction_era":  (2023, 9999),
}

# Managers included in scoring/FAAB/player analytics
KNOWN_MEMBERS = {
    "blake","brian","frank","jake","joey",
    "jordan","kyle","nick","rob","sam","zef"
}

FLEX_ELIGIBLE = {"WR", "RB", "TE"}

# ── helpers ───────────────────────────────────────────────────────────────────

def load(filename: str) -> dict:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(f"  [WARN] {filename} not found")
        return {}
    with open(path) as f:
        raw = json.load(f)
    if "data" in raw and isinstance(raw["data"], dict):
        return raw["data"]
    return raw


def dn(mid: str, results: dict) -> str:
    for yr in sorted(results.keys(), reverse=True):
        m = results[yr].get("managers", {}).get(mid, {})
        if m.get("display_name"):
            return m["display_name"]
    return mid.title()


def parse_roster_reqs(yr_rules: dict) -> tuple:
    """Returns (required_slots dict, flex_count int)."""
    required: dict = {}
    flex = 0
    for slot in yr_rules.get("roster_positions", []):
        pos = slot.get("position", "") if isinstance(slot, dict) else slot
        cnt = slot.get("count", 1)    if isinstance(slot, dict) else 1
        if not pos or pos in ("BN", "IR", "IR+"):
            continue
        if pos in ("W/R/T", "FLEX", "W/R", "Q/W/R/T"):
            flex += cnt
        else:
            required[pos] = required.get(pos, 0) + cnt
    return required, flex


def optimal_score(mid: str, wk_roster: dict, wk_stats: dict,
                  yr_info: dict, yr_rules: dict):
    """Best-ball score: optimal lineup from all rostered non-IR players."""
    team = wk_roster.get(mid, {})
    if not team:
        return None
    required, flex_count = parse_roster_reqs(yr_rules)
    players = []
    for slot in team.get("players", []):
        if not isinstance(slot, dict): continue
        if slot.get("is_on_ir"):       continue
        pk      = slot.get("player_key") or ""
        pi      = yr_info.get(pk, {})
        pos_raw = pi.get("position") or ""
        pos     = pos_raw.split("/")[0].strip() if "/" in pos_raw else pos_raw
        pd      = wk_stats.get(pk)
        pts     = float(pd.get("fantasy_points") or 0) if isinstance(pd, dict) else 0.0
        if pos:
            players.append({"pos": pos, "pts": pts, "used": False})
    if not players:
        return None
    players.sort(key=lambda x: -x["pts"])
    total = 0.0
    reqs  = dict(required)
    flex_left = flex_count
    for p in players:
        if reqs.get(p["pos"], 0) > 0:
            reqs[p["pos"]] -= 1
            total += p["pts"]
            p["used"] = True
    for p in players:
        if flex_left <= 0: break
        if p["used"]: continue
        if p["pos"] in FLEX_ELIGIBLE:
            total += p["pts"]
            p["used"] = True
            flex_left -= 1
    return round(total, 2)


def add_ranks(managers_dict: dict, key: str, rank_field: str,
              higher_is_better: bool = True) -> None:
    """Add rank field to each manager dict, ranked by key."""
    valid = [(mid, m) for mid, m in managers_dict.items()
             if m.get(key) is not None]
    sorted_vals = sorted(valid, key=lambda x: -x[1][key] if higher_is_better
                         else x[1][key])
    for rank, (mid, _) in enumerate(sorted_vals, 1):
        managers_dict[mid][rank_field] = rank


# ── main builder ──────────────────────────────────────────────────────────────

def build_wl_combined(results: dict, matchups: dict, rosters: dict,
                      player_stats: dict, player_info: dict,
                      rules: dict) -> dict:
    """
    Single-pass builder producing unified wl_records structure.
    Computes actual, theoretical, and best ball in one loop.
    """
    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    all_mids = set()
    for yr in finished:
        all_mids.update(finished[yr].get("managers", {}).keys())

    # ── per-season accumulators ───────────────────────────────────────────────
    # season_rows[yr][mid] = raw numbers, assembled at end
    season_rows: dict = {}

    # era+career accumulators: era_acc[era_key][mid] = {...}
    era_acc: dict = {era: {} for era in ERAS}

    def blank_acc():
        return {
            # actual RS
            "rs_w":0,"rs_l":0,"rs_t":0,"rs_g":0,"rs_seasons":0,
            "rs_pf":0.0,"rs_pa":0.0,"rs_proj_pf":0.0,"rs_proj_pa":0.0,
            # actual PO
            "po_apps":0,"po_w":0,"po_l":0,"po_t":0,"po_g":0,
            "po_pf":0.0,"po_pa":0.0,"po_proj_pf":0.0,"po_proj_pa":0.0,
            "po_finishes": [],   # list of {yr, finish}
            # theoretical RS
            "th_w":0.0,"th_l":0.0,"th_t":0.0,
            # best ball RS
            "bb_w":0,"bb_l":0,"bb_t":0,"bb_g":0,
            "bb_pf":0.0,"bb_pa":0.0,
            "bb_seasons":0,
        }

    for era in ERAS:
        for mid in all_mids:
            era_acc[era][mid] = blank_acc()

    # ── season loop ───────────────────────────────────────────────────────────
    for yr in sorted(finished.keys(), key=int):
        yr_int   = int(yr)
        managers = finished[yr].get("managers", {})
        yr_mu    = matchups.get(yr, {})
        ps       = yr_mu.get("playoff_start") or 99
        yr_rules = rules.get(yr, {})
        yr_stats = player_stats.get(yr, {})
        yr_info  = (player_info.get(yr, {}) or {}).get("players", {})
        has_bb   = bool(yr_stats and yr_info)

        # which eras include this season?
        active_eras = [era for era, (s, e) in ERAS.items() if s <= yr_int <= e]

        # ── per-season init ───────────────────────────────────────────────────
        season_rows[yr] = {}
        yr_theo: dict = {mid: {"w":0.0,"l":0.0,"t":0.0} for mid in managers}
        yr_bb:   dict = {mid: {"w":0,"l":0,"t":0,"pf":0.0,"pa":0.0}
                         for mid in managers}
        yr_actual_pf: dict = {}

        # ── weekly loop ───────────────────────────────────────────────────────
        for wk_entry in yr_mu.get("weeks", []):
            wk_num = wk_entry.get("week", 0)
            if wk_num >= ps: continue
            wk_key   = f"week_{wk_num}"
            wk_stats = yr_stats.get(wk_key, {}) if yr_stats else {}
            wk_roster= rosters.get(yr, {}).get(wk_key, {}) if rosters else {}

            # collect actual scores this week
            wk_scores: dict = {}
            for m in wk_entry.get("matchups", []):
                if m.get("is_consolation"): continue
                for t in m.get("teams", []):
                    mid = t.get("manager_id") or ""
                    try: pts = float(t.get("points") or 0)
                    except: pts = 0.0
                    if mid: wk_scores[mid] = pts

            if len(wk_scores) < 2: continue
            n = len(wk_scores)

            # theoretical: compare vs all others, divide by (n-1)
            for mid, my_pts in wk_scores.items():
                if mid not in yr_theo: continue
                opps = [s for m2, s in wk_scores.items() if m2 != mid]
                d    = len(opps)
                yr_theo[mid]["w"] += sum(1 for s in opps if my_pts > s) / d
                yr_theo[mid]["l"] += sum(1 for s in opps if my_pts < s) / d
                yr_theo[mid]["t"] += sum(1 for s in opps if my_pts == s) / d

            # best ball: optimal score for each team
            if has_bb and wk_stats and wk_roster:
                for m in wk_entry.get("matchups", []):
                    if m.get("is_consolation"): continue
                    teams = m.get("teams", [])
                    if len(teams) != 2: continue
                    mid1 = teams[0].get("manager_id") or ""
                    mid2 = teams[1].get("manager_id") or ""
                    if not mid1 or not mid2: continue
                    bb1 = optimal_score(mid1, wk_roster, wk_stats, yr_info, yr_rules)
                    bb2 = optimal_score(mid2, wk_roster, wk_stats, yr_info, yr_rules)
                    if bb1 is None or bb2 is None: continue
                    for mid, bb, opp_bb in [(mid1,bb1,bb2),(mid2,bb2,bb1)]:
                        if mid not in yr_bb: continue
                        yr_bb[mid]["pf"] = round(yr_bb[mid]["pf"] + bb,     2)
                        yr_bb[mid]["pa"] = round(yr_bb[mid]["pa"] + opp_bb, 2)
                    if   bb1 > bb2: yr_bb[mid1]["w"]+=1; yr_bb[mid2]["l"]+=1
                    elif bb2 > bb1: yr_bb[mid2]["w"]+=1; yr_bb[mid1]["l"]+=1
                    else:           yr_bb[mid1]["t"]+=1; yr_bb[mid2]["t"]+=1

        # ── assemble per-season rows ──────────────────────────────────────────
        for mid, m in managers.items():
            rs = m.get("regular_season", {})
            po = m.get("playoffs", {}) or m.get("playoff", {})

            rs_w = rs.get("wins")    or 0
            rs_l = rs.get("losses")  or 0
            rs_t = rs.get("ties")    or 0
            rs_g = rs_w + rs_l + rs_t
            pf   = rs.get("points_for")            or 0.0
            pa   = rs.get("points_against")        or 0.0
            ppf  = rs.get("projected_points_for")  or 0.0
            ppa  = rs.get("projected_points_against") or 0.0

            po_made = po.get("made_playoffs", False)
            po_w    = (po.get("wins")   or 0) if po_made else 0
            po_l    = (po.get("losses") or 0) if po_made else 0
            po_t    = (po.get("ties")   or 0) if po_made else 0
            po_g    = po_w + po_l + po_t
            po_pf   = (po.get("points_for")            or 0.0) if po_made else 0.0
            po_pa   = (po.get("points_against")        or 0.0) if po_made else 0.0
            po_ppf  = (po.get("projected_points_for")  or 0.0) if po_made else 0.0
            po_ppa  = (po.get("projected_points_against") or 0.0) if po_made else 0.0

            th  = yr_theo.get(mid, {"w":0.0,"l":0.0,"t":0.0})
            bb  = yr_bb.get(mid, {"w":0,"l":0,"t":0,"pf":0.0,"pa":0.0})
            bb_g= bb["w"] + bb["l"] + bb["t"]

            season_rows[yr][mid] = {
                "display_name": m.get("display_name") or mid.title(),
                # raw values for aggregation
                "_rs": {"w":rs_w,"l":rs_l,"t":rs_t,"g":rs_g,
                         "pf":pf,"pa":pa,"ppf":ppf,"ppa":ppa,
                         "rank":rs.get("rank"),
                         "pf_rank":rs.get("points_for_rank"),
                         "pa_rank":rs.get("points_against_rank")},
                "_po": {"made":po_made,"w":po_w,"l":po_l,"t":po_t,"g":po_g,
                         "pf":po_pf,"pa":po_pa,"ppf":po_ppf,"ppa":po_ppa,
                         "finish":po.get("finish"),
                         "pf_rank":po.get("points_for_rank"),
                         "pa_rank":po.get("points_against_rank")},
                "_th": {"w":round(th["w"],2),"l":round(th["l"],2),"t":round(th["t"],2)},
                "_bb": {"w":bb["w"],"l":bb["l"],"t":bb["t"],"g":bb_g,
                         "pf":round(bb["pf"],2),"pa":round(bb["pa"],2),
                         "has_data":has_bb},
            }

            # accumulate into each active era
            for era in active_eras:
                a = era_acc[era][mid]
                a["rs_w"]      += rs_w; a["rs_l"]      += rs_l; a["rs_t"] += rs_t
                a["rs_g"]      += rs_g; a["rs_seasons"] += 1
                a["rs_pf"]      = round(a["rs_pf"]  + pf,  2)
                a["rs_pa"]      = round(a["rs_pa"]  + pa,  2)
                a["rs_proj_pf"] = round(a["rs_proj_pf"] + ppf, 2)
                a["rs_proj_pa"] = round(a["rs_proj_pa"] + ppa, 2)
                if po_made:
                    a["po_apps"] += 1
                    a["po_w"] += po_w; a["po_l"] += po_l; a["po_t"] += po_t
                    a["po_g"] += po_g
                    a["po_pf"]      = round(a["po_pf"]     + po_pf,  2)
                    a["po_pa"]      = round(a["po_pa"]     + po_pa,  2)
                    a["po_proj_pf"] = round(a["po_proj_pf"]+ po_ppf, 2)
                    a["po_proj_pa"] = round(a["po_proj_pa"]+ po_ppa, 2)
                    if po.get("finish"):
                        a["po_finishes"].append({"year":yr_int,"finish":po["finish"]})
                a["th_w"] = round(a["th_w"] + th["w"], 4)
                a["th_l"] = round(a["th_l"] + th["l"], 4)
                a["th_t"] = round(a["th_t"] + th["t"], 4)
                if has_bb:
                    a["bb_w"] += bb["w"]; a["bb_l"] += bb["l"]; a["bb_t"] += bb["t"]
                    a["bb_g"] += bb_g
                    a["bb_pf"]  = round(a["bb_pf"] + bb["pf"], 2)
                    a["bb_pa"]  = round(a["bb_pa"] + bb["pa"], 2)
                    a["bb_seasons"] += 1

    # ── format helpers ────────────────────────────────────────────────────────

    def fmt_era_manager(mid: str, a: dict) -> dict:
        """Format one manager's era/overall accumulator into output block."""
        rs_g = a["rs_g"] or 1
        rs_s = a["rs_seasons"] or 1
        po_g = a["po_g"] or 1
        bb_g = a["bb_g"] or 1
        bb_s = a["bb_seasons"] or 1

        rs_wp  = round(a["rs_w"] / rs_g, 4)
        th_wp  = round(a["th_w"] / rs_g, 4)
        bb_wp  = round(a["bb_w"] / bb_g, 4) if bb_g else None
        luck   = round(a["rs_w"] - a["th_w"], 2)
        bb_diff= a["bb_w"] - a["rs_w"]

        return {
            "actual": {
                "total": {
                    "w":     a["rs_w"],   "l": a["rs_l"],   "t": a["rs_t"],
                    "games": a["rs_g"],   "seasons": a["rs_seasons"],
                    "win_pct": rs_wp,
                    "pf":      round(a["rs_pf"], 2),
                    "pa":      round(a["rs_pa"], 2),
                    "proj_pf": round(a["rs_proj_pf"], 2),
                    "proj_pa": round(a["rs_proj_pa"], 2),
                },
                "per_season": {
                    "w":     round(a["rs_w"] / rs_s, 2),
                    "l":     round(a["rs_l"] / rs_s, 2),
                    "t":     round(a["rs_t"] / rs_s, 2),
                    "pf_avg":     round(a["rs_pf"]      / rs_g, 2),
                    "pa_avg":     round(a["rs_pa"]      / rs_g, 2),
                    "proj_pf_avg":round(a["rs_proj_pf"] / rs_g, 2),
                    "proj_pa_avg":round(a["rs_proj_pa"] / rs_g, 2),
                    "pf_proj_diff":  round((a["rs_pf"]  - a["rs_proj_pf"])  / rs_g, 2),
                    "pa_proj_diff":  round((a["rs_pa"]  - a["rs_proj_pa"])  / rs_g, 2),
                },
                "playoffs": {
                    "appearances": a["po_apps"],
                    "w": a["po_w"], "l": a["po_l"], "t": a["po_t"],
                    "games": a["po_g"],
                    "win_pct": round(a["po_w"] / po_g, 4) if a["po_g"] else None,
                    "pf_avg":  round(a["po_pf"]      / po_g, 2) if a["po_g"] else None,
                    "pa_avg":  round(a["po_pa"]      / po_g, 2) if a["po_g"] else None,
                    "proj_pf_avg": round(a["po_proj_pf"] / po_g, 2) if a["po_g"] else None,
                    "proj_pa_avg": round(a["po_proj_pa"] / po_g, 2) if a["po_g"] else None,
                    "championships":  sum(1 for f in a["po_finishes"] if f["finish"]==1),
                    "runner_up":      sum(1 for f in a["po_finishes"] if f["finish"]==2),
                    "third_place":    sum(1 for f in a["po_finishes"] if f["finish"]==3),
                    "champ_years":    sorted([f["year"] for f in a["po_finishes"] if f["finish"]==1]),
                },
            },
            "theoretical": {
                "total": {
                    "w":      round(a["th_w"], 2),
                    "l":      round(a["th_l"], 2),
                    "t":      round(a["th_t"], 2),
                    "win_pct":th_wp,
                    "luck_total": luck,
                    "luck_label": "lucky" if luck > 0 else ("unlucky" if luck < 0 else "neutral"),
                },
                "per_season": {
                    "w":   round(a["th_w"] / rs_s, 2),
                    "l":   round(a["th_l"] / rs_s, 2),
                    "t":   round(a["th_t"] / rs_s, 2),
                    "luck":round(luck / rs_s, 2),
                },
            },
            "best_ball": {
                "total": {
                    "w":      a["bb_w"],
                    "l":      a["bb_l"],
                    "t":      a["bb_t"],
                    "games":  a["bb_g"],
                    "seasons_with_data": a["bb_seasons"],
                    "win_pct":bb_wp,
                    "bb_pf":  round(a["bb_pf"], 2),
                    "bb_pa":  round(a["bb_pa"], 2),
                    "bb_win_diff": bb_diff,
                    "bb_win_diff_label": f"+{bb_diff}" if bb_diff > 0 else str(bb_diff),
                    "pf_bb_actual_diff": round(a["bb_pf"] - a["rs_pf"], 2) if a["bb_pf"] else None,
                    "pa_bb_actual_diff": round(a["bb_pa"] - a["rs_pa"], 2) if a["bb_pa"] else None,
                } if a["bb_g"] else {"note": "no best ball data for this era"},
                "per_season": {
                    "w":     round(a["bb_w"] / bb_s, 2),
                    "l":     round(a["bb_l"] / bb_s, 2),
                    "t":     round(a["bb_t"] / bb_s, 2),
                    "bb_pf_avg": round(a["bb_pf"] / bb_g, 2),
                    "bb_pa_avg": round(a["bb_pa"] / bb_g, 2),
                    "bb_diff":   round(bb_diff / bb_s, 2),
                    "bb_pf_diff":round((a["bb_pf"] - a["rs_pf"]) / bb_g, 2) if bb_g else None,
                } if a["bb_seasons"] else {"note": "no best ball data for this era"},
            },
        }

    def fmt_season_manager(mid: str, row: dict, yr_int: int) -> dict:
        """Format one manager's season row into output block."""
        rs = row["_rs"]; po = row["_po"]
        th = row["_th"]; bb = row["_bb"]
        rs_g = rs["g"] or 1
        po_g = po["g"] or 1
        bb_g = bb["g"] or 1

        rs_wp  = round(rs["w"] / rs_g, 4)
        th_wp  = round(th["w"] / rs_g, 4)
        bb_wp  = round(bb["w"] / bb_g, 4) if bb_g else None
        luck   = round(rs["w"] - th["w"], 2)
        bb_diff= bb["w"] - rs["w"]

        return {
            "actual": {
                "total": {
                    "w": rs["w"], "l": rs["l"], "t": rs["t"], "games": rs_g,
                    "win_pct":    rs_wp,
                    "rank":       rs["rank"],
                    "pf":         round(rs["pf"],  2),
                    "pf_avg":     round(rs["pf"] / rs_g, 2),
                    "pf_rank":    rs["pf_rank"],
                    "proj_pf":    round(rs["ppf"], 2),
                    "proj_pf_avg":round(rs["ppf"] / rs_g, 2),
                    "pf_proj_diff":round((rs["pf"] - rs["ppf"]) / rs_g, 2),
                    "pa":         round(rs["pa"],  2),
                    "pa_avg":     round(rs["pa"] / rs_g, 2),
                    "pa_rank":    rs["pa_rank"],
                    "proj_pa":    round(rs["ppa"], 2),
                    "proj_pa_avg":round(rs["ppa"] / rs_g, 2),
                    "pa_proj_diff":round((rs["pa"] - rs["ppa"]) / rs_g, 2),
                },
                "playoffs": {
                    "made_playoffs": po["made"],
                    "finish":        po["finish"],
                    "w": po["w"], "l": po["l"], "t": po["t"],
                    "pf_avg":  round(po["pf"]  / po_g, 2) if po["g"] else None,
                    "pa_avg":  round(po["pa"]  / po_g, 2) if po["g"] else None,
                    "pf_rank": po["pf_rank"],
                    "pa_rank": po["pa_rank"],
                    "proj_pf_avg": round(po["ppf"] / po_g, 2) if po["g"] else None,
                    "proj_pa_avg": round(po["ppa"] / po_g, 2) if po["g"] else None,
                    "pf_proj_diff": round((po["pf"] - po["ppf"]) / po_g, 2) if po["g"] else None,
                },
            },
            "theoretical": {
                "total": {
                    "w":       th["w"], "l": th["l"], "t": th["t"],
                    "win_pct": th_wp,
                    "luck":    luck,
                    "luck_label": "lucky" if luck > 0 else ("unlucky" if luck < 0 else "neutral"),
                },
            },
            "best_ball": {
                "total": {
                    "w": bb["w"], "l": bb["l"], "t": bb["t"],
                    "win_pct":        bb_wp,
                    "bb_pf_avg":      round(bb["pf"] / bb_g, 2) if bb_g else None,
                    "bb_pa_avg":      round(bb["pa"] / bb_g, 2) if bb_g else None,
                    "bb_win_diff":    bb_diff,
                    "bb_win_diff_label": f"+{bb_diff}" if bb_diff > 0 else str(bb_diff),
                    "pf_bb_actual_diff": round(bb["pf"] - rs["pf"], 2) if bb_g else None,
                    "data_available": bb["has_data"],
                } if bb["has_data"] else {"data_available": False},
            },
        }

    # ── playoff helpers ───────────────────────────────────────────────────────

    def playoff_summary(yr: str, managers: dict, yr_theo: dict,
                        yr_bb: dict, has_bb: bool) -> dict:
        """
        For one season, compute actual / theoretical / bb playoff pictures.
        actual_top4:    managers with regular_season.rank <= 4
        theo_top4:      top 4 by theoretical wins (tiebreak: actual pf)
        bb_top4:        top 4 by bb wins (tiebreak: bb pf) — if has_bb
        Returns gained/lost for theo and bb vs actual.
        """
        rows = season_rows[yr]

        actual_top4 = {mid for mid, m in managers.items()
                       if (m.get("regular_season",{}).get("rank") or 99) <= 4}

        # theoretical top 4
        theo_sorted = sorted(
            [(mid, yr_theo.get(mid,{"w":0,"l":0,"t":0})) for mid in managers],
            key=lambda x: (-x[1]["w"], -(rows[x[0]]["_rs"]["pf"] if x[0] in rows else 0))
        )
        theo_top4 = {mid for mid, _ in theo_sorted[:4]}

        def mgr_entry(mid):
            return {
                "manager_id":   mid,
                "display_name": managers[mid].get("display_name") or mid.title(),
                "rs_rank":      managers[mid].get("regular_season",{}).get("rank"),
                "rs_pf":        round(rows[mid]["_rs"]["pf"],2) if mid in rows else None,
                "theo_w":       round(yr_theo.get(mid,{}).get("w",0),2),
                "bb_w":         yr_bb.get(mid,{}).get("w",0) if has_bb else None,
            }

        theo_gained = [mgr_entry(m) for m in (theo_top4 - actual_top4)]
        theo_lost   = [mgr_entry(m) for m in (actual_top4 - theo_top4)]

        result = {
            "actual_top4":  sorted([mgr_entry(m) for m in actual_top4],
                                    key=lambda x: x["rs_rank"] or 99),
            "theoretical_top4": sorted([mgr_entry(m) for m in theo_top4],
                                         key=lambda x: -x["theo_w"]),
            "theo_gained":  theo_gained,
            "theo_lost":    theo_lost,
            "theo_changed": bool(theo_gained or theo_lost),
        }

        if has_bb:
            bb_sorted = sorted(
                [(mid, yr_bb.get(mid,{"w":0,"pf":0})) for mid in managers],
                key=lambda x: (-x[1]["w"], -x[1].get("pf",0))
            )
            bb_top4   = {mid for mid, _ in bb_sorted[:4]}
            bb_gained = [mgr_entry(m) for m in (bb_top4 - actual_top4)]
            bb_lost   = [mgr_entry(m) for m in (actual_top4 - bb_top4)]
            result.update({
                "bb_top4":     sorted([mgr_entry(m) for m in bb_top4],
                                       key=lambda x: -(x["bb_w"] or 0)),
                "bb_gained":   bb_gained,
                "bb_lost":     bb_lost,
                "bb_changed":  bool(bb_gained or bb_lost),
            })

        return result

    # ── assemble output ───────────────────────────────────────────────────────

    # ERA blocks
    era_out: dict = {}
    for era, (era_s, era_e) in ERAS.items():
        mgr_blocks: dict = {}
        for mid in all_mids:
            a = era_acc[era][mid]
            if a["rs_seasons"] == 0:
                continue   # manager didn't play in this era
            mgr_blocks[mid] = {
                "manager_id":   mid,
                "display_name": dn(mid, results),
                **fmt_era_manager(mid, a),
            }

        # Add cross-manager rankings within this era
        for rank_key, field, higher in [
            ("win_rank",    "actual.total.win_pct",   True),
            ("pf_rank",     "actual.total.pf",        True),
            ("pa_rank",     "actual.total.pa",        False),
            ("theo_win_rank","theoretical.total.win_pct", True),
            ("bb_win_rank", "best_ball.total.win_pct", True),
        ]:
            valid = [(mid, m) for mid, m in mgr_blocks.items()]
            def _get(m, field):
                parts = field.split(".")
                v = m
                for p in parts:
                    if not isinstance(v, dict): return None
                    v = v.get(p)
                return v
            ranked = sorted(valid, key=lambda x: -(_get(x[1], field) or 0)
                            if higher else (_get(x[1], field) or 0))
            for rank, (mid, _) in enumerate(ranked, 1):
                # embed rank into the right nested location
                top, sub = field.rsplit(".", 1) if "." in field else ("", field)
                parts = top.split(".")
                target = mgr_blocks[mid]
                for p in parts:
                    if p: target = target.get(p, {})
                if isinstance(target, dict):
                    target[rank_key] = rank

        era_out[era] = mgr_blocks

    # SEASON blocks
    season_out: dict = {}
    for yr in sorted(season_rows.keys(), key=int):
        yr_int   = int(yr)
        managers = finished[yr].get("managers", {})
        yr_mu    = matchups.get(yr, {})
        yr_stats = player_stats.get(yr, {})
        yr_info  = (player_info.get(yr, {}) or {}).get("players", {})
        has_bb   = bool(yr_stats and yr_info)

        # Rebuild per-season theo/bb for playoff summary
        # (already computed above — extract from season_rows)
        yr_theo_rebuilt = {mid: row["_th"] for mid, row in season_rows[yr].items()}
        yr_bb_rebuilt   = {mid: row["_bb"] for mid, row in season_rows[yr].items()}

        mgr_season: dict = {}
        for mid, row in season_rows[yr].items():
            mgr_season[mid] = {
                "manager_id":   mid,
                "display_name": row["display_name"],
                **fmt_season_manager(mid, row, yr_int),
            }

        # Cross-season rankings
        rs_sorted = sorted(mgr_season.items(),
                           key=lambda x: x[1]["actual"]["total"].get("win_pct") or 0,
                           reverse=True)
        for rank, (mid, _) in enumerate(rs_sorted, 1):
            mgr_season[mid]["actual"]["total"]["win_rank"] = rank

        season_out[yr] = {
            "managers":        mgr_season,
            "playoff_picture": playoff_summary(
                yr, managers, yr_theo_rebuilt, yr_bb_rebuilt, has_bb
            ),
        }

    return {
        "era_blocks":  era_out,    # keyed by era name
        "seasons":     season_out, # keyed by year string
    }


# ── ice records builder ───────────────────────────────────────────────────────

def build_ice_records(results: dict, ices: dict) -> dict:
    """
    Ice records structured parallel to wl_records:
      era_blocks: { era: { mid: { totals: {...pos counts...} } } }
      seasons:    { yr:  { is_real, managers: { mid: { totals } } } }

    Real ices: 2023+ (managers actually owed a Smirnoff Ice)
    Theoretical: all years (retroactively applied)

    Position keys tracked: QB, WR, RB, TE, K, DEF, plus total.
    Each position has _real_count and _theo_count at era level.
    At season level: just _count (real OR theo depending on year).
    """
    REAL_ICE_START = 2023
    POSITIONS      = ["QB", "WR", "RB", "TE", "K", "DEF"]

    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}
    all_mids = set()
    for yr in finished:
        all_mids.update(finished[yr].get("managers", {}).keys())

    # ── accumulate per-season ice counts ─────────────────────────────────────
    # season_ice[yr][mid] = {pos: count, "total": count, "is_real": bool}
    season_ice: dict = {}

    for yr, yr_ices in ices.items():
        if yr not in finished:           continue
        if not isinstance(yr_ices, list): continue
        yr_int  = int(yr)
        is_real = yr_int >= REAL_ICE_START
        season_ice[yr] = {"is_real": is_real, "managers": {}}

        for ice in yr_ices:
            if ice.get("is_playoffs"):   continue   # regular season only
            mid = ice.get("manager_id") or ""
            pos = (ice.get("position") or "").strip().upper()
            if not mid: continue

            if mid not in season_ice[yr]["managers"]:
                season_ice[yr]["managers"][mid] = {
                    "display_name": dn(mid, results),
                    "total":        0,
                    **{p: 0 for p in POSITIONS},
                }
            s = season_ice[yr]["managers"][mid]
            s["total"] += 1
            if pos in POSITIONS:
                s[pos] += 1

    # ── accumulate into era blocks ────────────────────────────────────────────
    # era_acc[era][mid] = {pos_real, pos_theo, total_real, total_theo}
    era_acc: dict = {era: {} for era in ERAS}

    def blank_era():
        d = {"total_real": 0, "total_theo": 0}
        for p in POSITIONS:
            d[f"{p}_real"] = 0
            d[f"{p}_theo"] = 0
        return d

    for yr, yr_data in season_ice.items():
        yr_int   = int(yr)
        is_real  = yr_data["is_real"]
        active   = [era for era, (s, e) in ERAS.items() if s <= yr_int <= e]

        for mid, mgr_data in yr_data["managers"].items():
            for era in active:
                if mid not in era_acc[era]:
                    era_acc[era][mid] = blank_era()
                a = era_acc[era][mid]
                # always accumulate theoretical
                a["total_theo"] += mgr_data["total"]
                for p in POSITIONS:
                    a[f"{p}_theo"] += mgr_data.get(p, 0)
                # only accumulate real for 2023+
                if is_real:
                    a["total_real"] += mgr_data["total"]
                    for p in POSITIONS:
                        a[f"{p}_real"] += mgr_data.get(p, 0)

    # ── format era output ─────────────────────────────────────────────────────
    def fmt_era_mgr_ice(mid: str, a: dict) -> dict:
        totals = {
            "real_ice_count":  a["total_real"],
            "theo_ice_count":  a["total_theo"],
        }
        for p in POSITIONS:
            totals[f"{p.lower()}_real_count"] = a[f"{p}_real"]
            totals[f"{p.lower()}_theo_count"] = a[f"{p}_theo"]
        return {
            "manager_id":   mid,
            "display_name": dn(mid, results),
            "totals":       totals,
        }

    era_out: dict = {}
    for era in ERAS:
        era_mgrs = {}
        for mid in all_mids:
            if mid not in era_acc[era]: continue
            a = era_acc[era][mid]
            if a["total_theo"] == 0:    continue   # no ices in this era
            era_mgrs[mid] = fmt_era_mgr_ice(mid, a)
        # sort by theoretical ice count desc
        era_out[era] = dict(
            sorted(era_mgrs.items(),
                   key=lambda x: -x[1]["totals"]["theo_ice_count"])
        )

    # ── format season output ──────────────────────────────────────────────────
    season_out: dict = {}
    for yr in sorted(season_ice.keys(), key=int):
        yr_data  = season_ice[yr]
        is_real  = yr_data["is_real"]
        mgr_out  = {}
        for mid, mgr_data in sorted(yr_data["managers"].items(),
                                     key=lambda x: -x[1]["total"]):
            totals = {"ice_count": mgr_data["total"]}
            for p in POSITIONS:
                v = mgr_data.get(p, 0)
                if v > 0:
                    totals[f"{p.lower()}_count"] = v
            mgr_out[mid] = {
                "manager_id":   mid,
                "display_name": mgr_data["display_name"],
                "totals":       totals,
            }
        season_out[yr] = {
            "ice_type": "real" if is_real else "theoretical",
            "managers": mgr_out,
        }

    return {"era_blocks": era_out, "seasons": season_out}


# ── championship players builder ──────────────────────────────────────────────

def build_championship_players(results: dict, rosters: dict,
                                player_info: dict) -> list:
    """
    Players on championship rosters, weighted:
      starter = 5pts, bench = 3pts, IR = 1pt
    Only players on 2+ championship rosters included.
    Capped at top 10 by weighted score.
    Name-matched across seasons (player_key changes year to year).
    """
    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    champ_players: dict = {}   # player_name → {weight, appearances, position, years}

    for yr, season in finished.items():
        champ_mid = None
        for mid, m in season.get("managers", {}).items():
            po = m.get("playoffs", {}) or m.get("playoff", {})
            if po.get("finish") == 1:
                champ_mid = mid
                break
        if not champ_mid: continue

        yr_roster = rosters.get(yr, {})
        yr_info   = (player_info.get(yr, {}) or {}).get("players", {})
        wk_keys   = sorted([k for k in yr_roster if k.startswith("week_")],
                            key=lambda x: int(x.split("_")[1]))
        if not wk_keys: continue

        slots = yr_roster.get(wk_keys[-1], {}).get(champ_mid, {}).get("players", [])
        for slot in slots:
            if not isinstance(slot, dict): continue
            pk = slot.get("player_key") or ""
            pi = yr_info.get(pk, {})
            nm = (pi.get("name") or "").strip()
            if not nm: continue
            if slot.get("is_on_ir"):       weight = 1
            elif slot.get("is_starting"):  weight = 5
            else:                          weight = 3

            if nm not in champ_players:
                champ_players[nm] = {
                    "weight": 0, "appearances": 0,
                    "position": pi.get("position"), "years": [],
                }
            champ_players[nm]["weight"]      += weight
            champ_players[nm]["appearances"] += 1
            champ_players[nm]["years"].append(int(yr))

    top10 = sorted(
        [(nm, v) for nm, v in champ_players.items() if v["appearances"] >= 2],
        key=lambda x: -x[1]["weight"]
    )[:10]

    return [
        {
            "player_name":   nm,
            "position":      v["position"],
            "appearances":   v["appearances"],
            "weighted_score":v["weight"],
            "years":         sorted(v["years"]),
            "note":          "starter=5pts, bench=3pts, IR=1pt per championship appearance",
        }
        for nm, v in top10
    ]


# ── top draft picks builder ───────────────────────────────────────────────────

def build_top_draft_picks(results: dict, drafts: dict) -> list:
    """
    Most frequently appearing players in "key picks":
      Snake:   round 1 picks
      Auction: top 10 cost picks per draft

    Name-matched across seasons. Returns top 10 by count (min 2 appearances).
    Each entry includes player name, count, years, positions seen.
    """
    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    pick_counts: dict = {}   # player_name → {count, years, positions}

    for yr, yr_draft in drafts.items():
        if yr not in finished: continue
        draft_type = yr_draft.get("draft_type", "snake")
        picks      = yr_draft.get("picks", [])
        yr_int     = int(yr)

        if draft_type == "snake":
            key_picks = [p for p in picks if (p.get("round") or 0) == 1]
        else:
            valid = [p for p in picks if p.get("cost")]
            valid.sort(key=lambda x: -(x.get("cost") or 0))
            key_picks = valid[:10]

        for p in key_picks:
            nm  = (p.get("player_name") or "").strip()
            pos = (p.get("position")    or "").strip()
            if not nm: continue
            if nm not in pick_counts:
                pick_counts[nm] = {"count": 0, "years": [], "positions": set()}
            pick_counts[nm]["count"]      += 1
            pick_counts[nm]["years"].append(yr_int)
            if pos: pick_counts[nm]["positions"].add(pos)

    top10 = sorted(
        [(nm, v) for nm, v in pick_counts.items() if v["count"] >= 2],
        key=lambda x: -x[1]["count"]
    )[:10]

    return [
        {
            "player_name": nm,
            "count":       v["count"],
            "years":       sorted(v["years"]),
            "positions":   sorted(v["positions"]),
        }
        for nm, v in top10
    ]




# ── bar chart race ────────────────────────────────────────────────────────────

def build_bar_chart_race(results: dict) -> list:
    """Cumulative RS wins per manager per season — ALL managers."""
    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}
    all_mids = set()
    for yr in finished:
        all_mids.update(finished[yr].get("managers", {}).keys())

    cumulative: dict = {mid: 0 for mid in all_mids}
    race: list = []
    for yr in sorted(finished.keys(), key=int):
        for mid, m in finished[yr].get("managers", {}).items():
            cumulative[mid] = cumulative.get(mid, 0) + (
                m.get("regular_season", {}).get("wins") or 0)
        race.append({"year": int(yr),
                     "totals": {mid: cumulative.get(mid, 0) for mid in all_mids}})
    return race


# ── trade records ─────────────────────────────────────────────────────────────

def build_trade_records(results: dict, transactions: dict) -> dict:
    """Most common trade partners + most traded players, per era. All managers."""
    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    def _compute(start_yr: int, end_yr: int) -> dict:
        pairs: dict = {}
        traded: dict = {}
        for yr, yr_tx in transactions.items():
            if not (start_yr <= int(yr) <= end_yr): continue
            if yr not in finished: continue
            for trade in yr_tx.get("trades", []):
                m1 = trade.get("manager_a") or trade.get("trader_manager") or ""
                m2 = trade.get("manager_b") or trade.get("tradee_manager") or ""
                if m1 and m2:
                    key = tuple(sorted([m1, m2]))
                    pairs[key] = pairs.get(key, 0) + 1
                for side in ["a_received","b_received","trader_receives","tradee_receives"]:
                    for p in trade.get(side, []):
                        nm  = (p.get("name") or p.get("player_name") or "").strip()
                        pos = p.get("position") or ""
                        if nm and pos not in ("DEF","D/ST","K"):
                            traded[nm] = traded.get(nm, 0) + 1
        return {
            "top_partners": sorted([
                {"manager_1": {"manager_id": p[0], "display_name": dn(p[0], results)},
                 "manager_2": {"manager_id": p[1], "display_name": dn(p[1], results)},
                 "total_trades": cnt}
                for p, cnt in pairs.items()], key=lambda x: -x["total_trades"])[:10],
            "most_traded_players": sorted([
                {"player_name": nm, "times_in_trades": cnt}
                for nm, cnt in traded.items() if cnt >= 2],
                key=lambda x: -x["times_in_trades"])[:10],
        }
    return {era: _compute(s, e) for era, (s, e) in ERAS.items()}


# ── scoring records ───────────────────────────────────────────────────────────

def build_scoring_records(results: dict, matchups: dict,
                           player_stats: dict, player_info: dict,
                           rosters: dict) -> dict:
    """top/bottom PF + position records per era. KNOWN_MEMBERS only."""
    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    def _compute(start_yr: int, end_yr: int) -> dict:
        all_weekly: list = []
        all_season: list = []
        pos_week:   dict = {"QB":[],"WR":[],"RB":[],"TE":[]}
        pos_season: dict = {"QB":[],"WR":[],"RB":[],"TE":[]}

        for yr, season in finished.items():
            yr_int = int(yr)
            if not (start_yr <= yr_int <= end_yr): continue
            yr_mu    = matchups.get(yr, {})
            ps       = yr_mu.get("playoff_start") or 99
            yr_stats = player_stats.get(yr, {})
            yr_info  = (player_info.get(yr, {}) or {}).get("players", {})
            yr_roster= rosters.get(yr, {})

            # owner map
            owner_map: dict = {}
            wk_keys_r = sorted([k for k in yr_roster if k.startswith("week_")],
                                 key=lambda x: int(x.split("_")[1]))
            if wk_keys_r:
                lw = yr_roster.get(wk_keys_r[-1], {})
                for mid, team in lw.items():
                    if not isinstance(team, dict): continue
                    for slot in team.get("players", []):
                        pk = slot.get("player_key") if isinstance(slot, dict) else None
                        if pk: owner_map[pk] = {"manager_id": mid, "display_name": dn(mid, results)}

            # weekly PF
            mgr_szn: dict = {}
            for wk_entry in yr_mu.get("weeks", []):
                wk_num = wk_entry.get("week", 0)
                if wk_num >= ps: continue
                for m in wk_entry.get("matchups", []):
                    for t in m.get("teams", []):
                        mid = t.get("manager_id") or ""
                        if mid not in KNOWN_MEMBERS: continue
                        try: pts = float(t.get("points") or 0)
                        except: continue
                        if pts <= 0: continue
                        all_weekly.append({"manager_id":mid,"display_name":dn(mid,results),
                                           "year":yr_int,"week":wk_num,"points":round(pts,2)})
                        mgr_szn[mid] = round(mgr_szn.get(mid, 0) + pts, 2)

            for mid, pts in mgr_szn.items():
                rs = season.get("managers",{}).get(mid,{}).get("regular_season",{})
                g  = rs.get("games") or 1
                all_season.append({"manager_id":mid,"display_name":dn(mid,results),
                                   "year":yr_int,"total_pf":round(pts,2),
                                   "avg_pf":round(pts/g,2)})

            # position records
            if not yr_stats or not yr_info: continue
            yr_ps: dict = {}
            for wk_key, wk_data in yr_stats.items():
                if not isinstance(wk_data, dict): continue
                wk_num = int(wk_key.split("_")[1])
                if wk_num >= ps: continue
                for pk, pd in wk_data.items():
                    if not isinstance(pd, dict): continue
                    try: fp = float(pd.get("fantasy_points") or 0)
                    except: continue
                    if fp <= 0: continue
                    pi  = yr_info.get(pk, {})
                    pos_raw = pi.get("position") or ""
                    pos = pos_raw.split("/")[0].strip() if "/" in pos_raw else pos_raw
                    if pos not in pos_week: continue
                    nm    = pi.get("name") or pk
                    owner = owner_map.get(pk, {})
                    mid   = owner.get("manager_id") or ""
                    if mid and mid not in KNOWN_MEMBERS: continue
                    pos_week[pos].append({"player_name":nm,"position":pos,
                                          "manager_id":mid,"display_name":owner.get("display_name"),
                                          "year":yr_int,"week":wk_num,"points":round(fp,2)})
                    yr_ps.setdefault(pk, {"nm":nm,"pos":pos,"pts":0.0,"owner":owner})
                    yr_ps[pk]["pts"] += fp

            for pk, info in yr_ps.items():
                pos = info["pos"]
                if pos not in pos_season: continue
                mid = info["owner"].get("manager_id") or ""
                if mid and mid not in KNOWN_MEMBERS: continue
                pos_season[pos].append({"player_name":info["nm"],"position":pos,
                                        "manager_id":mid,"display_name":info["owner"].get("display_name"),
                                        "year":yr_int,"season_pts":round(info["pts"],2)})

        all_weekly.sort(key=lambda x: -x["points"])
        all_season.sort(key=lambda x: -x["total_pf"])
        return {
            "top10_weekly_pf":    all_weekly[:10],
            "bottom10_weekly_pf": list(reversed(all_weekly[-10:])) if len(all_weekly)>=10 else list(reversed(all_weekly)),
            "top10_season_pf":    all_season[:10],
            "bottom10_season_pf": list(reversed(all_season[-10:])) if len(all_season)>=10 else list(reversed(all_season)),
            "position_week_records":   {pos: sorted(v, key=lambda x: -x["points"])[:10]   for pos, v in pos_week.items()},
            "position_season_records": {pos: sorted(v, key=lambda x: -x["season_pts"])[:10] for pos, v in pos_season.items()},
        }

    return {era: _compute(s, e) for era, (s, e) in ERAS.items()}


# ── manager records ───────────────────────────────────────────────────────────

def build_mgr_records(results: dict, rosters: dict,
                       player_stats: dict, player_info: dict) -> dict:
    """best/worst season + player_mgr_combo. KNOWN_MEMBERS only. Not era-specific."""
    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}
    best: dict = {}; worst: dict = {}
    mgr_player_wks: dict = {}

    for yr, season in finished.items():
        yr_int   = int(yr)
        yr_info  = (player_info.get(yr, {}) or {}).get("players", {})
        yr_roster= rosters.get(yr, {})
        for mid, m in season.get("managers", {}).items():
            if mid not in KNOWN_MEMBERS: continue
            rs = m.get("regular_season", {})
            wp = rs.get("win_pct") or 0
            g  = (rs.get("wins") or 0)+(rs.get("losses") or 0)+(rs.get("ties") or 0)
            rec = {"year":yr_int,"wins":rs.get("wins"),"losses":rs.get("losses"),
                   "ties":rs.get("ties",0),"win_pct":round(wp,4),
                   "avg_pf":round(rs.get("avg_points_for") or 0,2),"rank":rs.get("rank")}
            if mid not in best  or wp > best[mid]["win_pct"]:
                best[mid]  = {"manager_id":mid,"display_name":dn(mid,results),**rec}
            if g >= 10 and (mid not in worst or wp < worst[mid]["win_pct"]):
                worst[mid] = {"manager_id":mid,"display_name":dn(mid,results),**rec}

        for wk_key, wk_data in yr_roster.items():
            if not wk_key.startswith("week_") or not isinstance(wk_data, dict): continue
            for mid, team in wk_data.items():
                if mid not in KNOWN_MEMBERS or not isinstance(team, dict): continue
                for slot in team.get("players", []):
                    if not isinstance(slot, dict): continue
                    pk = slot.get("player_key") or ""
                    pi = yr_info.get(pk, {})
                    nm = (pi.get("name") or "").strip()
                    if nm: mgr_player_wks[(mid, nm)] = mgr_player_wks.get((mid, nm), 0) + 1

    return {
        "best_season_per_manager":  sorted(best.values(),  key=lambda x: -x["win_pct"]),
        "worst_season_per_manager": sorted(worst.values(), key=lambda x:  x["win_pct"]),
        "player_mgr_combo": sorted(
            [{"manager_id":mid,"display_name":dn(mid,results),"player_name":nm,
              "weeks_together":wks,"approx_seasons":round(wks/16,1)}
             for (mid,nm),wks in mgr_player_wks.items() if mid in KNOWN_MEMBERS],
            key=lambda x: -x["weeks_together"])[:10],
    }


# ── FAAB + auction ────────────────────────────────────────────────────────────

def build_faab_auction(results: dict, transactions: dict, drafts: dict) -> dict:
    """FAAB + auction records per era. KNOWN_MEMBERS only."""
    FAAB_START = 2015; AUCTION_START = 2023
    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    def _compute(start_yr: int, end_yr: int) -> dict:
        faab_bids: list = []; faab_rem: list = []; faab_map: dict = {}
        auction_bids: list = []

        for yr, yr_tx in transactions.items():
            yr_int = int(yr)
            if not (start_yr <= yr_int <= end_yr) or yr not in finished: continue
            if yr_int < FAAB_START: continue
            spent: dict = {}
            for move in yr_tx.get("moves", []):
                mid = move.get("manager_id") or move.get("manager") or ""
                if mid not in KNOWN_MEMBERS: continue
                for added in move.get("added", []):
                    bid = added.get("waiver_bid")
                    if bid is None: continue
                    try: bid_int = int(bid)
                    except: continue
                    if bid_int <= 0: continue
                    spent[mid] = spent.get(mid, 0) + bid_int
                    faab_bids.append({"manager_id":mid,"display_name":dn(mid,results),
                                      "player_name":added.get("name"),
                                      "position":added.get("position"),
                                      "bid":bid_int,"year":yr_int})
            for mid, s in spent.items():
                rem = 200 - s
                faab_rem.append({"manager_id":mid,"display_name":dn(mid,results),
                                  "year":yr_int,"spent":s,"remaining":rem})
                faab_map.setdefault(mid,[]).append(rem)

        for yr, yr_draft in drafts.items():
            yr_int = int(yr)
            if not (start_yr <= yr_int <= end_yr) or yr not in finished: continue
            if yr_int < AUCTION_START or yr_draft.get("draft_type") != "auction": continue
            for p in yr_draft.get("picks", []):
                mid = p.get("manager_id") or ""
                if mid not in KNOWN_MEMBERS or not p.get("cost"): continue
                try: cost_int = int(p["cost"])
                except: continue
                auction_bids.append({"manager_id":mid,"display_name":dn(mid,results),
                                     "player_name":p.get("player_name"),
                                     "position":p.get("position"),
                                     "cost":cost_int,"year":yr_int})

        faab_bids.sort(key=lambda x: -x["bid"])
        faab_rem.sort(key=lambda x: -x["remaining"])
        auction_bids.sort(key=lambda x: -x["cost"])
        avg_rem = sorted([{"manager_id":m,"display_name":dn(m,results),
                           "avg_remaining":round(sum(v)/len(v),1),"seasons":len(v)}
                          for m,v in faab_map.items()], key=lambda x: -x["avg_remaining"])
        return {
            "faab":    {"top10_bids":faab_bids[:10],"bottom10_remaining":faab_rem[:10],"avg_remaining":avg_rem},
            "auction": {"top10_bids":auction_bids[:10]},
        }

    return {era: _compute(s, e) for era, (s, e) in ERAS.items()}


# ── double play frequency ─────────────────────────────────────────────────────

def build_double_play(results: dict, matchups: dict) -> dict:
    """Frequency of playing each opponent twice per season, per era. KNOWN_MEMBERS only."""
    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    def _compute(start_yr: int, end_yr: int) -> list:
        play_twice: dict = {}
        for yr, yr_mu in matchups.items():
            yr_int = int(yr)
            if not (start_yr <= yr_int <= end_yr) or yr not in finished: continue
            ps = yr_mu.get("playoff_start") or 99
            game_counts: dict = {}
            for wk_entry in yr_mu.get("weeks", []):
                if wk_entry.get("week", 0) >= ps: continue
                for m in wk_entry.get("matchups", []):
                    if m.get("is_consolation"): continue
                    teams = [t.get("manager_id") for t in m.get("teams", [])
                             if t.get("manager_id") in KNOWN_MEMBERS]
                    if len(teams) == 2:
                        key = tuple(sorted(teams))
                        game_counts[key] = game_counts.get(key, 0) + 1
            for (m1,m2), cnt in game_counts.items():
                for mid, opp in [(m1,m2),(m2,m1)]:
                    play_twice.setdefault(mid,{}).setdefault(opp,{"seasons":0,"twice":0})
                    play_twice[mid][opp]["seasons"] += 1
                    if cnt >= 2: play_twice[mid][opp]["twice"] += 1

        out: list = []
        for mid in sorted(KNOWN_MEMBERS):
            opp_list = []
            for opp, data in play_twice.get(mid, {}).items():
                s = data["seasons"]; tw = data["twice"]
                pct = round(tw/s, 4) if s else 0
                dev = round(pct - 0.6667, 4)
                opp_list.append({"opponent_id":opp,"display_name":dn(opp,results),
                                  "seasons":s,"twice_count":tw,"expected":round(s*0.6667,2),
                                  "actual_pct":pct,"deviation":dev,
                                  "deviation_label":"above" if dev>0 else ("below" if dev<0 else "exact")})
            opp_list.sort(key=lambda x: abs(x["deviation"]), reverse=True)
            out.append({"manager_id":mid,"display_name":dn(mid,results),
                        "furthest_from_expected":opp_list[0] if opp_list else None,
                        "all_opponents":opp_list})
        return out

    return {era: _compute(s, e) for era, (s, e) in ERAS.items()}


# ── position rankings ─────────────────────────────────────────────────────────

def build_position_rankings(results: dict, matchups: dict, rosters: dict,
                             player_stats: dict, player_info: dict) -> dict:
    """
    Per era AND per season. KNOWN_MEMBERS only.

    For each manager, sum fantasy_points for all is_starting=true players
    grouped by position. Divide by total regular season weeks played to get
    avg points per week at each position — regardless of how many starters
    fill that slot.

    Example: if a manager starts 2 RBs scoring 15+10=25 pts in week 3,
    that week contributes 25 to their RB total. Dividing by weeks gives
    true per-week output at that position.

    Then rank each manager 1-N for each position within that era/season.

    Output structure:
      era_blocks: { era: { position: [ {manager_id, total_pts, avg_per_week, rank, weeks} ] } }
      seasons:    { yr:  { position: [ {manager_id, total_pts, avg_per_week, rank, weeks} ] } }
    """
    POSITIONS = ["QB", "WR", "RB", "TE", "K", "DEF"]

    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    # ── season-level accumulation ─────────────────────────────────────────────
    # season_acc[yr][mid][pos] = {total_pts, weeks}
    # weeks = number of regular season weeks this manager started at least 1 player
    season_acc: dict = {}

    for yr in sorted(finished.keys(), key=int):
        yr_int    = int(yr)
        yr_mu     = matchups.get(yr, {})
        ps        = yr_mu.get("playoff_start") or 99
        yr_stats  = player_stats.get(yr, {})
        yr_info   = (player_info.get(yr, {}) or {}).get("players", {})
        yr_roster = rosters.get(yr, {})

        if not yr_stats or not yr_info or not yr_roster:
            continue

        season_acc[yr] = {}

        # Get regular season week keys
        wk_keys = sorted(
            [k for k in yr_roster if k.startswith("week_")
             and int(k.split("_")[1]) < ps],
            key=lambda x: int(x.split("_")[1])
        )

        for wk_key in wk_keys:
            wk_roster = yr_roster.get(wk_key, {})
            wk_stats  = yr_stats.get(wk_key, {})
            if not wk_stats: continue

            for mid, team in wk_roster.items():
                if mid not in KNOWN_MEMBERS:    continue
                if not isinstance(team, dict):  continue

                slots = team.get("players", [])
                if not slots: continue

                # Init manager entry for this season
                if mid not in season_acc[yr]:
                    season_acc[yr][mid] = {
                        pos: {"total_pts": 0.0, "weeks": 0}
                        for pos in POSITIONS
                    }

                # Accumulate starting points by position this week
                week_pos_pts: dict = {pos: 0.0 for pos in POSITIONS}
                week_pos_started: set = set()

                for slot in slots:
                    if not isinstance(slot, dict):      continue
                    if not slot.get("is_starting"):     continue
                    pk      = slot.get("player_key") or ""
                    pi      = yr_info.get(pk, {})
                    pos_raw = pi.get("position") or ""
                    pos     = pos_raw.split("/")[0].strip() if "/" in pos_raw else pos_raw
                    if pos not in POSITIONS:            continue
                    pd  = wk_stats.get(pk)
                    pts = float(pd.get("fantasy_points") or 0) if isinstance(pd, dict) else 0.0
                    week_pos_pts[pos] = round(week_pos_pts[pos] + pts, 2)
                    week_pos_started.add(pos)

                # Add week's contribution — only increment week count once per position per week
                for pos in POSITIONS:
                    if pos in week_pos_started:
                        season_acc[yr][mid][pos]["total_pts"] = round(
                            season_acc[yr][mid][pos]["total_pts"] + week_pos_pts[pos], 2
                        )
                        season_acc[yr][mid][pos]["weeks"] += 1

    # ── era accumulation ─────────────────────────────────────────────────────
    # era_acc[era][mid][pos] = {total_pts, weeks}
    era_acc: dict = {era: {} for era in ERAS}

    for yr, yr_data in season_acc.items():
        yr_int   = int(yr)
        active   = [era for era, (s, e) in ERAS.items() if s <= yr_int <= e]
        for mid, pos_data in yr_data.items():
            for era in active:
                if mid not in era_acc[era]:
                    era_acc[era][mid] = {
                        pos: {"total_pts": 0.0, "weeks": 0}
                        for pos in POSITIONS
                    }
                for pos in POSITIONS:
                    era_acc[era][mid][pos]["total_pts"] = round(
                        era_acc[era][mid][pos]["total_pts"] + pos_data[pos]["total_pts"], 2
                    )
                    era_acc[era][mid][pos]["weeks"] += pos_data[pos]["weeks"]

    # ── format helper ─────────────────────────────────────────────────────────
    def fmt_rankings(acc: dict) -> dict:
        """
        Given {mid: {pos: {total_pts, weeks}}},
        return {pos: [{manager_id, display_name, total_pts, avg_per_week, weeks, rank}]}
        sorted by avg_per_week desc with rank assigned.
        """
        out: dict = {}
        for pos in POSITIONS:
            mgr_rows = []
            for mid, pos_data in acc.items():
                pd_  = pos_data.get(pos, {})
                total= pd_.get("total_pts", 0.0)
                wks  = pd_.get("weeks", 0)
                if wks == 0: continue   # manager never started this position
                avg  = round(total / wks, 2)
                mgr_rows.append({
                    "manager_id":   mid,
                    "display_name": dn(mid, results),
                    "total_pts":    total,
                    "avg_per_week": avg,
                    "weeks":        wks,
                })
            # sort by avg_per_week descending, assign rank
            mgr_rows.sort(key=lambda x: -x["avg_per_week"])
            for rank, row in enumerate(mgr_rows, 1):
                row["rank"] = rank
            out[pos] = mgr_rows
        return out

    # ── assemble era output ───────────────────────────────────────────────────
    era_out: dict = {
        era: fmt_rankings(era_acc[era])
        for era in ERAS
    }

    # ── assemble season output ────────────────────────────────────────────────
    season_out: dict = {
        yr: fmt_rankings(yr_data)
        for yr, yr_data in season_acc.items()
    }

    return {"era_blocks": era_out, "seasons": season_out}


# ── touchdown records ─────────────────────────────────────────────────────────

def build_touchdown_records(results: dict, matchups: dict, rosters: dict,
                             player_stats: dict) -> dict:
    """
    Total TDs scored by each manager's starters and allowed against each manager.
    All managers (no KNOWN_MEMBERS restriction on td_against side since opponents
    may be outside the set). td_for restricted to KNOWN_MEMBERS.

    TD stat_ids counted:
      5  = passing TD
      10 = rushing TD
      15 = receiving TD
      57 = offensive fumble return TD
      35 = defensive TD
      49 = kickoff/punt return TD

    These are raw counts (quantity), not fantasy points.

    Output:
      era_blocks: { era: [ {manager_id, total_td_for, total_td_against, td_diff} ] }
      seasons:    { yr:  [ {manager_id, total_td_for, total_td_against, td_diff} ] }
    Both sorted by total_td_for desc.
    """
    TD_STAT_IDS = {"5", "10", "15", "57", "35", "49"}

    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    # ── season-level accumulation ─────────────────────────────────────────────
    # season_tds[yr][mid] = {for, against}
    season_tds: dict = {}

    for yr in sorted(finished.keys(), key=int):
        yr_mu     = matchups.get(yr, {})
        ps        = yr_mu.get("playoff_start") or 99
        yr_stats  = player_stats.get(yr, {})
        yr_roster = rosters.get(yr, {})

        if not yr_stats or not yr_roster:
            continue

        # Build weekly opponent map (mid → opp_mid per week, RS only)
        wk_opp: dict = {}   # (mid, wk_num) → opp_mid
        for wk_entry in yr_mu.get("weeks", []):
            wk_num = wk_entry.get("week", 0)
            if wk_num >= ps: continue
            for m in wk_entry.get("matchups", []):
                if m.get("is_consolation"): continue
                teams = [t.get("manager_id") for t in m.get("teams", [])
                         if t.get("manager_id")]
                if len(teams) == 2:
                    wk_opp[(teams[0], wk_num)] = teams[1]
                    wk_opp[(teams[1], wk_num)] = teams[0]

        season_tds[yr] = {}

        # Regular season week keys
        wk_keys = sorted(
            [k for k in yr_roster if k.startswith("week_")
             and int(k.split("_")[1]) < ps],
            key=lambda x: int(x.split("_")[1])
        )

        for wk_key in wk_keys:
            wk_num    = int(wk_key.split("_")[1])
            wk_roster = yr_roster.get(wk_key, {})
            wk_stats  = yr_stats.get(wk_key, {})
            if not wk_stats: continue

            for mid, team in wk_roster.items():
                if not isinstance(team, dict): continue
                # Init
                if mid not in season_tds[yr]:
                    season_tds[yr][mid] = {"td_for": 0, "td_against": 0}

                # Count TDs scored by this manager's starters
                wk_tds = 0
                for slot in team.get("players", []):
                    if not isinstance(slot, dict):  continue
                    if not slot.get("is_starting"): continue
                    pk = slot.get("player_key") or ""
                    pd = wk_stats.get(pk)
                    if not isinstance(pd, dict):    continue
                    for sid, val in (pd.get("stats") or {}).items():
                        if str(sid) in TD_STAT_IDS:
                            try: wk_tds += int(float(val))
                            except: pass

                season_tds[yr][mid]["td_for"] += wk_tds

                # Attribute this manager's TDs as td_against for their opponent
                opp = wk_opp.get((mid, wk_num))
                if opp:
                    if opp not in season_tds[yr]:
                        season_tds[yr][opp] = {"td_for": 0, "td_against": 0}
                    season_tds[yr][opp]["td_against"] += wk_tds

    # ── era accumulation ─────────────────────────────────────────────────────
    era_acc: dict = {era: {} for era in ERAS}

    for yr, yr_data in season_tds.items():
        yr_int = int(yr)
        active = [era for era, (s, e) in ERAS.items() if s <= yr_int <= e]
        for mid, counts in yr_data.items():
            for era in active:
                if mid not in era_acc[era]:
                    era_acc[era][mid] = {"td_for": 0, "td_against": 0}
                era_acc[era][mid]["td_for"]     += counts["td_for"]
                era_acc[era][mid]["td_against"] += counts["td_against"]

    # ── format helper ─────────────────────────────────────────────────────────
    def fmt_td_list(acc: dict) -> list:
        rows = []
        for mid, counts in acc.items():
            rows.append({
                "manager_id":    mid,
                "display_name":  dn(mid, results),
                "total_td_for":    counts["td_for"],
                "total_td_against":counts["td_against"],
                "td_diff":         counts["td_for"] - counts["td_against"],
            })
        rows.sort(key=lambda x: -x["total_td_for"])
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        return rows

    return {
        "era_blocks": {era: fmt_td_list(era_acc[era]) for era in ERAS},
        "seasons":    {yr: fmt_td_list(yr_data) for yr, yr_data in season_tds.items()},
    }


# ── team points breakdown ─────────────────────────────────────────────────────

def build_team_points_breakdown(results: dict, matchups: dict, rosters: dict,
                                 player_stats: dict, rules: dict) -> dict:
    """
    For each manager's starters each week, bucket their fantasy points into:

      td_category:  stat_ids 5,10,13,15,35,49
                    (pass TD, rush TD, rec TD, ret TD, def TD, KR/PR TD)
      yds_category: stat_ids 2,4,9,11,12
                    (completions, pass yds, rush yds, receptions, rec yds)
      st_category:  stat_ids 16,36,67,82
                    (2PT conv, safety, block kick, XP return)
      other:        total fantasy_points minus all above categories
                    (catches everything else: fumbles lost, PA tiers, etc.)

    Points are computed as stat_value × points_per_unit from that year's rules.json.
    Totals and averages (÷ weeks) per manager per era and per season.
    KNOWN_MEMBERS only.
    """
    TD_IDS = {"5","10","13","15","35","49"}
    YD_IDS = {"2","4","9","11","12"}
    ST_IDS = {"16","36","67","82"}
    ALL_BUCKETED = TD_IDS | YD_IDS | ST_IDS

    finished = {yr: s for yr, s in results.items()
                if str(yr).isdigit() and s.get("is_finished")}

    BREAKDOWN_START = 2022   # stat-level breakdown only available from 2022+

    # Pre-build ppu_map per year from rules.json
    # ppu_map[yr][stat_id_str] = points_per_unit (float)
    ppu_map: dict = {}
    for yr, yr_rules in rules.items():
        ppu_map[yr] = {}
        for cat in yr_rules.get("stat_categories", []):
            sid = str(cat.get("stat_id", ""))
            ppu = cat.get("points_per_unit")
            if sid and ppu is not None:
                try: ppu_map[yr][sid] = float(ppu)
                except: pass

    def blank_wk():
        return {"td": 0.0, "yds": 0.0, "st": 0.0, "other": 0.0, "total": 0.0}

    # ── season-level accumulation ─────────────────────────────────────────────
    # season_acc[yr][mid] = {td, yds, st, other, total, weeks}
    season_acc: dict = {}

    for yr in sorted(finished.keys(), key=int):
        yr_mu     = matchups.get(yr, {})
        ps        = yr_mu.get("playoff_start") or 99
        yr_stats  = player_stats.get(yr, {})
        yr_roster = rosters.get(yr, {})
        yr_ppu    = ppu_map.get(yr, {})

        if not yr_stats or not yr_roster:
            continue

        season_acc[yr] = {}

        wk_keys = sorted(
            [k for k in yr_roster if k.startswith("week_")
             and int(k.split("_")[1]) < ps],
            key=lambda x: int(x.split("_")[1])
        )

        for wk_key in wk_keys:
            wk_roster = yr_roster.get(wk_key, {})
            wk_stats  = yr_stats.get(wk_key, {})
            if not wk_stats: continue

            for mid, team in wk_roster.items():
                if mid not in KNOWN_MEMBERS:   continue
                if not isinstance(team, dict): continue

                slots = team.get("players", [])
                if not slots: continue

                if mid not in season_acc[yr]:
                    season_acc[yr][mid] = {
                        "td":0.0,"yds":0.0,"st":0.0,"other":0.0,
                        "total":0.0,"weeks":0
                    }

                wk_pts = blank_wk()
                had_starters = False

                for slot in slots:
                    if not isinstance(slot, dict):  continue
                    if not slot.get("is_starting"): continue
                    pk = slot.get("player_key") or ""
                    pd = wk_stats.get(pk)
                    if not isinstance(pd, dict):    continue

                    fp_total = float(pd.get("fantasy_points") or 0)
                    stats    = pd.get("stats") or {}
                    had_starters = True

                    td_pts = yds_pts = st_pts = 0.0

                    for sid, val in stats.items():
                        sid_str = str(sid)
                        ppu     = yr_ppu.get(sid_str, 0.0)
                        if ppu == 0: continue
                        try: contrib = float(val) * ppu
                        except: continue

                        if   sid_str in TD_IDS: td_pts  += contrib
                        elif sid_str in YD_IDS: yds_pts += contrib
                        elif sid_str in ST_IDS: st_pts  += contrib

                    other_pts = fp_total - td_pts - yds_pts - st_pts

                    wk_pts["td"]    += td_pts
                    wk_pts["yds"]   += yds_pts
                    wk_pts["st"]    += st_pts
                    wk_pts["other"] += other_pts
                    wk_pts["total"] += fp_total

                if had_starters:
                    a = season_acc[yr][mid]
                    a["td"]    = round(a["td"]    + wk_pts["td"],    2)
                    a["yds"]   = round(a["yds"]   + wk_pts["yds"],   2)
                    a["st"]    = round(a["st"]     + wk_pts["st"],    2)
                    a["other"] = round(a["other"]  + wk_pts["other"], 2)
                    a["total"] = round(a["total"]  + wk_pts["total"], 2)
                    a["weeks"] += 1

    # ── era accumulation ─────────────────────────────────────────────────────
    # Only include seasons from BREAKDOWN_START onward — pre-2022 has no
    # stat-level breakdown so including those years corrupts the percentages
    era_acc: dict = {era: {} for era in ERAS}

    for yr, yr_data in season_acc.items():
        yr_int = int(yr)
        if yr_int < BREAKDOWN_START:
            continue   # skip — no stat breakdown available
        active = [era for era, (s, e) in ERAS.items() if s <= yr_int <= e]
        for mid, counts in yr_data.items():
            for era in active:
                if mid not in era_acc[era]:
                    era_acc[era][mid] = {
                        "td":0.0,"yds":0.0,"st":0.0,"other":0.0,
                        "total":0.0,"weeks":0
                    }
                a = era_acc[era][mid]
                a["td"]    = round(a["td"]    + counts["td"],    2)
                a["yds"]   = round(a["yds"]   + counts["yds"],   2)
                a["st"]    = round(a["st"]     + counts["st"],    2)
                a["other"] = round(a["other"]  + counts["other"], 2)
                a["total"] = round(a["total"]  + counts["total"], 2)
                a["weeks"] += counts["weeks"]

    # ── format helper ─────────────────────────────────────────────────────────
    def fmt_breakdown(acc: dict) -> list:
        rows = []
        for mid, c in acc.items():
            wks = c["weeks"] or 1
            tot = c["total"] or 1
            rows.append({
                "manager_id":   mid,
                "display_name": dn(mid, results),
                "weeks":        c["weeks"],
                "totals": {
                    "td_pts":    round(c["td"],    2),
                    "yds_pts":   round(c["yds"],   2),
                    "st_pts":    round(c["st"],     2),
                    "other_pts": round(c["other"],  2),
                    "total_pts": round(c["total"],  2),
                },
                "avg_per_week": {
                    "td_pts":    round(c["td"]    / wks, 2),
                    "yds_pts":   round(c["yds"]   / wks, 2),
                    "st_pts":    round(c["st"]     / wks, 2),
                    "other_pts": round(c["other"]  / wks, 2),
                    "total_pts": round(c["total"]  / wks, 2),
                },
                "pct_of_total": {
                    "td_pct":    round(c["td"]    / tot * 100, 1),
                    "yds_pct":   round(c["yds"]   / tot * 100, 1),
                    "st_pct":    round(c["st"]     / tot * 100, 1),
                    "other_pct": round(c["other"]  / tot * 100, 1),
                },
                # store raw avgs temporarily for ranking pass
                "_avgs": {
                    "td":    round(c["td"]    / wks, 2),
                    "yds":   round(c["yds"]   / wks, 2),
                    "st":    round(c["st"]     / wks, 2),
                    "other": round(c["other"]  / wks, 2),
                    "total": round(c["total"]  / wks, 2),
                },
            })

        # Sort + overall rank
        rows.sort(key=lambda x: -x["totals"]["total_pts"])
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank

        # Per-category ranks inside avg_per_week
        for cat, avg_key in [("td","td_pts"),("yds","yds_pts"),
                              ("st","st_pts"),("other","other_pts"),("total","total_pts")]:
            cat_sorted = sorted(rows, key=lambda x: -x["_avgs"][cat])
            for rank, row in enumerate(cat_sorted, 1):
                row["avg_per_week"][f"{avg_key}_rank"] = rank

        # Clean up temp field
        for row in rows:
            del row["_avgs"]

        return rows

    return {
        "era_blocks": {era: fmt_breakdown(era_acc[era]) for era in ERAS},
        "seasons":    {yr: fmt_breakdown(yr_data)
                       for yr, yr_data in season_acc.items()
                       if int(yr) >= BREAKDOWN_START},
        "_data_note": f"Stat-level breakdown available from {BREAKDOWN_START} onward only.",
    }


# ── run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading data...")
    results      = load("results.json")
    matchups     = load("matchups.json")
    rosters      = load("rosters.json")
    player_stats = load("player_stats.json")
    player_info  = load("player_info.json")
    rules        = load("rules.json")
    ices         = load("ices.json")
    drafts       = load("drafts.json")
    transactions = load("transactions.json")

    if not results:
        print("ERROR: results.json not found or empty.")
        exit(1)

    finished_count = len([y for y in results if results[y].get("is_finished")])
    print(f"Found {finished_count} finished seasons\n")

    print("Building W-L records...")
    wl = build_wl_combined(results, matchups, rosters, player_stats, player_info, rules)
    overall = wl["era_blocks"].get("overall", {})
    print("=== OVERALL W-L-T ===")
    for mid, m in sorted(overall.items(), key=lambda x: -(x[1]["actual"]["total"].get("win_pct") or 0)):
        act = m["actual"]["total"]; th = m["theoretical"]["total"]
        bb  = m["best_ball"]["total"] if isinstance(m["best_ball"]["total"], dict) else {}
        print(f"  {m['display_name']:<10} Act:{act['w']}-{act['l']} ({act['win_pct']:.3f}) "
              f"Luck:{th['luck_total']:+.1f} BB:{bb.get('w','-')}-{bb.get('l','-')} diff={bb.get('bb_win_diff_label','-')}")

    print("\nBuilding ice records...")
    ice_rec = build_ice_records(results, ices)
    print(f"  Eras built: {list(ice_rec['era_blocks'].keys())}")

    print("\nBuilding championship players...")
    champ = build_championship_players(results, rosters, player_info)
    print(f"  Top: {champ[0]['player_name']} ({champ[0]['appearances']} apps, score={champ[0]['weighted_score']})" if champ else "  None")

    print("\nBuilding top draft picks...")
    picks = build_top_draft_picks(results, drafts)
    print(f"  Top: {picks[0]['player_name']} x{picks[0]['count']}" if picks else "  None")

    print("\nBuilding bar chart race...")
    race = build_bar_chart_race(results)
    print(f"  {len(race)} seasons, {len(race[0]['totals'])} managers")

    print("\nBuilding trade records...")
    trades = build_trade_records(results, transactions)
    ov = trades.get("overall", {})
    print(f"  Overall top partner: {ov.get('top_partners', [{}])[0].get('manager_1',{}).get('display_name','-')} / "
          f"{ov.get('top_partners', [{}])[0].get('manager_2',{}).get('display_name','-')} "
          f"({ov.get('top_partners', [{}])[0].get('total_trades',0)} trades)")

    print("\nBuilding scoring records...")
    scoring = build_scoring_records(results, matchups, player_stats, player_info, rosters)
    ov_s = scoring.get("overall", {})
    top_wk = ov_s.get("top10_weekly_pf", [{}])[0]
    print(f"  Overall top week: {top_wk.get('display_name','-')} {top_wk.get('year','-')} "
          f"wk{top_wk.get('week','-')} {top_wk.get('points','-')}pts")

    print("\nBuilding manager records...")
    mgr = build_mgr_records(results, rosters, player_stats, player_info)
    print(f"  Best seasons: {[x['display_name']+' '+str(x['year']) for x in mgr['best_season_per_manager'][:3]]}")
    print(f"  Top combo:    {mgr['player_mgr_combo'][0]['display_name']} + "
          f"{mgr['player_mgr_combo'][0]['player_name']} "
          f"({mgr['player_mgr_combo'][0]['weeks_together']} wks)" if mgr['player_mgr_combo'] else "  None")

    print("\nBuilding FAAB + auction records...")
    fa = build_faab_auction(results, transactions, drafts)
    ov_fa = fa.get("overall", {})
    top_faab = ov_fa.get("faab", {}).get("top10_bids", [{}])[0]
    print(f"  Top FAAB: {top_faab.get('display_name','-')} ${top_faab.get('bid','-')} "
          f"({top_faab.get('player_name','-')}, {top_faab.get('year','-')})")

    print("\nBuilding double play frequency...")
    dp = build_double_play(results, matchups)
    ov_dp = dp.get("overall", [])
    if ov_dp:
        first = ov_dp[0]
        fe = first.get("furthest_from_expected") or {}
        print(f"  {first['display_name']} furthest from expected vs "
              f"{fe.get('display_name','-')}: {fe.get('actual_pct',0):.1%} "
              f"(dev={fe.get('deviation',0):+.3f})")

    print("\nBuilding position rankings...")
    pos_rank = build_position_rankings(results, matchups, rosters, player_stats, player_info)
    ov_pr = pos_rank["era_blocks"].get("overall", {})
    for pos in ["QB","WR","RB","TE"]:
        rows = ov_pr.get(pos, [])
        if rows:
            top = rows[0]
            print(f"  {pos} #1: {top['display_name']:<10} "
                  f"avg={top['avg_per_week']:.1f} pts/wk  "
                  f"total={top['total_pts']}  wks={top['weeks']}")

    print("\nBuilding touchdown records...")
    td_rec = build_touchdown_records(results, matchups, rosters, player_stats)
    ov_td = td_rec["era_blocks"].get("overall", [])
    if ov_td:
        top = ov_td[0]
        print(f"  Overall TD leader: {top['display_name']} "
              f"for={top['total_td_for']} against={top['total_td_against']} "
              f"diff={top['td_diff']:+d}")
    latest_td_yr = sorted(td_rec["seasons"].keys(), key=int)[-1]
    print(f"  {latest_td_yr} season:")
    for row in td_rec["seasons"][latest_td_yr][:5]:
        print(f"    {row['display_name']:<10} for={row['total_td_for']:3d} "
              f"against={row['total_td_against']:3d} diff={row['td_diff']:+d}")

    print("\nBuilding team points breakdown...")
    tpb = build_team_points_breakdown(results, matchups, rosters, player_stats, rules)
    ov_tpb = tpb["era_blocks"].get("overall", [])
    if ov_tpb:
        top = ov_tpb[0]
        avg = top["avg_per_week"]
        pct = top["pct_of_total"]
        print(f"  Overall leader: {top['display_name']} ({top['weeks']} wks)")
        print(f"    avg/wk → TD:{avg['td_pts']} Yds:{avg['yds_pts']} ST:{avg['st_pts']} Other:{avg['other_pts']} Total:{avg['total_pts']}")
        print(f"    pct    → TD:{pct['td_pct']}% Yds:{pct['yds_pct']}% ST:{pct['st_pct']}% Other:{pct['other_pct']}%")

    print("\nAll builders complete.")




# ===========================================================================
# league.py endpoint — drop-in replacement for build_analytics()
# ===========================================================================

def build_analytics_endpoint(
    _load_json,
    _get_data_path,
    _write_json,
    force_clean: bool = False,
):
    """
    Drop-in for the @router.get("/data/analytics/build-all") endpoint body.

    Accepts the four helpers from league.py:
      _load_json(path)         → dict
      _get_data_path(filename) → str
      _write_json(path, data)  → None

    Usage in league.py:
      from analytics_builder import build_analytics_endpoint
      # then inside the route function body, replace all logic with:
      return build_analytics_endpoint(_load_json, _get_data_path, _write_json, force_clean)
    """
    import datetime

    path = _get_data_path("analytics.json")
    if not force_clean:
        existing = _load_json(path) or {}
        if existing.get("_built_at"):
            return {
                "status":    "already_built",
                "built_at":  existing["_built_at"],
                "note":      "Use force_clean=true to rebuild",
            }

    # Load all data files
    def _load(filename):
        raw = _load_json(_get_data_path(filename))
        if not raw: return {}
        if "data" in raw and isinstance(raw["data"], dict):
            return raw["data"]
        return raw

    results      = _load("results.json")
    matchups     = _load("matchups.json")
    rosters      = _load("rosters.json")
    player_stats = _load("player_stats.json")
    player_info  = _load("player_info.json")
    rules        = _load("rules.json")
    ices         = _load("ices.json")
    drafts       = _load("drafts.json")
    transactions = _load("transactions.json")

    if not results:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="results.json not found.")

    # Run all builders
    wl       = build_wl_combined(results, matchups, rosters, player_stats, player_info, rules)
    ice_rec  = build_ice_records(results, ices)
    champ    = build_championship_players(results, rosters, player_info)
    picks    = build_top_draft_picks(results, drafts)
    race     = build_bar_chart_race(results)
    trades   = build_trade_records(results, transactions)
    scoring  = build_scoring_records(results, matchups, player_stats, player_info, rosters)
    mgr_rec  = build_mgr_records(results, rosters, player_stats, player_info)
    fa       = build_faab_auction(results, transactions, drafts)
    dp       = build_double_play(results, matchups)
    pos_rank = build_position_rankings(results, matchups, rosters, player_stats, player_info)
    td_rec   = build_touchdown_records(results, matchups, rosters, player_stats)
    tpb      = build_team_points_breakdown(results, matchups, rosters, player_stats, rules)

    output = {
        "_built_at":       datetime.datetime.utcnow().isoformat(),
        "_seasons_covered":len([y for y in results if results[y].get("is_finished")]),
        "_members":        sorted(KNOWN_MEMBERS),

        # W-L-T (actual / theoretical / best ball) — era_blocks + seasons
        "wl_records":            wl,

        # Ices — era_blocks + seasons
        "ice_records":           ice_rec,

        # Championship roster players (all-time, top 10)
        "championship_players":  champ,

        # Most drafted players (snake R1 + auction top 10, all-time)
        "top_draft_picks":       picks,

        # Bar chart race — all managers, cumulative wins by season
        "bar_chart_race":        race,

        # Trade records — era_blocks only (top partners + most traded players)
        "trade_records":         trades,

        # Scoring records — era_blocks only (top/bottom PF + position records)
        "scoring_records":       scoring,

        # Manager records — all-time only (best/worst season + player_mgr_combo)
        "manager_records":       mgr_rec,

        # FAAB + auction — era_blocks only
        "faab_auction":          fa,

        # Double play frequency — era_blocks only
        "double_play_frequency": dp,

        # Position rankings — era_blocks + seasons
        "position_rankings":     pos_rank,

        # Touchdown records — era_blocks + seasons
        "touchdown_records":     td_rec,

        # Team points breakdown — era_blocks + seasons
        "team_points_breakdown": tpb,
    }

    try:
        _write_json(path, output)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Write failed: {e}")

    return {
        "status":           "complete",
        "built_at":         output["_built_at"],
        "seasons_computed": output["_seasons_covered"],
        "next_step":        "GET /league/data/analytics/download to save locally",
    }