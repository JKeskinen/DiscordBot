import os, json, sqlite3, datetime
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB = os.path.join(ROOT, 'data', 'discordbot.db')
REPORT_PATH = os.path.join(ROOT, 'data', 'competitions_report.json')
print('DB:', DB)
conn = sqlite3.connect(DB)
cur = conn.cursor()

# 1) Import class_definitions.json into json_store
class_defs_repo = os.path.join(ROOT, 'class_definitions.json')
if os.path.exists(class_defs_repo):
    try:
        with open(class_defs_repo, 'r', encoding='utf-8') as f:
            cd = json.load(f)
        cd_text = json.dumps(cd, ensure_ascii=False)
        print('Importing class_definitions.json into json_store')
        try:
            cur.execute("INSERT OR REPLACE INTO json_store(name, content) VALUES(?,?)", ('class_definitions.json', cd_text))
            conn.commit()
            print('Imported class_definitions.json')
        except Exception as e:
            print('Error writing to json_store:', e)
    except Exception as e:
        print('Error reading class_definitions.json:', e)
else:
    print('class_definitions.json not found in repo root')

# 2) Create normalized competitions table
cur.execute('''
CREATE TABLE IF NOT EXISTS competitions (
    comp_id TEXT PRIMARY KEY,
    name TEXT,
    url TEXT,
    registered INTEGER,
    cap_limit INTEGER,
    remaining INTEGER,
    queued INTEGER,
    note TEXT,
    metrix_header_empty INTEGER,
    source_rowid INTEGER
)
''')
conn.commit()

# 3) Populate from CAPACITY_SCAN_RESULTS.results
cur.execute("SELECT rowid, results FROM CAPACITY_SCAN_RESULTS")
rows = cur.fetchall()
inserted = 0
for row in rows:
    rowid, results_txt = row
    try:
        items = json.loads(results_txt)
    except Exception as e:
        print('Could not parse results JSON for row', rowid, e)
        continue
    for it in items:
        comp_id = it.get('id')
        name = it.get('name')
        url = it.get('url')
        cap = it.get('capacity_result') or {}
        def to_int(v):
            try:
                if v is None:
                    return None
                return int(v)
            except Exception:
                return None
        registered = to_int(cap.get('registered'))
        cap_limit = to_int(cap.get('limit'))
        remaining = to_int(cap.get('remaining'))
        queued = to_int(cap.get('queued'))
        note = cap.get('note')
        mhe = 1 if cap.get('metrix_header_empty') else 0
        try:
            cur.execute('INSERT OR REPLACE INTO competitions(comp_id,name,url,registered,cap_limit,remaining,queued,note,metrix_header_empty,source_rowid) VALUES(?,?,?,?,?,?,?,?,?,?)', (comp_id, name, url, registered, cap_limit, remaining, queued, note, mhe, rowid))
            inserted += 1
        except Exception as e:
            print('Error inserting competition', comp_id, e)
conn.commit()
print('Inserted/updated competitions:', inserted)

# 4) Generate report: waitlists and missing registration/limit
report = {'generated_at': datetime.datetime.utcnow().isoformat() + 'Z', 'waitlists': [], 'missing_registered': [], 'missing_limit': []}
cur.execute('SELECT comp_id, name, registered, cap_limit, remaining, queued, note FROM competitions WHERE queued IS NOT NULL AND queued>0 ORDER BY queued DESC')
for r in cur.fetchall():
    report['waitlists'].append({'comp_id': r[0], 'name': r[1], 'registered': r[2], 'cap_limit': r[3], 'remaining': r[4], 'queued': r[5], 'note': r[6]})
cur.execute('SELECT comp_id, name FROM competitions WHERE registered IS NULL ORDER BY comp_id')
for r in cur.fetchall():
    report['missing_registered'].append({'comp_id': r[0], 'name': r[1]})
cur.execute('SELECT comp_id, name FROM competitions WHERE cap_limit IS NULL ORDER BY comp_id')
for r in cur.fetchall():
    report['missing_limit'].append({'comp_id': r[0], 'name': r[1]})

# save report
with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('Report written to', REPORT_PATH)

# Print summary
print('\nSummary:')
print(' Waitlists:', len(report['waitlists']))
for it in report['waitlists']:
    print('  ', it['comp_id'], it['name'], 'queued=', it['queued'])
print(' Missing registered:', len(report['missing_registered']))
print(' Missing limit:', len(report['missing_limit']))

conn.close()
print('Done')
