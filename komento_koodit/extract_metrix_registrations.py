import sys
import requests
from bs4 import BeautifulSoup
import json
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

DEFAULT_URL = 'https://discgolfmetrix.com/3500547'


def find_best_table(soup):
    tables = soup.find_all('table')
    best = None
    best_count = 0
    for t in tables:
        rows = [r for r in t.select('tbody tr') if r.find('td')]
        if len(rows) > best_count:
            best = t
            best_count = len(rows)
    return best


def parse_table(table):
    rows = [r for r in table.select('tbody tr') if r.find('td')]
    out = []
    for tr in rows:
        tds = tr.find_all('td')
        if not tds:
            continue
        # first td: may contain <span class="league">CODE</span> and the class name
        first = tds[0]
        league_span = first.find('span', class_='league')
        code = league_span.get_text(strip=True) if league_span else None
        # name: text of first td with span removed
        if league_span:
            # remove the span from a copy
            span_text = league_span.get_text()
            name = first.get_text(' ', strip=True).replace(span_text, '').strip()
        else:
            name = first.get_text(' ', strip=True)

        # second td: eligibility or rules
        eligibility = tds[1].get_text(' ', strip=True) if len(tds) > 1 else ''

        out.append({'code': code, 'name': name, 'eligibility': eligibility})
    return out


def main(url=DEFAULT_URL, outpath=None):
    print('Fetching', url)
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    table = find_best_table(soup)
    if not table:
        print('No table with data rows found in static HTML')
        if sync_playwright is None:
            print('Playwright not available; cannot render JS fallback')
            return 1
        print('Rendering page with Playwright (fallback)')
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                # wait a bit for dynamic content
                page.wait_for_timeout(1000)
                html = page.content()
                browser.close()
                soup = BeautifulSoup(html, 'html.parser')
                table = find_best_table(soup)
        except Exception as e:
            print('Playwright render failed:', e)
            return 1
    if not table:
        print('No table with data rows found even after rendering')
        return 1
    items = parse_table(table)
    print(f'Found {len(items)} registration rows')
    for it in items:
        print(f"{it['code'] or '-':4}  {it['name']}  -- {it['eligibility']}")
    if outpath:
        with open(outpath, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print('Saved to', outpath)
    return 0


if __name__ == '__main__':
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    out = sys.argv[2] if len(sys.argv) > 2 else None
    raise SystemExit(main(url, out))
