import json
from datetime import date

with open("data/stages.json", encoding="utf-8") as f:
    stages = json.load(f)
with open("data/route.json", encoding="utf-8") as f:
    route = json.load(f)

today = date.today().isoformat()
staged_nums = {s["num"] for s in stages}
missing = [r for r in route if r["datum"] <= today and r["num"] not in staged_nums]
print(f"Heute: {today}")
print(f"Bereits geladen: E{[s['num'] for s in stages]}")
print(f"Werden jetzt geprueft: E{[r['num'] for r in missing]}")
