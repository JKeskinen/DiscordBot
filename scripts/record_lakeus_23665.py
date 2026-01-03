import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__) or '.', '..')))
from komento_koodit import commands_tulokset as ct

mid = '23665'
name = 'Janne Sinisalmi'
club = 'Lakeus Disc Golf'

ct._increment_club_success(mid, name, club, context='Simulated from provided profile')
print('Recorded Lakeus success for', name)

try:
    with open(ct.CLUB_SUCCESS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print('\nclub_successes.json content:')
    print(json.dumps(data, ensure_ascii=False, indent=2))
except Exception as e:
    print('Failed to read club_successes.json:', e)
