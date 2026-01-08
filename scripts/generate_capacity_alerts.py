import json
import os
from komento_koodit import data_store

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(BASE, 'CAPACITY_SCAN_RESULTS.json')
OUT = os.path.join(BASE, 'CAPACITY_ALERTS.json')

THRESHOLD = 20

data = data_store.load_category(os.path.basename(SRC))

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

data_store.save_category(os.path.basename(OUT), alerts)
try:
    print(f'Wrote {len(alerts)} alerts to sqlite as {os.path.splitext(os.path.basename(OUT))[0]}')
except Exception:
    print(f'Wrote {len(alerts)} alerts to sqlite')