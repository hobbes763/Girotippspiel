"""Ergänzt super_team für alle bereits gespeicherten Etappen in stages.json."""
import json
from updater import fetch_super_team_from_giro

with open("data/riders.json", encoding="utf-8") as f:
    riders = json.load(f)
with open("data/stages.json", encoding="utf-8") as f:
    stages = json.load(f)

known_teams = {r["team"] for r in riders}

for stage in stages:
    num = stage["num"]
    results = stage.setdefault("results", {})
    if results.get("super_team"):
        print(f"E{num}: super_team bereits vorhanden ({len(results['super_team'])} Fahrer), übersprungen.")
        continue
    ids = fetch_super_team_from_giro(num, riders, known_teams)
    results["super_team"] = ids
    print(f"E{num}: {len(ids)} Super Team Fahrer hinzugefügt.")

with open("data/stages.json", "w", encoding="utf-8") as f:
    json.dump(stages, f, ensure_ascii=False, indent=2)
print("\nstages.json gespeichert.")
