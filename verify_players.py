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

player_sheets = [s for s in wb.sheet_names() if s not in ('Fahrerliste', 'Punktetabelle')]

results = {}
print('=== Fahrer aus Excel (ohne Total) ===\n')
for sheet_name in player_sheets:
    ws = wb.sheet_by_name(sheet_name)
    excel_riders = []
    for i in range(3, ws.nrows):
        name = str(ws.cell_value(i, 0)).strip()
        if name and name != 'nan' and name.lower() != 'total' and not name.strip().isdigit():
            excel_riders.append(name)
    results[sheet_name] = excel_riders
    print(f'{sheet_name}: {len(excel_riders)} Fahrer')

print()
print('=== Matching Excel->riders.json ===')
all_unmatched = []
player_updates = {}
for sheet_name, excel_riders in results.items():
    rider_ids = []
    unmatched = []
    for name in excel_riders:
        rid, method = find_rider_id(name)
        if rid:
            rider_ids.append((rid, name, method))
        else:
            unmatched.append(name)
            all_unmatched.append((sheet_name, name))
    player_updates[sheet_name] = rider_ids
    if unmatched:
        print(f'  {sheet_name} - NICHT GEFUNDEN: {unmatched}')

print()
print('=== Alle nicht gematchten Fahrer ===')
for player, name in all_unmatched:
    print(f'  {player}: "{name}"')

print()
print('=== Vergleich Excel vs JSON ===')
for p in players_json:
    sheet = next((s for s in player_updates if normalize(s) == normalize(p['name'])), None)
    if sheet:
        excel_count = len(player_updates[sheet])
        json_count = len(p['rider_ids'])
        status = 'OK' if excel_count == json_count else f'*** ABWEICHUNG (Excel:{excel_count} JSON:{json_count}) ***'
        print(f'  {p["name"]}: {status}')
    else:
        print(f'  {p["name"]}: Sheet nicht gefunden')
