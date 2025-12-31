import requests
from bs4 import BeautifulSoup as BS
import re
import urllib.parse

# Debug + robustness: set a User-Agent and print short response snippets when parsing fails
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; metrixbot/1.0)"}

area = "Etelä-Pohjanmaa"
encoded = urllib.parse.quote(area)
# search window: 2026-01-01 .. 2027-01-01
url = f"https://discgolfmetrix.com/competitions_server.php?name=&date1=2026-01-01&date2=2027-01-01&registration_date1=&registration_date2=&country_code=FI&type=d&from=1&to=200&page=all&area={encoded}"
resp = requests.get(url, headers=HEADERS, timeout=30)
resp.encoding = resp.apparent_encoding
html = resp.text
soup = BS(html, "html.parser")


def find_doubles(area_name=None, date1='2026-01-01', date2='2027-01-01'):
    """Return list of doubles (parikilpailu) entries for the configured area/date window."""
    results = []
    container = soup
    # gridlist items
    for a in container.select('a.gridlist'):
        href = a.get('href','')
        m = re.search(r"/(\d+)", href)
        comp_id = m.group(1) if m else None
        title = a.find('h2').get_text(strip=True) if a.find('h2') else a.get_text(strip=True)
        kind = None
        tspan = a.select_one('.competition-type')
        if tspan:
            kind = tspan.get_text(strip=True)
        meta = a.select_one('.metadata-list')
        date = None
        location = None
        if meta:
            lis = meta.find_all('li')
            if lis:
                date = lis[0].get_text(strip=True)
            if len(lis) > 1:
                location = lis[1].get_text(strip=True)
        results.append({'id':comp_id,'title':title,'kind':kind,'date':date,'location':location})

    # table rows
    for tr in container.select('table.table-list tbody tr'):
        a = tr.select_one('a')
        href = a.get('href','') if a else ''
        m = re.search(r"/(\d+)", href)
        comp_id = m.group(1) if m else None
        name = a.get_text(strip=True) if a else tr.get_text(strip=True)
        cols = [td.get_text(strip=True) for td in tr.find_all('td')]
        date = cols[1] if len(cols) > 1 else None
        kind = cols[2] if len(cols) > 2 else None
        location = cols[3] if len(cols) > 3 else None
        results.append({'id':comp_id,'title':name,'kind':kind,'date':date,'location':location})

    # Deduplicate by id
    seen = set()
    unique = []
    for r in results:
        if r.get('id') and r['id'] not in seen:
            seen.add(r['id'])
            unique.append(r)

    # Filter heuristically for pair/doubles keywords
    pair_re = re.compile(r"\b(pari|parikisa|parikilpailu|parigolf|pariviikko|pair|pairs|double|doubles|best shot|max2)\b", re.I)
    doubles = [r for r in unique if (r.get('title') and pair_re.search(r.get('title'))) or (r.get('kind') and pair_re.search(r.get('kind')))]

    return doubles


def save_doubles_list(entries, out_path=None):
    import json, os
    from . import data_store
    if not out_path:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        out_path = os.path.join(base_dir, 'DOUBLES.json')
    try:
        # Use centralized data_store to persist doubles list
        data_store.save_category('DOUBLES', entries, out_path)
    except Exception as e:
        print(f"Failed to save DOUBLES JSON: {e}")


if __name__ == '__main__':
    doubles = find_doubles()
    save_doubles_list(doubles)


