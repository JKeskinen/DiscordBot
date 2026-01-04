import json
from komento_koodit import check_capacity as cc
url = 'https://discgolfmetrix.com/3500547'
print('sync_playwright available:', getattr(cc, 'sync_playwright', None) is not None)
print('Running check_competition_capacity with timeout=60...')
res = cc.check_competition_capacity(url, timeout=60)
print('Result:')
print(json.dumps(res, ensure_ascii=False, indent=2))
