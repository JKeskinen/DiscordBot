import os, sys, json, sqlite3
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
DB = os.path.join(ROOT, 'data', 'discordbot.db')
print('DB:', DB)
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT results, class_definitions FROM CAPACITY_SCAN_RESULTS LIMIT 1")
row = cur.fetchone()
if not row:
    print('No CAPACITY_SCAN_RESULTS found')
    sys.exit(1)
results_txt, class_defs_ref = row
print('class_definitions ref:', class_defs_ref)
try:
    items = json.loads(results_txt)
except Exception as e:
    print('Error parsing results JSON:', e)
    items = []

# Aggregate keys
top_keys_count = {}
cap_keys_count = {}
optional_flags = ['queued','metrix_header_empty','note']
null_registered = []
null_limit = []
queued_list = []
entries_with_classes = []
for it in items:
    for k in it.keys():
        top_keys_count[k] = top_keys_count.get(k,0)+1
    cap = it.get('capacity_result',{})
    for k in cap.keys():
        cap_keys_count[k] = cap_keys_count.get(k,0)+1
    if cap.get('registered') is None:
        null_registered.append((it.get('id'), it.get('name')))
    if cap.get('limit') is None:
        null_limit.append((it.get('id'), it.get('name')))
    if 'queued' in cap:
        queued_list.append((it.get('id'), it.get('name'), cap.get('queued')))
    # check nested 'classes' or 'class_definitions' inline
    if 'classes' in it or 'class_definitions' in it or 'class' in it:
        entries_with_classes.append((it.get('id'), it.get('name'), {k:it.get(k) for k in ('classes','class_definitions','class')}))

print('\nTop-level keys occurrence:')
for k,v in sorted(top_keys_count.items(), key=lambda x:-x[1]):
    print(f'  {k}: {v}')
print('\ncapacity_result keys occurrence:')
for k,v in sorted(cap_keys_count.items(), key=lambda x:-x[1]):
    print(f'  {k}: {v}')

print('\nCompetitions with null registered:', len(null_registered))
for cid,name in null_registered[:10]:
    print(' ', cid, name)
print('\nCompetitions with null limit:', len(null_limit))
for cid,name in null_limit[:10]:
    print(' ', cid, name)
print('\nCompetitions with queued entries:', len(queued_list))
for cid,name,q in queued_list[:10]:
    print(' ', cid, name, 'queued=', q)
print('\nCompetitions with inline class info:', len(entries_with_classes))
for cid,name,info in entries_with_classes[:10]:
    print(' ', cid, name, info)

# Show sample capacity_result entries
print('\nSample capacity_result entries (first 5):')
for it in items[:5]:
    cap = it.get('capacity_result',{})
    print(' ', it.get('id'), it.get('name'))
    print('   registered:', cap.get('registered'), 'limit:', cap.get('limit'), 'remaining:', cap.get('remaining'))
    extras = {k:v for k,v in cap.items() if k not in ('registered','limit','remaining')}
    if extras:
        print('   extras:', extras)

# Read class_definitions.json from repo if present
class_defs_path = os.path.join(ROOT, 'class_definitions.json')
if os.path.exists(class_defs_path):
    print('\nFound class_definitions.json in repo; loading...')
    try:
        with open(class_defs_path, 'r', encoding='utf-8') as f:
            cd = json.load(f)
        print('class_definitions type:', type(cd).__name__)
        if isinstance(cd, dict):
            print('  keys count:', len(cd))
            print('  sample keys:', list(cd.keys())[:20])
        elif isinstance(cd, list):
            print('  list length:', len(cd))
            print('  sample item:', cd[:3])
    except Exception as e:
        print('  error reading class_definitions.json:', e)
else:
    print('\nclass_definitions.json not found in repo root')

# Also check json_store for class_definitions
cur.execute("SELECT content FROM json_store WHERE name LIKE '%class_def%' OR name LIKE '%class%';")
rows = cur.fetchall()
if rows:
    print('\nclass-like entries in json_store:')
    for r in rows:
        try:
            data = json.loads(r[0])
            print('  parsed type:', type(data).__name__)
        except Exception as e:
            print('  could not parse json_store content:', e)

conn.close()
print('\nDone')
