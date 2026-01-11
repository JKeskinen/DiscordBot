#!/usr/bin/env python3
"""
Assign club ranking points for an event's top-5 and save into the DB.
Usage:
  python scripts/assign_points.py <event_id> <player1_metrix_id>:<name> <player2_metrix_id>:<name> ...
Example:
  python scripts/assign_points.py 3512046 12345:Maija 23456:Teppo 34567:Juho 45678:Liisa 56789:Kari

Points distribution: 1..5 -> 100,70,40,10,-20
"""
import sqlite3, os, sys, datetime
if len(sys.argv) < 3:
    print('Usage: assign_points.py <event_id> <metrix_id:name> [..up to 5]')
    raise SystemExit(1)

event_id = sys.argv[1]
players = sys.argv[2:]
entries = []
for i,p in enumerate(players[:5], start=1):
    if ':' in p:
        mid,name = p.split(':',1)
    else:
        mid = p
        name = ''
    entries.append((i, mid.strip(), name.strip()))
# compute points: linear from 100 to -20 over positions 1..5
points_map = {pos: 100 + (pos-1)*-30 for pos in range(1,6)}
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
db = os.path.join(root, 'data', 'discordbot.db')
conn = sqlite3.connect(db)
cur = conn.cursor()
# create table if not exists
cur.execute('''CREATE TABLE IF NOT EXISTS club_ranking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metrix_id TEXT,
    name TEXT,
    event_id TEXT,
    position INTEGER,
    points INTEGER,
    created_at TEXT
)''')
now = datetime.datetime.utcnow().isoformat() + 'Z'
for pos, mid, name in entries:
    pts = points_map.get(pos, 0)
    cur.execute('INSERT INTO club_ranking (metrix_id, name, event_id, position, points, created_at) VALUES (?,?,?,?,?,?)', (mid or None, name or None, event_id, pos, pts, now))
conn.commit()
print('Inserted', len(entries), 'rows into club_ranking')
conn.close()
