import json
import os

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(BASE, 'CAPACITY_SCAN_RESULTS.json')
OUT = os.path.join(BASE, 'CAPACITY_ALERTS.json')

THRESHOLD = 20

with open(SRC, 'r', encoding='utf-8') as f:
    data = json.load(f)

alerts = []
# normalize: if there is no explicit limit, clear remaining (no max players)
for item in data:
    cap = item.get('capacity_result', {})
    if cap.get('limit') is None:
        cap['remaining'] = None

for item in data:
    cap = item.get('capacity_result', {})
    rem = cap.get('remaining')
    if rem is None:
        continue
    # skip events without an explicit limit (no max players)
    if cap.get('limit') is None:
        continue
    if isinstance(rem, int) and rem <= THRESHOLD:
        alerts.append({
            'id': item.get('id'),
            'title': item.get('name'),
            'url': item.get('url'),
            'registered': cap.get('registered'),
            'limit': cap.get('limit'),
            'remaining': rem,
            'note': cap.get('note')
        })

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(alerts, f, ensure_ascii=False, indent=2)

print(f'Wrote {len(alerts)} alerts to {OUT}')