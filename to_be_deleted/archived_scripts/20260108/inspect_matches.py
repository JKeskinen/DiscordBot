import os, json, re
from komento_koodit.date_utils import normalize_date_string
from komento_koodit import data_store

ROOT = os.path.abspath('.')
candidate_files = [
    "PDGA.json",
    "VIIKKOKISA.json",
    "known_weekly_competitions.json",
    "known_pdga_competitions.json",
    "known_doubles_competitions.json",
    "DOUBLES.json",
]
entries = []
for fname in candidate_files:
    data = data_store.load_category(fname)
    if not data:
        continue
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                item['_src_file'] = fname
            entries.append(item)
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        item['_src_file'] = fname
                    entries.append(item)
            else:
                if isinstance(v, dict):
                    v['_src_file'] = fname
                entries.append(v)

# match 'kauhajoki'
fields = ["title","name","location","venue","track","area","place","city","region","kind"]
q='kauhajoki'
matches=[]
for e in entries:
    try:
        hay = ' '.join(str(e.get(f,'') or '') for f in fields).lower()
        if q in hay:
            matches.append(e)
    except Exception:
        continue

print('Total matches:', len(matches))
for e in matches:
    print('---')
    print('title:', e.get('title'))
    print('_src_file:', e.get('_src_file'))
    df = e.get('date') or e.get('start_date') or ''
    print('raw date:', df)
    print('norm prefer F:', normalize_date_string(str(df), prefer_month_first=False))
    print('norm prefer T:', normalize_date_string(str(df), prefer_month_first=True))
