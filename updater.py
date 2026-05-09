"""
Automatische Aktualisierung der Etappenresultate via giroditalia.it.
Wird sowohl manuell (Admin-Button) als auch via Scheduler aufgerufen.
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

GIRO_STAGE_BASE = "https://www.giroditalia.it/en/classifiche/di-tappa"
GIRO_GENERAL_URL = "https://www.giroditalia.it/en/classifiche/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en,de;q=0.9",
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


def match_rider(name_raw: str, riders: list) -> int | None:
    """Fahrername zu interner ID matchen (exakt dann fuzzy)."""
    norm = _norm(name_raw)
    # Exakter Match
    for r in riders:
        if _norm(r["name"]) == norm:
            return r["id"]
    # Reversed (Vorname Nachname -> Nachname Vorname)
    parts = norm.split()
    if len(parts) == 2:
        rev = f"{parts[1]} {parts[0]}"
        for r in riders:
            if _norm(r["name"]) == rev:
                return r["id"]
    # Fuzzy-Match
    best_id, best_s = None, 0.0
    for r in riders:
        s = _sim(_norm(r["name"]), norm)
        if s > best_s:
            best_s, best_id = s, r["id"]
    return best_id if best_s >= 0.78 else None


def match_team(team_raw: str, known_teams: set) -> str:
    """Teamname zum internen Teamnamen matchen."""
    norm_raw = _norm(team_raw).replace("-", " ").replace("  ", " ")
    for t in known_teams:
        if _norm(t).replace("-", " ").replace("  ", " ") == norm_raw:
            return t
    best_t, best_s = team_raw, 0.0
    for t in known_teams:
        s = _sim(_norm(t).replace("-", " "), norm_raw)
        if s > best_s:
            best_s, best_t = s, t
    return best_t if best_s >= 0.72 else team_raw


# ── Giro-Website Parsing ──────────────────────────────────────────────────────

def _giro_name(link_el) -> str:
    """Fahrernamen aus Giro-Link-Element extrahieren (Vor- und Nachname mit Leerzeichen)."""
    return " ".join(link_el.stripped_strings)


def _riders_from_panel(panel, max_n: int, riders: list, include_hidden: bool = True) -> list:
    """Fahrer-IDs aus einem Giro-Klassifikations-Panel lesen."""
    result = []
    for line in panel.find_all("div", class_="line-table"):
        if len(result) >= max_n:
            break
        if not include_hidden and "display: none" in (line.get("style") or ""):
            continue
        a = line.find("a")
        if a:
            rid = match_rider(_giro_name(a), riders)
            if rid and rid not in result:
                result.append(rid)
    return result


def _teams_from_panel(panel, max_n: int, known_teams: set, visible_only: bool = True) -> list:
    """Team-Namen aus einem Giro-Panel lesen."""
    result = []
    for line in panel.find_all("div", class_="line-table"):
        if len(result) >= max_n:
            break
        if visible_only and "display: none" in (line.get("style") or ""):
            continue
        a = line.find("a")
        if a:
            matched = match_team(a.get_text(strip=True), known_teams)
            if matched and matched not in result:
                result.append(matched)
    return result


def fetch_stage_from_giro(
    stage_num: int,
    riders: list,
    route_stage: dict,
    known_teams: set,
) -> tuple:
    """
    Lädt Etappenresultate von giroditalia.it.
    Gibt (stage_data, dnf_ids, message) zurück.
    stage_data ist None wenn das Laden fehlgeschlagen ist.
    """
    stage_url = f"{GIRO_STAGE_BASE}/{stage_num}/"
    try:
        stage_resp = requests.get(stage_url, headers=HEADERS, timeout=15)
        gen_resp = requests.get(GIRO_GENERAL_URL, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        return None, [], f"E{stage_num}: Verbindungsfehler – {e}"

    if stage_resp.status_code != 200:
        return None, [], f"E{stage_num}: HTTP {stage_resp.status_code}."

    stage_soup = BeautifulSoup(stage_resp.text, "lxml")

    is_ttt = "ttt" in route_stage.get("typ", "").lower() or \
             "team time" in route_stage.get("name", "").lower()

    results = {
        "etappe": [], "leader": [], "berg": [],
        "punkte": [], "nachwuchs": [], "team_day": [], "ttt_order": [],
        "super_team": [],
    }

    # 1. Etappenresultat (ORARR – Top 12, inkl. hidden Zeilen)
    orarr = stage_soup.find(attrs={"data-category": "tab-classifica-ORARR"})
    if orarr:
        results["etappe"] = _riders_from_panel(orarr, 12, riders, include_hidden=True)

    if not results["etappe"]:
        return None, [], f"E{stage_num}: Keine Resultate auf giroditalia.it (noch nicht abgeschlossen?)."

    # 2. Super Team (CLSQA – nur sichtbare Teams)
    clsqa = stage_soup.find(attrs={"data-category": "tab-classifica-CLSQA"})
    if clsqa:
        super_teams = set(_teams_from_panel(clsqa, 10, known_teams, visible_only=True))
        results["super_team"] = [r["id"] for r in riders if r["team"] in super_teams]

    # 3. DNF-Fahrer dieser Etappe
    dnf_ids = []
    dnf_panel = stage_soup.find(attrs={"data-category": "tab-ritirati-tappa"})
    if dnf_panel:
        for line in dnf_panel.find_all("div", class_="line-table"):
            a = line.find("a")
            if a:
                rid = match_rider(_giro_name(a), riders)
                if rid:
                    dnf_ids.append(rid)

    # 4. Gesamtwertungen von /classifiche/
    if gen_resp.status_code == 200:
        gen_soup = BeautifulSoup(gen_resp.text, "lxml")

        # GC / Leader (Top 10)
        p = gen_soup.find(attrs={"data-category": "tab-classifica-CLGEN"})
        if p:
            results["leader"] = _riders_from_panel(p, 10, riders)

        # Bergwertung (Top 5)
        p = gen_soup.find(attrs={"data-category": "tab-classifica-CLGPMGEN"})
        if p:
            results["berg"] = _riders_from_panel(p, 5, riders)

        # Punktewertung (Top 5)
        p = gen_soup.find(attrs={"data-category": "tab-classifica-CLPUNGEN"})
        if p:
            results["punkte"] = _riders_from_panel(p, 5, riders)

        # Nachwuchs / Weißes Trikot (Top 3)
        p = gen_soup.find(attrs={"data-category": "tab-classifica-CLGENGIO"})
        if p:
            results["nachwuchs"] = _riders_from_panel(p, 3, riders)

        # Teamwertung (Top 3) – oder TTT
        p = gen_soup.find(attrs={"data-category": "tab-classifica-CLCOMGEN"})
        if p:
            if is_ttt:
                results["ttt_order"] = _teams_from_panel(p, 4, known_teams)
            else:
                results["team_day"] = _teams_from_panel(p, 3, known_teams)

    stage_data = {
        "num": stage_num,
        "date": route_stage.get("datum", ""),
        "name": f"{route_stage.get('von', '')} – {route_stage.get('bis', '')}",
        "is_ttt": is_ttt,
        "results": results,
    }

    filled = sum(1 for v in results.values() if v)
    return stage_data, dnf_ids, f"E{stage_num} ({stage_data['name']}) importiert ({filled}/8 Felder)."


# ── Haupt-Update-Funktion ─────────────────────────────────────────────────────

def check_and_update() -> dict:
    """
    Prüft auf fehlende Etappenresultate und lädt diese von giroditalia.it.
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
    all_dnf_ids = []

    for rs in missing:
        data, dnf_ids, msg = fetch_stage_from_giro(rs["num"], riders, rs, known_teams)
        msgs.append(msg)
        logger.info(msg)
        if data:
            stages.append(data)
            updated_nums.append(rs["num"])
            all_dnf_ids.extend(dnf_ids)

    if updated_nums:
        stages.sort(key=lambda s: s["num"])
        _save("stages.json", stages)

        # Aufgegebene Fahrer markieren
        if all_dnf_ids:
            dnf_set = set(all_dnf_ids)
            for r in riders:
                if r["id"] in dnf_set:
                    r["aufgegeben"] = True
            _save("riders.json", riders)

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
