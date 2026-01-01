import os, json
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
path = os.path.join(base_dir, 'CAPACITY_ALERTS.json')
with open(path, 'r', encoding='utf-8') as f:
    res = json.load(f)
lines = []
for c in res[:200]:
    name = c.get('title') or c.get('name') or c.get('name_en') or c.get('event') or ''
    url = c.get('url') or ''
    reg = c.get('registered')
    lim = c.get('limit')
    rem = c.get('remaining')
    if reg is not None and lim is not None:
        try:
            calc_rem = int(lim) - int(reg)
        except Exception:
            calc_rem = rem
        if calc_rem is None:
            rem_txt = '?'
        elif calc_rem >= 0:
            rem_txt = f'{calc_rem} left'
        else:
            rem_txt = f'over by {abs(int(calc_rem))}'
        disp = f'{reg}/{lim} ({rem_txt})'
    elif reg is not None and lim is None:
        disp = f'{reg}/?'
    elif reg is None and lim is not None:
        disp = f'?/{lim} ({rem if rem is not None else "?"} left)'
    else:
        disp = f'järjellä {rem if rem is not None else "?"} paikkaa'
    if url:
        lines.append(f'• [{name}]({url}) — {disp}')
    else:
        lines.append(f'• {name} — {disp}')
print('Kilpailut, joissa vähän paikkoja:')
for ln in lines:
    print(ln)
