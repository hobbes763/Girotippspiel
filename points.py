ETAPPE = {1: 120, 2: 80, 3: 70, 4: 60, 5: 50, 6: 40, 7: 35, 8: 30, 9: 25, 10: 20, 11: 10, 12: 8}
LEADER = {1: 30, 2: 20, 3: 15, 4: 12, 5: 12, 6: 9, 7: 8, 8: 8, 9: 7, 10: 6}
BERG = {1: 15, 2: 10, 3: 7, 4: 5, 5: 4}
PUNKTE = {1: 15, 2: 10, 3: 7, 4: 5, 5: 4}
NACHWUCHS = {1: 10, 2: 7, 3: 5}
TEAM_TAG = {1: 10, 2: 7, 3: 5}
TTT = {1: 30, 2: 20, 3: 15, 4: 10}
SUPER_TEAM = 10

GESAMT = {1: 450, 2: 300, 3: 200, 4: 150, 5: 120, 6: 90, 7: 80, 8: 70, 9: 60, 10: 50}
BERG_GESAMT = {1: 180, 2: 100, 3: 75, 4: 50, 5: 40}
PUNKTE_GESAMT = {1: 180, 2: 100, 3: 75, 4: 50, 5: 40}
TEAM_GESAMT = {1: 50, 2: 30, 3: 20}
NACHWUCHS_GESAMT = {1: 120, 2: 80, 3: 50}
ANKUNFT = 30


def get_rider_team(riders_by_id, rid):
    r = riders_by_id.get(rid)
    return r["team"] if r else None


def calc_stage_points(player_ids, riders_by_id, stage):
    r = stage.get("results", {})
    pts = dict(etappe=0, leader=0, berg=0, punkte=0, nachwuchs=0, team_tag=0, ttt=0)

    active_ids = {rid for rid in player_ids if not riders_by_id.get(rid, {}).get("aufgegeben", False)}
    player_teams = {get_rider_team(riders_by_id, rid) for rid in active_ids}

    for pos, rid in enumerate(r.get("etappe", []), 1):
        if rid in active_ids and pos in ETAPPE:
            pts["etappe"] += ETAPPE[pos]

    for pos, rid in enumerate(r.get("leader", []), 1):
        if rid in active_ids and pos in LEADER:
            pts["leader"] += LEADER[pos]

    for pos, rid in enumerate(r.get("berg", []), 1):
        if rid in active_ids and pos in BERG:
            pts["berg"] += BERG[pos]

    for pos, rid in enumerate(r.get("punkte", []), 1):
        if rid in active_ids and pos in PUNKTE:
            pts["punkte"] += PUNKTE[pos]

    for pos, rid in enumerate(r.get("nachwuchs", []), 1):
        if rid in active_ids and pos in NACHWUCHS:
            pts["nachwuchs"] += NACHWUCHS[pos]

    for pos, team in enumerate(r.get("team_day", []), 1):
        if team in player_teams and pos in TEAM_TAG:
            count = sum(1 for rid in active_ids if get_rider_team(riders_by_id, rid) == team)
            pts["team_tag"] += TEAM_TAG[pos] * count

    if stage.get("is_ttt"):
        for pos, team in enumerate(r.get("ttt_order", []), 1):
            if team in player_teams and pos in TTT:
                count = sum(1 for rid in active_ids if get_rider_team(riders_by_id, rid) == team)
                pts["ttt"] += TTT[pos] * count

    for rid in r.get("super_team", []):
        if rid in active_ids:
            pts["team_tag"] += SUPER_TEAM

    return pts


def calc_final_points(player_ids, riders_by_id, final):
    pts = dict(gesamt=0, berg_gesamt=0, punkte_gesamt=0, nachwuchs_gesamt=0, team_gesamt=0, ankunft=0)
    if not final:
        return pts

    active_ids = {rid for rid in player_ids if not riders_by_id.get(rid, {}).get("aufgegeben", False)}
    player_teams = {get_rider_team(riders_by_id, rid) for rid in active_ids}

    for pos, rid in enumerate(final.get("gesamt", []), 1):
        if rid in active_ids and pos in GESAMT:
            pts["gesamt"] += GESAMT[pos]

    for pos, rid in enumerate(final.get("berg_gesamt", []), 1):
        if rid in active_ids and pos in BERG_GESAMT:
            pts["berg_gesamt"] += BERG_GESAMT[pos]

    for pos, rid in enumerate(final.get("punkte_gesamt", []), 1):
        if rid in active_ids and pos in PUNKTE_GESAMT:
            pts["punkte_gesamt"] += PUNKTE_GESAMT[pos]

    for pos, rid in enumerate(final.get("nachwuchs_gesamt", []), 1):
        if rid in active_ids and pos in NACHWUCHS_GESAMT:
            pts["nachwuchs_gesamt"] += NACHWUCHS_GESAMT[pos]

    for pos, team in enumerate(final.get("team_gesamt", []), 1):
        if team in player_teams and pos in TEAM_GESAMT:
            count = sum(1 for rid in active_ids if get_rider_team(riders_by_id, rid) == team)
            pts["team_gesamt"] += TEAM_GESAMT[pos] * count

    for rid in final.get("finishers", []):
        if rid in active_ids:
            pts["ankunft"] += ANKUNFT

    return pts


