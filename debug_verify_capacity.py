import os
import re
import json
from bs4 import BeautifulSoup as BS
from hyvat_koodit.check_capacity import check_competition_capacity

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

OUT_DIR = 'debug_verify'
os.makedirs(OUT_DIR, exist_ok=True)

with open('CAPACITY_ALERTS.json', 'r', encoding='utf-8') as f:
    alerts = json.load(f)

for a in alerts:
    id = a.get('id') or a.get('title')
    url = a.get('url')
    print('---')
    print(f'ID: {id} | URL: {url}')
    print('orig -> registered:', a.get('registered'), 'limit:', a.get('limit'), 'remaining:', a.get('remaining'), 'note:', a.get('note'))
    try:
        res = check_competition_capacity(url, timeout=15)
    except Exception as e:
        res = {'error': str(e)}
    print('check_competition_capacity ->', res)

    # Render page and save HTML + extract <tr> <b> numbers
    if sync_playwright is None:
        print('Playwright not available in this environment; skipping render.')
        continue
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=15000)
            content = page.content()
            body_text = page.inner_text('body') if page.query_selector('body') else ''
            browser.close()
        outpath = os.path.join(OUT_DIR, f'verify_{id}.html')
        with open(outpath, 'w', encoding='utf-8') as fh:
            fh.write(content)
        print('Rendered HTML saved to', outpath)
        soup = BS(content, 'html.parser')
        found = False
        for tr in soup.find_all('tr'):
            bnums = []
            for b in tr.find_all('b'):
                txt = (b.get_text(strip=True) or '').strip()
                if re.match(r'^\d{1,4}$', txt):
                    try:
                        bnums.append(int(txt))
                    except Exception:
                        pass
            if bnums:
                print('tr bnums:', bnums)
                found = True
                break
        if not found:
            # labelled b patterns
            for b in soup.find_all('b'):
                parts = [s.strip() for s in b.stripped_strings]
                if parts and re.match(r'^\d{1,4}$', parts[0]):
                    print('labelled b:', parts)
                    found = True
                    break
        if not found:
            # fallback: print snippet of body_text
            print('No <b> numbers found in rows; body text snippet:')
            print(body_text[:400].replace('\n',' '))
    except Exception as e:
        print('Render/extract failed:', e)

print('\nDiagnostic run complete.')
