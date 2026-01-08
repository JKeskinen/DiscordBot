import os, sys, sqlite3, json
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
from komento_koodit import data_store

def read_json_store(conn, name):
    cur = conn.cursor()
    cur.execute('SELECT content FROM json_store WHERE name = ?', (name,))
    r = cur.fetchone()
    if not r or not r[0]:
        return None
    try:
        return json.loads(r[0])
    except Exception:
        return None

if __name__ == '__main__':
    db = data_store._db_path()
    print('DB path:', db)
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    # List all user tables
    cur.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = cur.fetchall()
    if not tables:
        print('No user tables found in DB')
    else:
        print('Found tables/views:')
        for name, typ in tables:
            print(' -', name, f'({typ})')
        print('\nPer-table summary:')
        for name, typ in tables:
            try:
                if name == 'json_store':
                    cur.execute('SELECT COUNT(*) FROM json_store')
                    total = cur.fetchone()[0]
                    print(f"{name}: {total} rows (json_store)")
                    cur.execute('SELECT name, substr(content,1,1000) FROM json_store LIMIT 3')
                    rows = cur.fetchall()
                    for rname, content in rows:
                        try:
                            data = json.loads(content) if content else None
                        except Exception:
                            data = None
                        if isinstance(data, list):
                            print(f'  {rname}: list with {len(data)} items; sample:', data[:3])
                        else:
                            print(f'  {rname}:', data)
                else:
                    cur.execute(f'SELECT COUNT(*) FROM "{name}"')
                    total = cur.fetchone()[0]
                    print(f"{name}: {total} rows")
                    cur.execute(f'SELECT * FROM "{name}" LIMIT 3')
                    rows = cur.fetchall()
                    for r in rows:
                        print('  sample row:', r)
            except Exception as e:
                print(f"{name}: error reading table - {e}")
    conn.close()
