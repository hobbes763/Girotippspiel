import json
from datetime import date
from pathlib import Path
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional, List
from points import calculate_standings, calculate_player_detail

app = FastAPI(title="Bogos Giro Tippspiel 2026")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def load(filename):
    p = DATA_DIR / filename
    if not p.exists():
        return [] if filename != "final.json" else {}
    return json.loads(p.read_text(encoding="utf-8"))


def save(filename, data):
    (DATA_DIR / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def next_id(items):
    return max((i["id"] for i in items), default=0) + 1


# ── Public pages ──────────────────────────────────────────────────────────────

def get_stage_today_tomorrow():
    route = load("route.json")
    today_str = date.today().isoformat()
    today_stage = next((s for s in route if s["datum"] == today_str), None)
    route_sorted = sorted(route, key=lambda s: s["datum"])
    future = [s for s in route_sorted if s["datum"] > today_str]
    tomorrow_stage = future[0] if future else None
    return today_stage, tomorrow_stage


@app.get("/", response_class=HTMLResponse)
async def rangliste(request: Request):
    players = load("players.json")
    riders = load("riders.json")
    stages = load("stages.json")
    final = load("final.json")
    standings = calculate_standings(players, riders, stages, final)
    today_stage, tomorrow_stage = get_stage_today_tomorrow()
    return templates.TemplateResponse("rangliste.html", {
        "request": request,
        "standings": standings,
        "stages": stages,
        "stages_played": len(stages),
        "today_stage": today_stage,
        "tomorrow_stage": tomorrow_stage,
    })


@app.get("/spieler/{player_id}", response_class=HTMLResponse)
async def spieler_detail(request: Request, player_id: int):
    players = load("players.json")
    riders = load("riders.json")
    stages = load("stages.json")
    final = load("final.json")

    player = next((p for p in players if p["id"] == player_id), None)
    if not player:
        raise HTTPException(404, "Spieler nicht gefunden")

    standings = calculate_standings(players, riders, stages, final)
    player_standing = next((s for s in standings if s["player"]["id"] == player_id), None)
    rider_details = calculate_player_detail(player, riders, stages, final)
    riders_by_id = {r["id"]: r for r in riders}

    return templates.TemplateResponse("spieler.html", {
        "request": request,
        "player": player,
        "standing": player_standing,
        "rider_details": rider_details,
        "stages": stages,
        "riders_by_id": riders_by_id,
    })


@app.get("/etappe/{num}", response_class=HTMLResponse)
async def etappe_detail(request: Request, num: int):
    stages = load("stages.json")
    riders = load("riders.json")
    players = load("players.json")
    final = load("final.json")
    riders_by_id = {r["id"]: r for r in riders}

    stage = next((s for s in stages if s["num"] == num), None)
    if not stage:
        raise HTTPException(404, "Etappe nicht gefunden")

    standings = calculate_standings(players, riders, stages, final)
    all_stages = sorted(stages, key=lambda s: s["num"])

    return templates.TemplateResponse("etappe.html", {
        "request": request,
        "stage": stage,
        "riders_by_id": riders_by_id,
        "standings": standings,
        "all_stages": all_stages,
        "num": num,
    })


@app.get("/etappenplan", response_class=HTMLResponse)
async def etappenplan(request: Request):
    route = load("route.json")
    today_str = date.today().isoformat()
    route_sorted = sorted(route, key=lambda s: s["datum"])
    future = [s for s in route_sorted if s["datum"] > today_str]
    tomorrow_str = future[0]["datum"] if future else ""
    return templates.TemplateResponse("etappenplan.html", {
        "request": request,
        "route": route_sorted,
        "today": today_str,
        "tomorrow": tomorrow_str,
    })


@app.get("/giro", response_class=HTMLResponse)
async def giro_fahrerliste(request: Request):
    riders = load("riders.json")

    def split_name(name):
        parts = name.split()
        i = 0
        while i < len(parts) and parts[i].isupper():
            i += 1
        if i == 0:
            i = 1
        return " ".join(parts[:i]), " ".join(parts[i:])

    teams: dict = {}
    for r in riders:
        nachname, vorname = split_name(r["name"])
        teams.setdefault(r["team"], []).append(
            {**r, "nachname": nachname, "vorname": vorname}
        )
    for t in teams:
        teams[t].sort(key=lambda x: (-x["wert"], x["nachname"]))

    team_list = sorted(teams.items())

    return templates.TemplateResponse("giro.html", {
        "request": request,
        "team_list": team_list,
        "total_riders": len(riders),
    })


# ── Admin pages ───────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_index(request: Request):
    players = load("players.json")
    riders = load("riders.json")
    stages = load("stages.json")
    return templates.TemplateResponse("admin/index.html", {
        "request": request,
        "player_count": len(players),
        "rider_count": len(riders),
        "stage_count": len(stages),
    })


@app.get("/admin/fahrer", response_class=HTMLResponse)
async def admin_fahrer(request: Request):
    riders = load("riders.json")
    riders_sorted = sorted(riders, key=lambda r: r.get("name", ""))
    teams = sorted({r["team"] for r in riders})
    return templates.TemplateResponse("admin/fahrer.html", {
        "request": request,
        "riders": riders_sorted,
        "teams": teams,
    })


@app.post("/admin/fahrer/add")
async def admin_fahrer_add(
    name: str = Form(...),
    team: str = Form(...),
    wert: float = Form(...),
):
    riders = load("riders.json")
    if any(r["name"].lower() == name.lower() for r in riders):
        return RedirectResponse("/admin/fahrer?error=exists", status_code=303)
    riders.append({"id": next_id(riders), "name": name.strip(), "team": team.strip(), "wert": round(wert, 1)})
    save("riders.json", riders)
    return RedirectResponse("/admin/fahrer", status_code=303)


@app.post("/admin/fahrer/delete")
async def admin_fahrer_delete(rider_id: int = Form(...)):
    riders = load("riders.json")
    riders = [r for r in riders if r["id"] != rider_id]
    save("riders.json", riders)
    players = load("players.json")
    for p in players:
        p["rider_ids"] = [rid for rid in p.get("rider_ids", []) if rid != rider_id]
    save("players.json", players)
    return RedirectResponse("/admin/fahrer", status_code=303)


@app.get("/admin/spieler", response_class=HTMLResponse)
async def admin_spieler(request: Request):
    players = load("players.json")
    riders = load("riders.json")
    riders_by_id = {r["id"]: r for r in riders}
    riders_sorted = sorted(riders, key=lambda r: r.get("wert", 0), reverse=True)
    teams_sorted = sorted({r["team"] for r in riders})

    player_data = []
    for p in players:
        prs = [riders_by_id[rid] for rid in p.get("rider_ids", []) if rid in riders_by_id]
        budget_used = round(sum(r.get("wert", 0) for r in prs), 1)
        player_data.append({**p, "riders": prs, "budget_used": budget_used})

    return templates.TemplateResponse("admin/spieler.html", {
        "request": request,
        "players": player_data,
        "all_riders": riders_sorted,
        "teams": teams_sorted,
    })


@app.post("/admin/spieler/add")
async def admin_spieler_add(name: str = Form(...)):
    players = load("players.json")
    players.append({"id": next_id(players), "name": name.strip(), "rider_ids": []})
    save("players.json", players)
    return RedirectResponse("/admin/spieler", status_code=303)


@app.post("/admin/spieler/delete")
async def admin_spieler_delete(player_id: int = Form(...)):
    players = load("players.json")
    players = [p for p in players if p["id"] != player_id]
    save("players.json", players)
    return RedirectResponse("/admin/spieler", status_code=303)


@app.post("/admin/spieler/{player_id}/fahrer")
async def admin_spieler_fahrer(
    request: Request,
    player_id: int,
    rider_ids: List[int] = Form(default=[]),
):
    players = load("players.json")
    for p in players:
        if p["id"] == player_id:
            p["rider_ids"] = rider_ids
    save("players.json", players)
    return RedirectResponse("/admin/spieler", status_code=303)


@app.get("/admin/etappe/{num}", response_class=HTMLResponse)
async def admin_etappe(request: Request, num: int):
    stages = load("stages.json")
    riders = load("riders.json")
    riders_sorted = sorted(riders, key=lambda r: r.get("name", ""))
    teams = sorted({r["team"] for r in riders})

    stage = next((s for s in stages if s["num"] == num), None)
    if not stage:
        stage = {
            "num": num,
            "date": "",
            "name": f"Etappe {num}",
            "is_ttt": False,
            "results": {
                "etappe": [], "leader": [], "berg": [], "punkte": [],
                "nachwuchs": [], "team_day": [], "ttt_order": [],
            },
        }

    return templates.TemplateResponse("admin/etappe.html", {
        "request": request,
        "stage": stage,
        "riders": riders_sorted,
        "teams": teams,
        "num": num,
    })


@app.post("/admin/etappe/{num}")
async def admin_etappe_save(request: Request, num: int):
    form = await request.form()
    stages = load("stages.json")

    def ids(key):
        vals = form.getlist(key)
        result = []
        for v in vals:
            v = v.strip()
            if v:
                try:
                    result.append(int(v))
                except ValueError:
                    pass
        return result

    def teams_list(key):
        return [v.strip() for v in form.getlist(key) if v.strip()]

    stage_data = {
        "num": num,
        "date": form.get("date", ""),
        "name": form.get("name", f"Etappe {num}"),
        "is_ttt": form.get("is_ttt") == "on",
        "results": {
            "etappe": ids("etappe"),
            "leader": ids("leader"),
            "berg": ids("berg"),
            "punkte": ids("punkte"),
            "nachwuchs": ids("nachwuchs"),
            "team_day": teams_list("team_day"),
            "ttt_order": teams_list("ttt_order"),
        },
    }

    existing = next((s for s in stages if s["num"] == num), None)
    if existing:
        stages = [s if s["num"] != num else stage_data for s in stages]
    else:
        stages.append(stage_data)
        stages.sort(key=lambda s: s["num"])

    save("stages.json", stages)
    return RedirectResponse(f"/etappe/{num}", status_code=303)


@app.post("/admin/etappe/{num}/delete")
async def admin_etappe_delete(num: int):
    stages = load("stages.json")
    stages = [s for s in stages if s["num"] != num]
    save("stages.json", stages)
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/final", response_class=HTMLResponse)
async def admin_final(request: Request):
    final = load("final.json")
    riders = load("riders.json")
    riders_sorted = sorted(riders, key=lambda r: r.get("name", ""))
    teams = sorted({r["team"] for r in riders})

    return templates.TemplateResponse("admin/final.html", {
        "request": request,
        "final": final,
        "riders": riders_sorted,
        "teams": teams,
    })


@app.post("/admin/final")
async def admin_final_save(request: Request):
    form = await request.form()

    def ids(key):
        vals = form.getlist(key)
        result = []
        for v in vals:
            v = v.strip()
            if v:
                try:
                    result.append(int(v))
                except ValueError:
                    pass
        return result

    def teams_list(key):
        return [v.strip() for v in form.getlist(key) if v.strip()]

    final = {
        "gesamt": ids("gesamt"),
        "berg_gesamt": ids("berg_gesamt"),
        "punkte_gesamt": ids("punkte_gesamt"),
        "nachwuchs_gesamt": ids("nachwuchs_gesamt"),
        "team_gesamt": teams_list("team_gesamt"),
        "finishers": ids("finishers"),
    }
    save("final.json", final)
    return RedirectResponse("/admin/final?saved=1", status_code=303)


@app.get("/admin/gc", response_class=HTMLResponse)
async def admin_gc(request: Request):
    gc = load("gc.json")
    riders = load("riders.json")
    riders_sorted = sorted(riders, key=lambda r: r.get("name", ""))
    teams = sorted({r["team"] for r in riders})
    return templates.TemplateResponse("admin/gc.html", {
        "request": request,
        "gc": gc,
        "riders": riders_sorted,
        "teams": teams,
    })


@app.post("/admin/gc")
async def admin_gc_save(request: Request):
    form = await request.form()

    def ids(key):
        vals = form.getlist(key)
        result = []
        for v in vals:
            v = v.strip()
            if v:
                try:
                    result.append(int(v))
                except ValueError:
                    pass
        return result

    def teams_list(key):
        return [v.strip() for v in form.getlist(key) if v.strip()]

    gc = {
        "gc": ids("gc"),
        "berg": ids("berg"),
        "punkte": ids("punkte"),
        "nachwuchs": ids("nachwuchs"),
        "team": teams_list("team"),
        "updated": form.get("updated", ""),
    }
    save("gc.json", gc)
    return RedirectResponse("/giro", status_code=303)
