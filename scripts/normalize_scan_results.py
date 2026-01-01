import json
import os

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(BASE, 'CAPACITY_SCAN_RESULTS.json')

with open(SRC, 'r', encoding='utf-8') as f:
    data = json.load(f)

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
    with open(SRC, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

print(f'Normalized {changed} entries in {SRC}')