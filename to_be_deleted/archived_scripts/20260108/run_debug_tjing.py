#!/usr/bin/env python3
import sys
import json
import time
from pathlib import Path
import requests
from bs4 import BeautifulSoup as BS
from komento_koodit import check_capacity

URL = sys.argv[1] if len(sys.argv) > 1 else 'https://discgolfmetrix.com/3512047'
OUT_DIR = Path('.') / 'debug_tjing'
OUT_DIR.mkdir(exist_ok=True)
print('Checking URL:', URL)

# fetch metrix page
r = requests.get(URL, headers=check_capacity.USER_AGENT, timeout=15)
print('Metrix HTTP', r.status_code, 'url', getattr(r, 'url', ''))
metrix_path = OUT_DIR / 'metrix.html'
metrix_path.write_text(r.text, encoding='utf-8')
print('Saved metrix snapshot to', metrix_path)

soup = BS(r.text, 'html.parser')
page_text = soup.get_text(separator=' ', strip=True)
# find tjing link
tjing_link = check_capacity._find_tjing_link(soup, page_text, base_url=URL)
print('Detected TJing link:', tjing_link)

# fetch tjing static
if tjing_link:
    try:
        tr = requests.get(tjing_link, headers=check_capacity.USER_AGENT, timeout=15)
        print('TJing static HTTP', tr.status_code)
        tjing_static = OUT_DIR / 'tjing_static.html'
        tjing_static.write_text(tr.text, encoding='utf-8')
        print('Saved tjing static to', tjing_static)
    except Exception as e:
        print('TJing static fetch failed:', e)
else:
    print('No TJing link found; skipping TJing fetch.')

# run existing fetch_tjing_capacity (which uses heuristics and Playwright fallback)
print('\nRunning fetch_tjing_capacity() to get parsed result...')
res = check_capacity.fetch_tjing_capacity(tjing_link or URL, timeout=20)
print('Result:', json.dumps(res, ensure_ascii=False, indent=2))

# If Playwright available, also render and save DOM and inspect <b><span> labels
if check_capacity.sync_playwright is not None and tjing_link:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(tjing_link, timeout=20000)
            time.sleep(0.5)
            content = page.content()
            rendered = OUT_DIR / 'tjing_rendered.html'
            rendered.write_text(content, encoding='utf-8')
            print('Saved rendered HTML to', rendered)
            # inspect labelled <b><span>
            try:
                b_texts = page.eval_on_selector_all('b', 'els => els.map(e => e.innerText)')
                print('\n<b> tag inner texts (rendered):')
                for t in b_texts[:30]:
                    print(' -', repr(t))
            except Exception as e:
                print('Could not evaluate <b> tags:', e)
            # try to fetch window initial state
            try:
                state = page.evaluate('() => (window.__INITIAL_STATE__ || window.__INITIAL_DATA__ || window.__INITIAL || null)')
                print('\nDetected initial JS state type:', type(state))
                sfile = OUT_DIR / 'tjing_state.json'
                try:
                    sfile.write_text(json.dumps(state or {}, ensure_ascii=False, indent=2), encoding='utf-8')
                    print('Saved JS state to', sfile)
                except Exception:
                    pass
            except Exception as e:
                print('No initial JS state found or evaluate failed:', e)
            browser.close()
    except Exception as e:
        print('Playwright render failed:', e)

print('\nDone. Inspect files under', OUT_DIR)
