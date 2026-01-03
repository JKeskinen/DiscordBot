import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__) or '.', '..')))
from komento_koodit import metrix_stats as ms
from komento_koodit import commands_tulokset as ct

pid = '23665'
debug_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__) or '.', '..')), f"Metrix_player_{pid}_debug.html")
print('Looking for debug HTML at', debug_path)

if not os.path.exists(debug_path):
    print('Debug HTML not found; aborting')
    sys.exit(1)

with open(debug_path, 'r', encoding='utf-8') as f:
    html = f.read()

ps = ms._parse_player_stats(html, pid)
print('Parsed name:', ps.name)
print('Parsed clubs:', getattr(ps, 'clubs', []))

found = False
for c in getattr(ps, 'clubs', []) or []:
    if 'lakeus' in c.lower():
        found = True
        print('Detected Lakeus club:', c)
        ct._increment_club_success(pid, ps.name or 'Unknown', c, context='Simulated local 23665')
        print(f"Simulated congrats: Onnittelut {ps.name}! Hyvä sijoitus seurassa {c} — kirjasin menestyksen.")
        break

if not found:
    print('No Lakeus club detected in local HTML')

# Print club_successes.json
try:
    with open(ct.CLUB_SUCCESS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print('\nclub_successes.json content:')
    print(json.dumps(data, ensure_ascii=False, indent=2))
except FileNotFoundError:
    print('\nclub_successes.json not found')
except Exception as e:
    print('\nFailed to read club_successes.json:', e)
