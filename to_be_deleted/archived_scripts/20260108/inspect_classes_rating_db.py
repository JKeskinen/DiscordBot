import sqlite3, json, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB = os.path.join(ROOT, 'data', 'discordbot.db')
print('DB:', DB)
conn = sqlite3.connect(DB)
cur = conn.cursor()
# list tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print('Tables:', tables)

def table_info(name):
    cur.execute(f"PRAGMA table_info('{name}')")
    return cur.fetchall()

for t in tables:
    info = table_info(t)
    print('\nTable:', t)
    print('Columns:')
    for col in info:
        # col: cid, name, type, notnull, dflt_value, pk
        print(' ', col[1], col[2])
    # show sample rows
    try:
        cur.execute(f"SELECT * FROM '{t}' LIMIT 5")
        rows = cur.fetchall()
        if rows:
            print('Sample rows:')
            for r in rows:
                print(' ', r)
        else:
            print('No rows')
    except Exception as e:
        print('Error reading rows:', e)

# Search for columns with class/rating/limit in name
keywords = ['class','rating','limit']
print('\nColumns matching keywords:')
for t in tables:
    info = table_info(t)
    matches = [col for col in info if any(k in col[1].lower() for k in keywords)]
    if matches:
        print('\nTable', t)
        for col in matches:
            print(' ', col[1], col[2])
        # show values for these columns from first 10 rows
        try:
            cur.execute(f"SELECT {', '.join([col[1] for col in matches])} FROM '{t}' LIMIT 10")
            rows = cur.fetchall()
            print(' Sample values:')
            for r in rows:
                print('  ', r)
        except Exception as e:
            print('  Error selecting columns:', e)

# Also check json_store for class_definitions or rating info
cur.execute("SELECT name, length(content) FROM json_store")
js = cur.fetchall()
print('\njson_store entries:')
for name, length in js:
    print(' ', name, length)
    if 'class' in name.lower() or 'rating' in name.lower():
        cur.execute("SELECT content FROM json_store WHERE name=?", (name,))
        c = cur.fetchone()[0]
        try:
            data = json.loads(c)
            print('  parsed type:', type(data).__name__)
            if isinstance(data, dict):
                for k in list(data)[:10]:
                    print('   key:', k)
            elif isinstance(data, list):
                print('   list len:', len(data))
                print('   sample:', data[:3])
        except Exception as e:
            print('  could not parse JSON:', e)

conn.close()
print('\nDone')
