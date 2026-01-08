#!/usr/bin/env python3
import os, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
# ignore data/ folder and __pycache__
ignore_dirs = {str(ROOT / 'data')}
import sys
sys.path.insert(0, str(ROOT))
try:
    from komento_koodit import data_store
except Exception as e:
    print('Failed to import komento_koodit.data_store:', e)
    raise

candidates = []
for p in ROOT.rglob('*.json'):
    # skip files under data/ and pycache
    if any(str(p).startswith(d) for d in ignore_dirs):
        continue
    # skip backup files with extra extensions
    if p.name.endswith('.bak'):
        continue
    candidates.append(p)

if not candidates:
    print('No JSON files found to import')
    sys.exit(0)

print(f'Found {len(candidates)} JSON files to import')
imported = []
for p in candidates:
    key = p.stem
    try:
        with p.open('r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print('Failed to load', p, e)
        continue
    try:
        data_store.save_category(key, data)
        imported.append(key)
        print('Imported', p.name, '-> key=', key)
    except Exception as e:
        print('Failed to save to db for', p, e)

print('\nImport complete. Verifying DB keys:')
# verify by reading back keys from json_store table
import sqlite3
from komento_koodit import data_store as _ds
db = os.path.join(str(ROOT), 'data', 'discordbot.db')
if not os.path.exists(db):
    print('Database not found at', db)
    sys.exit(1)
conn = sqlite3.connect(db)
try:
    cur = conn.execute("SELECT name, length(content) FROM json_store ORDER BY name")
    rows = cur.fetchall()
    if not rows:
        print('No entries in json_store')
    else:
        for name, ln in rows:
            print(f" - {name}: content_length={ln}")
finally:
    conn.close()

# Show any remaining top-level JSON files
remaining = [str(p.relative_to(ROOT)) for p in ROOT.glob('*.json') if p.name != 'requirements.txt']
if remaining:
    print('\nRemaining top-level JSON files:')
    for r in remaining:
        print(' -', r)
else:
    print('\nNo top-level JSON files remain (in repo root).')
