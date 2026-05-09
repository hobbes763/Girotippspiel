import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from points import calculate_standings, calculate_player_detail, calculate_all_rider_points
from updater import check_and_update, load_config, save_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_PASSWORD = "Girobogo"
SESSION_SECRET = "bogus-giro-2026-s3cr3t-k3y-abc"

scheduler = AsyncIOScheduler(timezone="Europe/Zurich")


def _schedule_jobs():
    scheduler.add_job(
        _auto_update_task,
        CronTrigger(hour=18, minute=0, timezone="Europe/Zurich"),
        id="update_1800",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        _auto_update_task,
        CronTrigger(hour=18, minute=30, timezone="Europe/Zurich"),
        id="update_1830",
        replace_existing=True,
        misfire_grace_time=300,
    )


def _remove_jobs():
    for job_id in ("update_1800", "update_1830"):
        job = scheduler.get_job(job_id)
        if job:
            job.remove()


async def _auto_update_task():
    logger.info("Automatische Aktualisierung gestartet (Scheduler)...")
    result = await asyncio.to_thread(check_and_update)
    logger.info(f"Auto-Update abgeschlossen: {result['message']}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    if cfg.get("auto_update_enabled", True):
        _schedule_jobs()
    scheduler.start()
    logger.info("Scheduler gestartet.")
    yield
    scheduler.shutdown(wait=False)
    logger.info("Scheduler gestoppt.")


app = FastAPI(title="Bogos Giro Tippspiel 2026", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=28800)
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
    (DATA_DIR / filename).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def next_id(items):
    return max((i["id"] for i in items), default=0) + 1


def _is_admin(request: Request) -> bool:
    return request.session.get("admin") is True


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
    stage_maxes = (
        [max((s["stage_totals"][j]["pts"] for s in standings), default=0) for j in range(len(stages))]
        if standings and stages else []
    )
    return templates.TemplateResponse("rangliste.html", {
        "request": request,
        "standings": standings,
        "stages": stages,
        "stages_played": len(stages),
        "today_stage": today_stage,
        "tomorrow_stage": tomorrow_stage,
        "stage_maxes": stage_maxes,
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
    return templates.TemplateResponse("etappenplan.html", {
        "request": request,
        "route": route_sorted,
        "today": today_str,
    })


@app.get("/teilnehmer", response_class=HTMLResponse)
async def teilnehmer_liste(request: Request):
    players = sorted(load("players.json"), key=lambda p: p["name"].lower())
    if players:
        return RedirectResponse(f"/teilnehmer/{players[0]['id']}", status_code=302)
    return templates.TemplateResponse("teilnehmer.html", {
        "request": request, "players": players, "active_player": None,
        "active_riders": [], "active_id": None,
    })


@app.get("/teilnehmer/{player_id}", response_class=HTMLResponse)
async def teilnehmer_detail(request: Request, player_id: int):
    players = sorted(load("players.json"), key=lambda p: p["name"].lower())
    riders = load("riders.json")
    stages = load("stages.json")
    final = load("final.json")
    riders_by_id = {r["id"]: r for r in riders}

    active_player = next((p for p in players if p["id"] == player_id), None)
    if not active_player:
        raise HTTPException(404, "Teilnehmer nicht gefunden")

    rider_details = calculate_player_detail(active_player, riders, stages, final)
    rider_pts_by_id = {rd["rider"]["id"]: rd["total"] for rd in rider_details}
    active_riders = sorted(
        [riders_by_id[rid] for rid in active_player.get("rider_ids", []) if rid in riders_by_id],
        key=lambda r: rider_pts_by_id.get(r["id"], 0),
        reverse=True,
    )
    player_total = sum(rd["total"] for rd in rider_details)

    return templates.TemplateResponse("teilnehmer.html", {
        "request": request,
        "players": players,
        "active_player": active_player,
        "active_riders": active_riders,
        "rider_pts_by_id": rider_pts_by_id,
        "player_total": player_total,
        "active_id": player_id,
    })


@app.get("/punktewertung", response_class=HTMLResponse)
async def punktewertung(request: Request):
    return templates.TemplateResponse("punktewertung.html", {"request": request})


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


@app.get("/giro/punkte", response_class=HTMLResponse)
async def giro_punkte_pro_fahrer(request: Request):
    riders = load("riders.json")
    stages = load("stages.json")
    final = load("final.json")
    rider_points = calculate_all_rider_points(riders, stages, final)
    return templates.TemplateResponse("giro_punkte.html", {
        "request": request,
        "rider_points": rider_points,
        "total_riders": len(riders),
    })


# ── Admin: Auth ───────────────────────────────────────────────────────────────

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if _is_admin(request):
        return RedirectResponse("/admin", status_code=302)
    error = request.query_params.get("error")
    return templates.TemplateResponse("admin/login.html", {
        "request": request,
        "error": error,
    })


@app.post("/admin/login")
async def admin_login(request: Request, password: str = Form(...)):
    if hmac.compare_digest(password, ADMIN_PASSWORD):
        request.session["admin"] = True
        return RedirectResponse("/admin", status_code=303)
    return RedirectResponse("/admin/login?error=1", status_code=303)


@app.get("/admin/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


# ── Admin: Update ─────────────────────────────────────────────────────────────

@app.post("/admin/update")
async def admin_update_now(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    result = await asyncio.to_thread(check_and_update)
    request.session["update_flash"] = result["message"]
    request.session["update_count"] = result["updated"]
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/toggle-auto-update")
async def admin_toggle_auto_update(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    cfg = load_config()
    cfg["auto_update_enabled"] = not cfg.get("auto_update_enabled", True)
    save_config(cfg)
    if cfg["auto_update_enabled"]:
        _schedule_jobs()
    else:
        _remove_jobs()
    return RedirectResponse("/admin", status_code=303)


# ── Admin: Übersicht ──────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_index(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)

    players = load("players.json")
    riders = load("riders.json")
    stages = load("stages.json")

    cfg = load_config()
    update_flash = request.session.pop("update_flash", None)
    update_count = request.session.pop("update_count", None)

    return templates.TemplateResponse("admin/index.html", {
        "request": request,
        "player_count": len(players),
        "rider_count": len(riders),
        "stage_count": len(stages),
        "cfg": cfg,
        "update_flash": update_flash,
        "update_count": update_count,
    })


# ── Admin: Fahrer ─────────────────────────────────────────────────────────────

@app.get("/admin/fahrer", response_class=HTMLResponse)
async def admin_fahrer(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
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
    request: Request,
    name: str = Form(...),
    team: str = Form(...),
    wert: float = Form(...),
):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    riders = load("riders.json")
    if any(r["name"].lower() == name.lower() for r in riders):
        return RedirectResponse("/admin/fahrer?error=exists", status_code=303)
    riders.append({"id": next_id(riders), "name": name.strip(), "team": team.strip(), "wert": round(wert, 1)})
    save("riders.json", riders)
    return RedirectResponse("/admin/fahrer", status_code=303)


@app.post("/admin/fahrer/delete")
async def admin_fahrer_delete(request: Request, rider_id: int = Form(...)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    riders = load("riders.json")
    riders = [r for r in riders if r["id"] != rider_id]
    save("riders.json", riders)
    players = load("players.json")
    for p in players:
        p["rider_ids"] = [rid for rid in p.get("rider_ids", []) if rid != rider_id]
    save("players.json", players)
    return RedirectResponse("/admin/fahrer", status_code=303)


# ── Admin: Spieler ────────────────────────────────────────────────────────────

@app.get("/admin/spieler", response_class=HTMLResponse)
async def admin_spieler(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
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
async def admin_spieler_add(request: Request, name: str = Form(...)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    players = load("players.json")
    players.append({"id": next_id(players), "name": name.strip(), "rider_ids": []})
    save("players.json", players)
    return RedirectResponse("/admin/spieler", status_code=303)


@app.post("/admin/spieler/delete")
async def admin_spieler_delete(request: Request, player_id: int = Form(...)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
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
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    players = load("players.json")
    for p in players:
        if p["id"] == player_id:
            p["rider_ids"] = rider_ids
    save("players.json", players)
    return RedirectResponse("/admin/spieler", status_code=303)


# ── Admin: Etappe ─────────────────────────────────────────────────────────────

@app.get("/admin/etappe/{num}", response_class=HTMLResponse)
async def admin_etappe(request: Request, num: int):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
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
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
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
async def admin_etappe_delete(request: Request, num: int):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    stages = load("stages.json")
    stages = [s for s in stages if s["num"] != num]
    save("stages.json", stages)
    return RedirectResponse("/admin", status_code=303)


# ── Admin: Final ──────────────────────────────────────────────────────────────

@app.get("/admin/final", response_class=HTMLResponse)
async def admin_final(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
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
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
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


# ── Admin: GC ─────────────────────────────────────────────────────────────────

@app.get("/admin/gc", response_class=HTMLResponse)
async def admin_gc(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
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
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
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
