import sqlite3, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB = os.path.join(ROOT, 'data', 'discordbot.db')
print('DB:', DB)
conn = sqlite3.connect(DB)
cur = conn.cursor()
print('Setting pragmas...')
# Set WAL
cur.execute("PRAGMA journal_mode = WAL;")
jm = cur.fetchone()
print('journal_mode ->', jm)
# Set synchronous
cur.execute("PRAGMA synchronous = NORMAL;")
cur.execute("PRAGMA synchronous;")
print('synchronous ->', cur.fetchone())
# Set wal_autocheckpoint
cur.execute("PRAGMA wal_autocheckpoint = 1000;")
cur.execute("PRAGMA wal_autocheckpoint;")
print('wal_autocheckpoint ->', cur.fetchone())

print('Creating indexes (if not exists)...')
try:
    cur.execute('CREATE INDEX IF NOT EXISTS idx_competitions_queued ON competitions(queued)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_competitions_caplimit ON competitions(cap_limit)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_alerts_id ON CAPACITY_ALERTS(id)')
    conn.commit()
    print('Indexes created')
except Exception as e:
    print('Error creating indexes:', e)

# Show indexes
cur.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' ORDER BY name")
for r in cur.fetchall():
    print(' index:', r)

conn.close()
print('Done')
