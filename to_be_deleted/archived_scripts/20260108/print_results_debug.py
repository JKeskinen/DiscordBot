import requests
from bs4 import BeautifulSoup as BS
import re

URL = "https://discgolfmetrix.com/3523711&view=result"

headers = {"User-Agent": "Mozilla/5.0 (compatible; MetrixDiscordBot/1.0)"}
resp = requests.get(URL, headers=headers, timeout=30)
print(f"HTTP {resp.status_code} for {URL}")
if resp.status_code != 200:
    print('Failed to fetch page')
    raise SystemExit(1)

soup = BS(resp.text, 'html.parser')

# Guess event title
title = None
h1 = soup.find('h1')
if h1:
    title = h1.get_text(strip=True)
if not title:
    t = soup.find('title')
    title = t.get_text(strip=True) if t else URL
print('\nEVENT:', title)

# find all tables that look like score tables
tables = soup.find_all('table')
print(f'Found {len(tables)} tables')

def guess_class_name(table, idx):
    name = None
    try:
        thead = table.find('thead')
        if thead:
            ths = thead.find_all('th')
            for th in ths:
                txt = str(th.get_text(' ', strip=True))
                if txt and re.search(r"\([0-9]+\)", txt) and not txt.lower().startswith('sija'):
                    name = txt
                    break
    except Exception:
        name = None
    if not name:
        heading = table.find_previous(['h3','h4','h2'])
        if heading:
            name = heading.get_text(' ', strip=True)
    if not name:
        try:
            thead = table.find('thead')
            if thead:
                ths = thead.find_all('th')
                for th in ths:
                    txt = th.get_text(' ', strip=True)
                    if txt and len(txt.split()) >= 2 and not txt.lower().startswith('sija'):
                        name = txt
                        break
        except Exception:
            name = None
    if not name:
        name = f"Sarja {idx+1}"
    if len(name) > 80:
        name = name[:77] + '...'
    return name

# parse tables to classes
classes = []
for idx, table in enumerate(tables):
    rows_data = []
    rating_index = None
    for tr in table.find_all('tr'):
        ths = tr.find_all('th')
        if ths:
            if rating_index is None:
                for i, th in enumerate(ths):
                    txt = th.get_text(strip=True).lower()
                    if 'rating' in txt or 'rtg' in txt:
                        rating_index = i
                        break
            continue
        player_td = tr.find('td', class_='player-cell')
        if not player_td:
            continue
        tds = tr.find_all('td')
        if len(tds) < 3:
            continue
        pos_text = tds[0].get_text(strip=True)
        m_pos = re.match(r"(\d+)", pos_text)
        pos_html = int(m_pos.group(1)) if m_pos else None
        name_parts = list(player_td.stripped_strings)
        name = name_parts[0] if name_parts else player_td.get_text(strip=True)
        metrix_id = ''
        try:
            link = player_td.find('a', href=True)
            if link:
                href = str(link.get('href') or '')
                m_id = re.search(r"/player/(\d+)", href)
                if m_id:
                    metrix_id = m_id.group(1)
        except Exception:
            metrix_id = ''
        to_par = tds[2].get_text(strip=True)
        total = tds[-1].get_text(strip=True)
        rating = ''
        if rating_index is not None and rating_index < len(tds):
            rating = tds[rating_index].get_text(strip=True)
        rows_data.append({
            'position': pos_html,
            'name': name,
            'to_par': to_par,
            'total': total,
            'rating': rating,
            'metrix_id': metrix_id,
        })
    if rows_data:
        # recompute positions as in bot
        def score_key(r):
            total_txt = str(r.get('total') or '').strip()
            to_par_txt = str(r.get('to_par') or '').strip()
            def parse_int(s):
                m = re.match(r"-?\d+", s)
                return int(m.group(0)) if m else None
            total_val = parse_int(total_txt)
            to_par_val = parse_int(to_par_txt)
            primary = total_val if total_val is not None else 9999
            secondary = to_par_val if to_par_val is not None else 0
            return (primary, secondary)
        last_score = None
        current_place = 0
        for r in rows_data:
            sk = score_key(r)
            if last_score is None:
                current_place = 1
            elif sk != last_score:
                current_place += 1
            r['position'] = current_place
            last_score = sk
        cname = guess_class_name(table, idx)
        classes.append({'class_name': cname, 'rows': rows_data})

print(f'Parsed {len(classes)} classes')
for cls in classes:
    print('\n==', cls['class_name'], '==')
    # select top_rows: 1,2 and all 3s; exclude total==0
    top_rows = []
    count3 = 0
    for r in cls['rows']:
        try:
            total_num = int(str(r.get('total') or ''))
        except Exception:
            total_num = None
        pos = r.get('position')
        if not isinstance(pos, int) or total_num == 0:
            continue
        if pos in (1,2):
            top_rows.append(r)
        elif pos == 3:
            count3 += 1
    if count3 > 0:
        for r in cls['rows']:
            try:
                total_num = int(str(r.get('total') or ''))
            except Exception:
                total_num = None
            if r.get('position') == 3 and total_num != 0 and r not in top_rows:
                top_rows.append(r)
    if not top_rows:
        print(' (no top3 results)')
    else:
        for r in top_rows:
            print(f"{r.get('position')}. {r.get('name')} {r.get('to_par')} ({r.get('total')}, rtg {r.get('rating')})")

print('\nDone')
