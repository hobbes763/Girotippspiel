import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

with open("data/stages.json", encoding="utf-8") as f:
    stages = json.load(f)
with open("data/riders.json", encoding="utf-8") as f:
    riders = json.load(f)

id2name = {r["id"]: r["name"] for r in riders}
dnf = [r for r in riders if r.get("aufgegeben")]

for s in stages:
    r = s["results"]
    print(f"\nEtappe {s['num']} – {s['name']}")
    print(f"  Etappe top12: {[id2name.get(i,'?') for i in r.get('etappe',[])]}")
    print(f"  Leader  top10: {[id2name.get(i,'?') for i in r.get('leader',[])]}")
    print(f"  Berg    top5:  {[id2name.get(i,'?') for i in r.get('berg',[])]}")
    print(f"  Punkte  top5:  {[id2name.get(i,'?') for i in r.get('punkte',[])]}")
    print(f"  Nachwu. top3:  {[id2name.get(i,'?') for i in r.get('nachwuchs',[])]}")
    print(f"  SuperTm:       {len(r.get('super_team',[]))} Fahrer")

print(f"\nAufgegeben: {[r['name'] for r in dnf]}")
