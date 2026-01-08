import json
import os
from komento_koodit import data_store

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(BASE, 'CAPACITY_SCAN_RESULTS.json')

# load from sqlite-backed store (fallback to file)
data = data_store.load_category(os.path.basename(SRC))

changed = 0
for item in data:
    cap = item.get('capacity_result')
    if not cap:
        continue
    if cap.get('limit') is None:
        if cap.get('remaining') is not None:
            cap['remaining'] = None
            changed += 1

if changed > 0:
    data_store.save_category(os.path.basename(SRC), data)

print(f'Normalized {changed} entries in {SRC}')