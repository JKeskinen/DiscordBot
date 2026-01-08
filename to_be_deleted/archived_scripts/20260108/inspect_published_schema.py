import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'discordbot.db')
if not os.path.exists(DB):
    print('DB not found at', DB)
    raise SystemExit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()
try:
    cur.execute("PRAGMA table_info('PUBLISHED_GAMES')")
    rows = cur.fetchall()
    print('PUBLISHED_GAMES columns:')
    for r in rows:
        print(r)
    print('\nSample row (if any):')
    try:
        cur.execute('SELECT * FROM PUBLISHED_GAMES LIMIT 1')
        print(cur.fetchone())
    except Exception as e:
        print('Could not fetch sample row:', e)
finally:
    conn.close()