def calculate_standings(players, riders, stages, final=None):
    riders_by_id = {r["id"]: r for r in riders}

    standings = []
    for player in players:
        player_ids = set(player.get("rider_ids", []))

        stage_totals = []
        cumulative = []
        running = 0
        cat_totals = dict(etappe=0, leader=0, berg=0, punkte=0, nachwuchs=0, team_tag=0, ttt=0)

        for stage in stages:
            sp = calc_stage_points(player_ids, riders_by_id, stage)
            stage_sum = sum(sp.values())
            stage_totals.append({"stage": stage["num"], "pts": stage_sum, "breakdown": sp})
            running += stage_sum
            cumulative.append(running)
            for k in sp:
                cat_totals[k] += sp[k]

        final_pts = calc_final_points(player_ids, riders_by_id, final or {})
        grand_total = sum(cat_totals.values()) + sum(final_pts.values())

        standings.append({
            "player": player,
            "total": grand_total,
            "cat_totals": cat_totals,
            "final_pts": final_pts,
            "stage_totals": stage_totals,
            "cumulative": cumulative,
        })

    standings.sort(key=lambda x: x["total"], reverse=True)

    for i, s in enumerate(standings):
        if i > 0 and standings[i]["total"] == standings[i - 1]["total"]:
            s["rank"] = standings[i - 1]["rank"]
        else:
            s["rank"] = i + 1

    return standings


def calculate_all_rider_points(riders, stages, final=None):
    riders_by_id = {r["id"]: r for r in riders}
    all_ids = {r["id"] for r in riders}
    active_ids = {r["id"] for r in riders if not r.get("aufgegeben", False)}

    rider_pts = {rid: dict(etappe=0, leader=0, berg=0, punkte=0, nachwuchs=0, team_tag=0,
                           gesamt=0, berg_gesamt=0, punkte_gesamt=0, nachwuchs_gesamt=0, ankunft=0)
                 for rid in all_ids}

    for stage in stages:
        r = stage.get("results", {})
        for pos, rid in enumerate(r.get("etappe", []), 1):
            if rid in active_ids and pos in ETAPPE:
                rider_pts[rid]["etappe"] += ETAPPE[pos]
        for pos, rid in enumerate(r.get("leader", []), 1):
            if rid in active_ids and pos in LEADER:
                rider_pts[rid]["leader"] += LEADER[pos]
        for pos, rid in enumerate(r.get("berg", []), 1):
            if rid in active_ids and pos in BERG:
                rider_pts[rid]["berg"] += BERG[pos]
        for pos, rid in enumerate(r.get("punkte", []), 1):
            if rid in active_ids and pos in PUNKTE:
                rider_pts[rid]["punkte"] += PUNKTE[pos]
        for pos, rid in enumerate(r.get("nachwuchs", []), 1):
            if rid in active_ids and pos in NACHWUCHS:
                rider_pts[rid]["nachwuchs"] += NACHWUCHS[pos]
        for rid in r.get("super_team", []):
            if rid in active_ids:
                rider_pts[rid]["team_tag"] += SUPER_TEAM

    if final:
        for pos, rid in enumerate(final.get("gesamt", []), 1):
            if rid in active_ids and pos in GESAMT:
                rider_pts[rid]["gesamt"] += GESAMT[pos]
        for pos, rid in enumerate(final.get("berg_gesamt", []), 1):
            if rid in active_ids and pos in BERG_GESAMT:
                rider_pts[rid]["berg_gesamt"] += BERG_GESAMT[pos]
        for pos, rid in enumerate(final.get("punkte_gesamt", []), 1):
            if rid in active_ids and pos in PUNKTE_GESAMT:
                rider_pts[rid]["punkte_gesamt"] += PUNKTE_GESAMT[pos]
        for pos, rid in enumerate(final.get("nachwuchs_gesamt", []), 1):
            if rid in active_ids and pos in NACHWUCHS_GESAMT:
                rider_pts[rid]["nachwuchs_gesamt"] += NACHWUCHS_GESAMT[pos]
        for rid in final.get("finishers", []):
            if rid in active_ids:
                rider_pts[rid]["ankunft"] += ANKUNFT

    result = []
    for rid in all_ids:
        r = riders_by_id.get(rid)
        if not r:
            continue
        pts = rider_pts[rid]
        result.append({"rider": r, "pts": pts, "total": sum(pts.values())})
    result.sort(key=lambda x: (-x["total"], x["rider"]["name"]))
    return result


