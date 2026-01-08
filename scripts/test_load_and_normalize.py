import os, json
from komento_koodit.date_utils import normalize_date_string
from komento_koodit import data_store
root = os.path.abspath('.')
fname = 'known_weekly_competitions.json'
data = data_store.load_category(fname)
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
