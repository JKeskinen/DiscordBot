import requests
from bs4 import BeautifulSoup as BS
import re
import urllib.parse
from .date_utils import normalize_date_string

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
        href = a.get('href', '') or ''
        href_str = str(href)
        m = re.search(r"/(\d+)", href_str)
        comp_id = m.group(1) if m else None
        h2 = a.find('h2')
        if h2 is not None:
            title = h2.get_text(strip=True)
        else:
            title = a.get_text(strip=True) or ''
        kind = None
        tspan = a.select_one('.competition-type')
        if tspan is not None:
            kind = tspan.get_text(strip=True)
        meta = a.select_one('.metadata-list')
        date = None
        location = None
        if meta is not None:
            lis = meta.find_all('li') or []
            if lis:
                raw_date = lis[0].get_text(strip=True) if getattr(lis[0], 'get_text', None) else None
                # Metrix often presents dates as MM/DD/YY — normalize preferring month-first
                try:
                    date = normalize_date_string(raw_date, prefer_month_first=True) if raw_date else raw_date
                except Exception:
                    date = raw_date
            if len(lis) > 1:
                location = lis[1].get_text(strip=True) if getattr(lis[1], 'get_text', None) else None
        # Rakenna absoluuttinen URL aina kun id on saatavilla
        url_full = ''
        if comp_id:
            try:
                url_full = urllib.parse.urljoin('https://discgolfmetrix.com', f'/{comp_id}')
            except Exception:
                url_full = f'https://discgolfmetrix.com/{comp_id}'
        elif href_str:
            # fallback jos tunnistettu id puuttuu
            try:
                url_full = urllib.parse.urljoin('https://discgolfmetrix.com', href_str)
            except Exception:
                url_full = href_str

        results.append({'id':comp_id,'title':title,'kind':kind,'date':date,'location':location,'url':url_full})

    # table rows
    for tr in container.select('table.table-list tbody tr'):
        a = tr.select_one('a')
        href = a.get('href','') if a else ''
        href_str = str(href)
        m = re.search(r"/(\d+)", href_str)
        comp_id = m.group(1) if m else None
        name = a.get_text(strip=True) if a is not None else tr.get_text(strip=True)
        cols = [td.get_text(strip=True) for td in tr.find_all('td')]
        date = cols[1] if len(cols) > 1 else None
        # Normalize date tokens found in table rows as well (assume Metrix month-first)
        try:
            date = normalize_date_string(date, prefer_month_first=True) if date else date
        except Exception:
            pass
        kind = cols[2] if len(cols) > 2 else None
        location = cols[3] if len(cols) > 3 else None

        # Rakenna absoluuttinen URL aina kun id on saatavilla
        url_full = ''
        if comp_id:
            try:
                url_full = urllib.parse.urljoin('https://discgolfmetrix.com', f'/{comp_id}')
            except Exception:
                url_full = f'https://discgolfmetrix.com/{comp_id}'
        elif href_str:
            try:
                url_full = urllib.parse.urljoin('https://discgolfmetrix.com', href_str)
            except Exception:
                url_full = href_str

        results.append({'id':comp_id,'title':name,'kind':kind,'date':date,'location':location,'url':url_full})

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


