import os, json
from komento_koodit.date_utils import normalize_date_string
root = os.path.abspath('.')
fname = 'known_weekly_competitions.json'
with open(os.path.join(root, fname), 'r', encoding='utf-8') as f:
    data = json.load(f)
entries = []
for item in data:
    if isinstance(item, dict):
        item['_src_file'] = fname
    entries.append(item)

for e in entries:
    if e.get('id')=='3523248':
        df = e.get('date')
        print('raw date:', df)
        print('norm prefer False:', normalize_date_string(str(df), prefer_month_first=False))
        print('norm prefer True :', normalize_date_string(str(df), prefer_month_first=True))
        print('src:', e.get('_src_file'))
        break
