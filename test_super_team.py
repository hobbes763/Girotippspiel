import json
from updater import fetch_super_team_from_giro

with open("data/riders.json", encoding="utf-8") as f:
    riders = json.load(f)
known_teams = {r["team"] for r in riders}

ids = fetch_super_team_from_giro(1, riders, known_teams)
id_to_rider = {r["id"]: r for r in riders}

print(f"Super Team Etappe 1: {len(ids)} Fahrer")
for rid in ids:
    r = id_to_rider.get(rid)
    if r:
        print(f"  [{rid:3d}] {r['name']:35s} ({r['team']})")
