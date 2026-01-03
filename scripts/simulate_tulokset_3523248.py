import json
import sys, os
# Ensure project root is on sys.path so imports work when running the script directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__) or '.', '..')))
from komento_koodit import commands_tulokset as ct

url = ct._ensure_results_url('https://discgolfmetrix.com/3523248')
print('Fetching:', url)
res = ct._fetch_competition_results(url)
hc = ct._fetch_handicap_table(url)
import pprint
print('\n--- Parsed result structure ---')
pprint.pprint(res)
print('\n--- Raw Top3 Lines ---')
raw = ct._format_top3_lines_for_result(res, hc_present=bool(hc))
for l in raw:
    print(l)
print('\n--- HC Lines ---')
for l in (ct._format_hc_top3_lines(hc) if hc else []):
    print(l)

print('\nCLUB_DETECTIONS (module):', ct.CLUB_DETECTIONS)
# Simulate post: persist and print congrat messages
for d in list(ct.CLUB_DETECTIONS):
    mid = d.get('metrix_id')
    name = d.get('name')
    club = d.get('club')
    ct._increment_club_success(mid, name, club, context='Simulated 3523248')
    print(f"Simulated congrats: Onnittelut {name}! Hyvä sijoitus seurassa {club} — kirjasin menestyksen.")
ct.CLUB_DETECTIONS.clear()

# Print resulting persistence file (if any)
try:
    with open(ct.CLUB_SUCCESS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print('\nclub_successes.json content:')
    print(json.dumps(data, ensure_ascii=False, indent=2))
except FileNotFoundError:
    print('\nclub_successes.json not found')
except Exception as e:
    print('\nFailed to read club_successes.json:', e)
