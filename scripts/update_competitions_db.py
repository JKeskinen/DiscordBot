#!/usr/bin/env python3
import sqlite3, os, json
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
db = os.path.join(root, 'data', 'discordbot.db')
print('DB', db)
if not os.path.exists(db):
    print('DB not found')
    raise SystemExit(1)
conn = sqlite3.connect(db)
cur = conn.cursor()
# Show schema for competitions table
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitions';")
exists = bool(cur.fetchone())
print('competitions table exists?', exists)
if exists:
    cur.execute('PRAGMA table_info(competitions)')
    print('schema:', cur.fetchall())
# Query current rows for the two events
for cid in ('3509798','3512046'):
    cur.execute('SELECT comp_id, url, registered, cap_limit FROM competitions WHERE comp_id=? OR url LIKE ?', (cid, '%'+cid+'%'))
    rows = cur.fetchall()
    print(cid, 'rows found:', rows)
# Update rows (best-effort)
try:
    cur.execute("UPDATE competitions SET registered=?, cap_limit=? WHERE comp_id=?", (76,72,'3509798'))
    cur.execute("UPDATE competitions SET registered=?, cap_limit=? WHERE comp_id=?", (51,84,'3512046'))
    conn.commit()
    print('DB updated (attempted)')
except Exception as e:
    print('DB update error', e)
finally:
    conn.close()