def calculate_player_detail(player, riders, stages, final=None):
    riders_by_id = {r["id"]: r for r in riders}
    player_ids = set(player.get("rider_ids", []))
    active_ids = {rid for rid in player_ids if not riders_by_id.get(rid, {}).get("aufgegeben", False)}

    rider_pts = {rid: dict(etappe=0, leader=0, berg=0, punkte=0, nachwuchs=0, team_tag=0, ttt=0,
                           gesamt=0, berg_gesamt=0, punkte_gesamt=0, nachwuchs_gesamt=0,
                           team_gesamt=0, ankunft=0) for rid in player_ids}

    for stage in stages:
        r = stage.get("results", {})
        active_teams = {get_rider_team(riders_by_id, rid) for rid in active_ids}

        for pos, rid in enumerate(r.get("etappe", []), 1):
            if rid in active_ids and pos in ETAPPE:
                rider_pts[rid]["etappe"] += ETAPPE[pos]

        for pos, rid in enumerate(r.get("leader", []), 1):
            if rid in active_ids and pos in LEADER:
                rider_pts[rid]["leader"] += LEADER[pos]

        for pos, rid in enumerate(r.get("berg", []), 1):
            if rid in active_ids and pos in BERG:
                rider_pts[rid]["berg"] += BERG[pos]

        for pos, rid in enumerate(r.get("punkte", []), 1):
            if rid in active_ids and pos in PUNKTE:
                rider_pts[rid]["punkte"] += PUNKTE[pos]

        for pos, rid in enumerate(r.get("nachwuchs", []), 1):
            if rid in active_ids and pos in NACHWUCHS:
                rider_pts[rid]["nachwuchs"] += NACHWUCHS[pos]

        for pos, team in enumerate(r.get("team_day", []), 1):
            if team in active_teams and pos in TEAM_TAG:
                for rid in active_ids:
                    if get_rider_team(riders_by_id, rid) == team:
                        rider_pts[rid]["team_tag"] += TEAM_TAG[pos]

        if stage.get("is_ttt"):
            for pos, team in enumerate(r.get("ttt_order", []), 1):
                if team in active_teams and pos in TTT:
                    for rid in active_ids:
                        if get_rider_team(riders_by_id, rid) == team:
                            rider_pts[rid]["ttt"] += TTT[pos]

        for rid in r.get("super_team", []):
            if rid in active_ids:
                rider_pts[rid]["team_tag"] += SUPER_TEAM

    if final:
        active_teams = {get_rider_team(riders_by_id, rid) for rid in active_ids}
        for pos, rid in enumerate(final.get("gesamt", []), 1):
            if rid in active_ids and pos in GESAMT:
                rider_pts[rid]["gesamt"] += GESAMT[pos]
        for pos, rid in enumerate(final.get("berg_gesamt", []), 1):
            if rid in active_ids and pos in BERG_GESAMT:
                rider_pts[rid]["berg_gesamt"] += BERG_GESAMT[pos]
        for pos, rid in enumerate(final.get("punkte_gesamt", []), 1):
            if rid in active_ids and pos in PUNKTE_GESAMT:
                rider_pts[rid]["punkte_gesamt"] += PUNKTE_GESAMT[pos]
        for pos, rid in enumerate(final.get("nachwuchs_gesamt", []), 1):
            if rid in active_ids and pos in NACHWUCHS_GESAMT:
                rider_pts[rid]["nachwuchs_gesamt"] += NACHWUCHS_GESAMT[pos]
        for pos, team in enumerate(final.get("team_gesamt", []), 1):
            if team in active_teams and pos in TEAM_GESAMT:
                for rid in active_ids:
                    if get_rider_team(riders_by_id, rid) == team:
                        rider_pts[rid]["team_gesamt"] += TEAM_GESAMT[pos]
        for rid in final.get("finishers", []):
            if rid in active_ids:
                rider_pts[rid]["ankunft"] += ANKUNFT

    result = []
    for rid in player_ids:
        r = riders_by_id.get(rid)
        if not r:
            continue
        pts = rider_pts[rid]
        result.append({
            "rider": r,
            "pts": pts,
            "total": sum(pts.values()),
        })
    result.sort(key=lambda x: x["total"], reverse=True)
    return result
