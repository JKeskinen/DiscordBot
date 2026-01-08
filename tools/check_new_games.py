import os, sys, json, sqlite3, datetime
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
from komento_koodit import data_store

DB = os.path.join(ROOT, 'data', 'discordbot.db')
conn = sqlite3.connect(DB)
cur = conn.cursor()

# Load PDGA list from json_store
cur.execute("SELECT content FROM json_store WHERE name='PDGA'")
row = cur.fetchone()
if not row:
    print('No PDGA list in json_store')
    pdga = []
else:
    pdga = json.loads(row[0])

# Get published game ids
cur.execute('SELECT id FROM PUBLISHED_GAMES')
published = set(r[0] for r in cur.fetchall())

# Detect new PDGA games
new_games = [g for g in pdga if g.get('id') not in published]
print('PDGA entries total:', len(pdga))
print('Published games total:', len(published))
print('New PDGA games (not in PUBLISHED_GAMES):', len(new_games))
for g in new_games[:20]:
    print('-', g.get('id'), g.get('name'), '|', g.get('date'), '|', g.get('url'))

# Weekly games: PDGA entries with date string containing this week numbers or within next 7 days if parsable
def parse_date(s):
    # try to find YYYY-MM-DD or DD/MM/YY or MM/DD/YY patterns
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    # try common formats
    fmts = ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%d/%m/%y %H:%M', '%d/%m/%y', '%m/%d/%y %H:%M', '%m/%d/%y']
    for f in fmts:
        try:
            return datetime.datetime.strptime(s, f)
        except Exception:
            pass
    # try to extract year 2026
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

# Check competitions table for changes / club members placeholder
cur.execute('SELECT comp_id, name, registered, cap_limit, remaining, queued FROM competitions')
comps = cur.fetchall()
print('\nKnown competitions in `competitions` table:', len(comps))
# show those with waitlist
waitlists = [c for c in comps if c[5] is not None and c[5]>0]
print(' Competitions with waitlist:', len(waitlists))
for c in waitlists:
    print('  waitlist:', c[0], c[1], 'queued=', c[5], 'registered=', c[2], 'limit=', c[3])

# For club members detection: check player_store or club_successes? quick heuristic: search for known player names in PUBLISHED_GAMES titles
# Load club players if available
club_players = []
try:
    cur.execute("SELECT content FROM json_store WHERE name='pelaaja.json'")
    r = cur.fetchone()
    if r:
        club_players = [p.get('name') for p in json.loads(r[0]) if isinstance(p, dict) and 'name' in p]
except Exception:
    club_players = []

print('\nClub players loaded:', len(club_players))
# naive check: for published games, see if any player names appear in title (unlikely)
cur.execute('SELECT id, title FROM PUBLISHED_GAMES')
published_rows = cur.fetchall()
congrats = []
for pid, title in published_rows:
    for player in club_players[:50]:
        if player and player.lower() in title.lower():
            congrats.append((pid, title, player))

print('\nCongratulation matches in published titles (naive):', len(congrats))
for c in congrats[:10]:
    print(' ', c)

conn.close()
print('\nDone')
