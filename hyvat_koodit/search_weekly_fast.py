import requests
from bs4 import BeautifulSoup as BS
import re
import urllib.parse
import os
from . import data_store
import time
import json

# Config: area and date window. Read from env if provided.
AREA = os.environ.get('WEEKLY_LOCATION', 'Etelä-Pohjanmaa')
DATE1 = os.environ.get('WEEKLY_DATE1', '2026-01-01')
DATE2 = os.environ.get('WEEKLY_DATE2', '2027-01-01')
COUNTRY = os.environ.get('WEEKLY_COUNTRY', 'FI')
TYPE = os.environ.get('WEEKLY_TYPE', '')  # '' = all, 'd' = doubles, 'c' = all competitions, etc.

area_enc = urllib.parse.quote(AREA)
# Use server endpoint with large page size for speed
type_part = f"&type={TYPE}" if TYPE else ""
url = f"https://discgolfmetrix.com/competitions_server.php?name=&date1={DATE1}&date2={DATE2}&registration_date1=&registration_date2=&country_code={COUNTRY}{type_part}&from=1&to=200&page=all&area={area_enc}"

print('URL:', url)
start = time.perf_counter()
resp = requests.get(url, timeout=20, headers={'User-Agent':'Mozilla/5.0'})
elapsed = time.perf_counter() - start
print(f"HTTP fetch time: {elapsed:.2f}s, status: {resp.status_code}")
resp.encoding = resp.apparent_encoding
soup = BS(resp.text, 'html.parser')
container = soup.find(id='competition_list2')

results = []

weekly_re = re.compile(r"\b(weekly|week|viikko|viikotta|viikkokisa|viikkokisat|weeklies)\b", re.I)
pair_re = re.compile(r"\b(pari|parikisa|parikilpailu|parigolf|pariviikko|pariviikkokisat|pair|pairs|double|doubles|best shot|max2)\b", re.I)

if container:
    # gridlist entries
    for a in container.select('a.gridlist'):
        href = a.get('href','')
        comp_id = None
        m = re.search(r"/(\d+)", href)
        if m:
            comp_id = m.group(1)
        title = a.find('h2').get_text(strip=True) if a.find('h2') else a.get_text(strip=True)
        tspan = a.select_one('.competition-type')
        tier = tspan.get_text(strip=True) if tspan else ''
        meta = a.select('.metadata-list li')
        date = meta[0].get_text(strip=True) if len(meta) > 0 else ''
        location = meta[1].get_text(strip=True) if len(meta) > 1 else ''
        kind = None
        title_l = (title or '').lower()
        loc_l = (location or '').lower()
        tier_l = (tier or '').lower()
        # substring fallback for robustness
        pair_keywords = ['pari','parikisa','parikilpailu','parigolf','pariviikko','pariviikkokisat','pair','pairs','double','doubles','best shot','max2']
        weekly_keywords = ['weekly','week','viikko','viikkari','viikotta','viikkokisa','viikkokisat','viikkot','weeklies']
        is_pair = bool(pair_re.search(title_l) or pair_re.search(loc_l) or pair_re.search(tier_l) or any(k in title_l or k in loc_l or k in tier_l for k in pair_keywords))
        is_weekly = bool(weekly_re.search(title_l) or weekly_re.search(loc_l) or weekly_re.search(tier_l) or any(k in title_l or k in loc_l or k in tier_l for k in weekly_keywords))
        # avoid tagging PDGA-liiga as weekly
        is_liiga = 'liiga' in title_l or 'liiga' in tier_l
        if is_pair:
            kind = 'PARIKISA'
        elif is_weekly and not is_liiga:
            kind = 'VIIKKOKISA'
        # build absolute URL when href is present
        url = ''
        if href:
            try:
                url = urllib.parse.urljoin('https://discgolfmetrix.com', href)
            except Exception:
                url = href
        results.append({'id': comp_id, 'title': title, 'tier': tier, 'date': date, 'location': location, 'kind': kind, 'url': url})
    # table rows fallback
    for tr in container.select('table.table-list tbody tr'):
        cols = tr.find_all('td')
        if not cols:
            continue
        link = cols[0].find('a')
        href = link['href'] if link else ''
        comp_id = None
        m = re.search(r"/(\d+)", href)
        if m:
            comp_id = m.group(1)
        name = link.get_text(strip=True) if link else cols[0].get_text(strip=True)
        date = cols[1].get_text(strip=True) if len(cols) > 1 else ''
        tier = cols[2].get_text(strip=True) if len(cols) > 2 else ''
        location = cols[3].get_text(strip=True) if len(cols) > 3 else ''
        kind = None
        if pair_re.search(name) or pair_re.search(location) or pair_re.search(tier):
            kind = 'PARIKISA'
        elif weekly_re.search(name) or weekly_re.search(location) or weekly_re.search(tier):
            kind = 'VIIKKOKISA'
        # build absolute URL when href is present
        url = ''
        if href:
            try:
                url = urllib.parse.urljoin('https://discgolfmetrix.com', href)
            except Exception:
                url = href
        results.append({'id': comp_id, 'title': name, 'tier': tier, 'date': date, 'location': location, 'kind': kind, 'url': url})

# dedupe
seen = set()
unique = []
for r in results:
    cid = r.get('id') or r.get('title')
    if cid in seen:
        continue
    seen.add(cid)
    unique.append(r)
# If area filter is used, default entries without an explicit kind to VIIKKOKISA
if AREA and unique:
    for r in unique:
        if not r.get('kind'):
            # Default any unclassified area result to weekly
            r['kind'] = 'VIIKKOKISA'

print(f"Parsed {len(unique)} entries (gridlist/table) in {AREA}")
# show counts by kind
from collections import Counter
kcounts = Counter([r.get('kind') or 'OTHER' for r in unique])
print('Counts by kind:', dict(kcounts))

# Report how many were defaulted to VIIKKOKISA and save them
wk_count = sum(1 for r in unique if r.get('kind') == 'VIIKKOKISA')
print(f"VIIKKOKISA after defaulting: {wk_count}")
try:
    # Persist using centralized data_store (keeps filename VIIKKOKISA.json by default)
    entries = [r for r in unique if r.get('kind') == 'VIIKKOKISA']
    data_store.save_category('VIIKKOKISA', entries)
except Exception as e:
    print(f"Failed to save VIIKKOKISA.json: {e}")

for r in unique:
    print(f"- {r.get('id')} | {r.get('title')} | {r.get('kind')} | {r.get('location')} | {r.get('date')}")

print('\nDone.')
