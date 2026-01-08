import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PENDING = os.path.join(ROOT, 'pending_registration.json')

try:
    from komento_koodit import data_store
except Exception:
    data_store = None

if data_store is not None:
    entries = data_store.load_category('pending_registration') or []
else:
    with open(PENDING, 'r', encoding='utf-8') as f:
        entries = json.load(f)

lines = []
for e in entries:
    kind = (e.get('kind') or '').strip()
    # consider PDGA entries not to be part of weekly !rek
    if 'PDGA' in kind.upper():
        continue

    title = e.get('title') or e.get('name') or ''
    url = e.get('url') or ''

    date_text = ''
    try:
        if e.get('opening_soon') and e.get('opens_in_days') is not None:
            date_text = f'avautuu {int(e.get("opens_in_days"))} pv'
        else:
            date_field = e.get('date') or e.get('start_date')
            if date_field:
                date_text = str(date_field)
            else:
                m = re.search(r'(\d{1,2}\.\d{1,2}\.\d{2,4})', title)
                if m:
                    date_text = m.group(1)
    except Exception:
        date_text = ''

    # hide the kind label when it's just 'VIIKKOKISA'
    if 'VIIKKOKISA' in kind.upper():
        kind_display = ''
    else:
        kind_display = f' ({kind})' if kind else ''
    date_display = f' — {date_text}' if date_text else ''

    if url:
        lines.append(f'• [{title}]({url}){kind_display}{date_display}')
    else:
        lines.append(f'• {title}{kind_display}{date_display}')

# chunk into embed-sized blocks
max_len = 1900
cur = []
cur_len = 0
blocks = []
for ln in lines:
    if cur_len + len(ln) + 1 > max_len and cur:
        blocks.append('\n'.join(cur))
        cur = []
        cur_len = 0
    cur.append(ln)
    cur_len += len(ln) + 1
if cur:
    blocks.append('\n'.join(cur))

for i, b in enumerate(blocks, 1):
    print('\n' + '='*40)
    print(f'Embed block {i}:')
    print(b)
print('\nTotal embed blocks:', len(blocks))
