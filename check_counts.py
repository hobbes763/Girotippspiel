import json
with open('data/players.json', encoding='utf-8') as f:
    players = json.load(f)
with open('data/riders.json', encoding='utf-8') as f:
    riders = {r['id']: r['name'] for r in json.load(f)}

print('Spieler          | Anzahl Fahrer')
print('-' * 35)
for p in players:
    print(f'{p["name"]:17s}: {len(p["rider_ids"])} Fahrer')
