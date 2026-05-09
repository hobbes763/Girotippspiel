"""
Automatische Aktualisierung der Etappenresultate via ProCyclingStats.
Wird sowohl manuell (Admin-Button) als auch via Scheduler (18:00/18:30 Uhr) aufgerufen.
"""
import json
import logging
import unicodedata
from datetime import datetime, date
from difflib import SequenceMatcher
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
CONFIG_FILE = DATA_DIR / "update_config.json"

PCS_BASE = "https://www.procyclingstats.com/race/giro-d-italia/2026"
GIRO_STAGE_BASE = "https://www.giroditalia.it/en/classifiche/di-tappa"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de,en;q=0.9",
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _load(name: str):
    p = DATA_DIR / name
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _save(name: str, data):
    (DATA_DIR / name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {
        "last_updated": None,
        "last_check": None,
        "auto_update_enabled": True,
        "last_message": "Noch keine Aktualisierung durchgeführt.",
        "stages_updated": [],
    }


def save_config(cfg: dict):
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _norm(s: str) -> str:
    """Name normalisieren: Akzente entfernen, uppercase, strip."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.upper().strip()


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def match_rider(name_pcs: str, riders: list) -> int | None:
    """PCS-Fahrername zu interner ID matchen."""
    norm = _norm(name_pcs)
    for r in riders:
        if _norm(r["name"]) == norm:
            return r["id"]
    # Fuzzy-Match
    best_id, best_s = None, 0.0
    for r in riders:
        s = _sim(_norm(r["name"]), norm)
        if s > best_s:
            best_s, best_id = s, r["id"]
    return best_id if best_s >= 0.82 else None


def match_team(team_pcs: str, known_teams: set) -> str:
    """PCS-Teamname zum internen Teamnamen matchen."""
    norm_pcs = _norm(team_pcs).replace("-", " ").replace("  ", " ")
    for t in known_teams:
        if _norm(t).replace("-", " ").replace("  ", " ") == norm_pcs:
            return t
    best_t, best_s = team_pcs, 0.0
    for t in known_teams:
        s = _sim(_norm(t).replace("-", " "), norm_pcs)
        if s > best_s:
            best_s, best_t = s, t
    return best_t if best_s >= 0.72 else team_pcs


# ── Giro Super Team ──────────────────────────────────────────────────────────

def fetch_super_team_from_giro(stage_num: int, riders: list, known_teams: set) -> list:
    """Super Team Fahrer von giroditalia.it holen. Gibt Liste der Rider-IDs zurück."""
    url = f"{GIRO_STAGE_BASE}/{stage_num}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    panel = soup.find(attrs={"data-category": "tab-classifica-CLSQA"})
    if not panel:
        return []

    super_teams = set()
    for line in panel.find_all("div", class_="line-table"):
        if "display: none" in (line.get("style") or ""):
            continue
        link = line.find("a")
        if link:
            team_raw = link.get_text(strip=True)
            matched = match_team(team_raw, known_teams)
            super_teams.add(matched)

    return [r["id"] for r in riders if r["team"] in super_teams]


# ── PCS-Parsing ───────────────────────────────────────────────────────────────

def _find_result_ul(soup: BeautifulSoup, *keywords: str) -> BeautifulSoup | None:
    """
    Sucht nach einer PCS result-cont-Sektion deren Überschrift eines der Keywords enthält.
    Gibt das ul-Element zurück, falls gefunden.
    """
    for div in soup.find_all("div", class_=lambda c: c and "result" in c.split()):
        heading = div.find(["h2", "h3", "h4"])
        if heading:
            heading_text = heading.get_text(strip=True).lower()
            if any(kw.lower() in heading_text for kw in keywords):
                ul = div.find("ul")
                if ul:
                    return ul
    return None


def _rider_ids_from_ul(ul, max_n: int, riders: list) -> list:
    result = []
    for li in ul.find_all("li"):
        if len(result) >= max_n:
            break
        link = li.find("a", href=lambda h: h and "/rider/" in (h or ""))
        if link:
            rid = match_rider(link.get_text(strip=True), riders)
            if rid and rid not in result:
                result.append(rid)
    return result


def _teams_from_ul(ul, max_n: int, known_teams: set) -> list:
    result = []
    for li in ul.find_all("li"):
        if len(result) >= max_n:
            break
        link = li.find("a", href=lambda h: h and "/team/" in (h or ""))
        if not link:
            link = li.find("a")
        if link:
            team = match_team(link.get_text(strip=True), known_teams)
            if team and team not in result:
                result.append(team)
    return result


def fetch_stage_from_pcs(
    stage_num: int,
    riders: list,
    route_stage: dict,
    known_teams: set,
) -> tuple:
    """
    Lädt Etappenresultate von PCS und gibt (stage_data, message) zurück.
    stage_data ist None wenn das Laden fehlgeschlagen ist.
    """
    url = f"{PCS_BASE}/stage-{stage_num}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        return None, f"E{stage_num}: Verbindungsfehler – {e}"

    if resp.status_code == 404:
        return None, f"E{stage_num}: Seite auf PCS nicht gefunden."
    if resp.status_code != 200:
        return None, f"E{stage_num}: HTTP-Fehler {resp.status_code}."

    soup = BeautifulSoup(resp.text, "lxml")

    is_ttt = "ttt" in route_stage.get("typ", "").lower() or \
             "team time" in route_stage.get("name", "").lower()

    results = {
        "etappe": [], "leader": [], "berg": [],
        "punkte": [], "nachwuchs": [], "team_day": [], "ttt_order": [],
        "super_team": [],
    }

    # 1. Etappenresultat (Top 12)
    for kw in ["stage result", "stage", "finish", "result"]:
        ul = _find_result_ul(soup, kw)
        if ul:
            ids = _rider_ids_from_ul(ul, 12, riders)
            if ids:
                results["etappe"] = ids
                break

    # Fallback: erste ul.list auf der Seite
    if not results["etappe"]:
        for ul in soup.find_all("ul", class_=lambda c: c and "list" in (c or "").split()):
            ids = _rider_ids_from_ul(ul, 12, riders)
            if ids:
                results["etappe"] = ids
                break

    if not results["etappe"]:
        return None, f"E{stage_num}: Keine Resultate gefunden (noch nicht abgeschlossen?)."

    # 2. GC nach Etappe (Top 10)
    for kw in ["general classification", "gc", "overall"]:
        ul = _find_result_ul(soup, kw)
        if ul:
            ids = _rider_ids_from_ul(ul, 10, riders)
            if ids:
                results["leader"] = ids
                break

    # 3. Bergwertung (Top 5)
    for kw in ["mountain", "climb", "berg", "kom"]:
        ul = _find_result_ul(soup, kw)
        if ul:
            ids = _rider_ids_from_ul(ul, 5, riders)
            if ids:
                results["berg"] = ids
                break

    # 4. Punktewertung (Top 5)
    for kw in ["point", "sprint", "cycliste"]:
        ul = _find_result_ul(soup, kw)
        if ul:
            ids = _rider_ids_from_ul(ul, 5, riders)
            if ids:
                results["punkte"] = ids
                break

    # 5. Nachwuchswertung (Top 3)
    for kw in ["young", "youth", "u23", "white jersey", "maglia bianca"]:
        ul = _find_result_ul(soup, kw)
        if ul:
            ids = _rider_ids_from_ul(ul, 3, riders)
            if ids:
                results["nachwuchs"] = ids
                break

    # 6. Teamwertung (Top 3/4)
    for kw in ["team"]:
        ul = _find_result_ul(soup, kw)
        if ul:
            if is_ttt:
                results["ttt_order"] = _teams_from_ul(ul, 4, known_teams)
            else:
                results["team_day"] = _teams_from_ul(ul, 3, known_teams)
            break

    # 7. Super Team von giroditalia.it
    results["super_team"] = fetch_super_team_from_giro(stage_num, riders, known_teams)

    stage_data = {
        "num": stage_num,
        "date": route_stage.get("datum", ""),
        "name": f"{route_stage.get('von', '')} – {route_stage.get('bis', '')}",
        "is_ttt": is_ttt,
        "results": results,
    }

    filled = sum(1 for v in results.values() if v)
    return stage_data, f"E{stage_num} ({stage_data['name']}) importiert ({filled}/8 Felder)."


# ── Haupt-Update-Funktion ─────────────────────────────────────────────────────

def check_and_update() -> dict:
    """
    Prüft auf fehlende Etappenresultate und lädt diese von PCS.
    Gibt {updated, message, stages} zurück.
    """
    cfg = load_config()
    now = datetime.now()
    cfg["last_check"] = now.isoformat(timespec="seconds")

    route = _load("route.json")
    stages = _load("stages.json")
    riders = _load("riders.json")
    known_teams = {r["team"] for r in riders}

    today = date.today().isoformat()
    staged_nums = {s["num"] for s in stages}

    # Etappen die abgeschlossen sein sollten (Datum <= heute, noch nicht in stages.json)
    missing = [r for r in route if r["datum"] <= today and r["num"] not in staged_nums]

    if not missing:
        cfg["last_message"] = "Keine neuen Etappenresultate vorhanden."
        save_config(cfg)
        return {"updated": 0, "message": cfg["last_message"], "stages": []}

    updated_nums, msgs = [], []

    for rs in missing:
        data, msg = fetch_stage_from_pcs(rs["num"], riders, rs, known_teams)
        msgs.append(msg)
        logger.info(msg)
        if data:
            stages.append(data)
            updated_nums.append(rs["num"])

    if updated_nums:
        stages.sort(key=lambda s: s["num"])
        _save("stages.json", stages)
        cfg["last_updated"] = now.isoformat(timespec="seconds")
        prev = cfg.get("stages_updated", [])
        cfg["stages_updated"] = sorted(set(prev + updated_nums))

    cfg["last_message"] = " | ".join(msgs) if msgs else "Keine Aktualisierung."
    save_config(cfg)

    return {
        "updated": len(updated_nums),
        "message": cfg["last_message"],
        "stages": updated_nums,
    }
