import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__) or '.', '..')))
from komento_koodit import metrix_stats as ms
from komento_koodit import commands_tulokset as ct
import requests

pid = '23665'
print('Fetching player', pid)
url = f"{ms.BASE_PLAYER_URL}{pid}"
try:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MetrixDiscordBot/1.0)"}
    r = requests.get(url, timeout=20, headers=headers)
    if r.status_code == 200 and r.text:
        # Save debug HTML for inspection
        try:
            with open('Metrix_player_23665_debug.html', 'w', encoding='utf-8') as f:
                f.write(r.text)
        except Exception:
            pass
        ps = ms._parse_player_stats(r.text, pid)
        print('Name:', ps.name)
        print('Rating:', ps.rating)
        print('Clubs parsed:', getattr(ps, 'clubs', []))
    else:
        print('HTTP fetch failed:', getattr(r, 'status_code', None))
        ps = None
except Exception as e:
    print('HTTP fetch exception:', e)
    ps = None

# If Lakeus in clubs, simulate increment
clubs = getattr(ps, 'clubs', []) or []
found = False
for c in clubs:
    if 'lakeus' in c.lower():
        found = True
        print('Detected Lakeus club:', c)
        ct._increment_club_success(pid, ps.name or 'Unknown', c, context='Manual check 23665')
        break
if not found:
    print('Lakeus not detected in parsed clubs')

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
