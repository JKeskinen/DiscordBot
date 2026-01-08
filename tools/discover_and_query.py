import sys, os, json, sqlite3, datetime
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from komento_koodit import search_pdga_sfl as pdga_mod
from komento_koodit import data_store

DB = os.path.join(ROOT, 'data', 'discordbot.db')
print('DB:', DB)

print('Fetching competitions (this makes network requests)')
comps = pdga_mod.fetch_competitions(pdga_mod.DEFAULT_URL)
print('Fetched', len(comps), 'competitions')
pdga_entries = [c for c in comps if pdga_mod.is_pdga_entry(c)]
print('PDGA heuristics matched', len(pdga_entries), 'entries')

# Save PDGA list via module (uses data_store)
pdga_mod.save_pdga_list(pdga_entries, None)
print('Saved PDGA list to sqlite')

# Detection: new games vs PUBLISHED_GAMES, weekly, waitlists, club member checks
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Load PDGA list from json_store
cur.execute("SELECT content FROM json_store WHERE name='PDGA'")
row = cur.fetchone()
pdga = json.loads(row[0]) if row and row[0] else []

# Published games
cur.execute('SELECT id FROM PUBLISHED_GAMES')
published = set(r[0] for r in cur.fetchall())

new_games = [g for g in pdga if g.get('id') not in published]
print('\nNew PDGA games (not in PUBLISHED_GAMES):', len(new_games))
for g in new_games[:30]:
    print('-', g.get('id'), g.get('name'), '|', g.get('date'), '|', g.get('url'))

# Weekly games (next 7 days when parsable)
def parse_date(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    fmts = ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%d/%m/%y %H:%M', '%d/%m/%y', '%m/%d/%y %H:%M', '%m/%d/%y']
    for f in fmts:
        try:
            return datetime.datetime.strptime(s, f)
        except Exception:
            pass
    import re
    m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', s)
    if m:
        try:
            return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None
    return None

now = datetime.datetime.utcnow()
week_ahead = now + datetime.timedelta(days=7)
weekly = []
for g in pdga:
    d = parse_date(g.get('date'))
    if d and now <= d <= week_ahead:
        weekly.append((g.get('id'), g.get('name'), g.get('date'), g.get('url')))

print('\nPDGA games this week (parsed dates):', len(weekly))
for id,name,date,url in weekly:
    print(' *', id, name, date, url)

# Check competitions table for waitlists
cur.execute('SELECT comp_id, name, registered, cap_limit, remaining, queued FROM competitions')
comps = cur.fetchall()
waitlists = [c for c in comps if c[5] is not None and c[5]>0]
print('\nCompetitions with waitlist:', len(waitlists))
for c in waitlists:
    print('  waitlist:', c[0], c[1], 'queued=', c[5], 'registered=', c[2], 'limit=', c[3])

# Club members detection (if club player list available in json_store)
club_players = []
try:
    cur.execute("SELECT content FROM json_store WHERE name='pelaaja.json'")
    r = cur.fetchone()
    if r:
        club_players = [p.get('name') for p in json.loads(r[0]) if isinstance(p, dict) and 'name' in p]
except Exception:
    club_players = []

print('\nClub players loaded:', len(club_players))
# Naive match in published game titles
cur.execute('SELECT id, title FROM PUBLISHED_GAMES')
published_rows = cur.fetchall()
congrats = []
for pid, title in published_rows:
    for player in club_players[:200]:
        if player and player.lower() in title.lower():
            congrats.append((pid, title, player))

print('\nCongratulation matches in published titles (naive):', len(congrats))
for c in congrats[:10]:
    print(' ', c)

conn.close()
print('\nDone')
