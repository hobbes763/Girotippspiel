import xlrd, json
from difflib import get_close_matches

wb = xlrd.open_workbook(r'C:\Users\domwe\Downloads\Giro 2026 Etppe 1.xls')
with open('data/riders.json', encoding='utf-8') as f:
    riders_list = json.load(f)
with open('data/players.json', encoding='utf-8') as f:
    players_json = json.load(f)

def normalize(s):
    return str(s).strip().lower()

# Build name->id map from riders.json
rider_lookup = {}
for r in riders_list:
    n = normalize(r['name'])
    rider_lookup[n] = r['id']
    parts = n.split()
    if len(parts) == 2:
        rider_lookup[parts[1] + ' ' + parts[0]] = r['id']

all_rider_names = [normalize(r['name']) for r in riders_list]
id_to_name = {r['id']: r['name'] for r in riders_list}

def find_rider_id(excel_name):
    n = normalize(excel_name)
    if n in rider_lookup:
        return rider_lookup[n], 'exact'
    parts = n.split()
    if len(parts) == 2:
        rev = parts[1] + ' ' + parts[0]
        if rev in rider_lookup:
            return rider_lookup[rev], 'reversed'
    matches = get_close_matches(n, all_rider_names, n=1, cutoff=0.7)
    if matches:
        return rider_lookup[matches[0]], f'fuzzy:{matches[0]}'
    return None, 'NOT FOUND'

# Skip "Sven (2)" - it's a draft version, use "Sven" as the final
player_sheets = [s for s in wb.sheet_names() if s not in ('Fahrerliste', 'Punktetabelle', 'Sven (2)')]

# Parse all players from Excel
excel_player_riders = {}
for sheet_name in player_sheets:
    ws = wb.sheet_by_name(sheet_name)
    rider_ids = []
    unmatched = []
    for i in range(3, ws.nrows):
        name = str(ws.cell_value(i, 0)).strip()
        if name and name != 'nan' and name.lower() != 'total' and not name.strip().isdigit():
            rid, method = find_rider_id(name)
            if rid:
                if rid not in rider_ids:  # avoid duplicates
                    rider_ids.append(rid)
            else:
                unmatched.append(name)
    excel_player_riders[sheet_name] = rider_ids
    if unmatched:
        print(f'WARNUNG - {sheet_name} nicht gefunden: {unmatched}')

# Update players.json
updated = 0
for p in players_json:
    sheet = next((s for s in excel_player_riders if normalize(s) == normalize(p['name'])), None)
    if sheet:
        old_ids = p['rider_ids']
        new_ids = excel_player_riders[sheet]
        if old_ids != new_ids:
            old_set = set(old_ids)
            new_set = set(new_ids)
            added = new_set - old_set
            removed = old_set - new_set
            print(f'\n{p["name"]}: {len(old_ids)} -> {len(new_ids)} Fahrer')
            if added:
                print(f'  + hinzugefuegt: {[id_to_name[i] for i in added]}')
            if removed:
                print(f'  - entfernt: {[id_to_name[i] for i in removed]}')
            p['rider_ids'] = new_ids
            updated += 1
    else:
        print(f'WARNUNG: Spieler "{p["name"]}" hat kein Excel-Sheet!')

with open('data/players.json', 'w', encoding='utf-8') as f:
    json.dump(players_json, f, ensure_ascii=False, indent=2)

print(f'\n{updated} Spieler aktualisiert. players.json gespeichert.')
