from playwright.sync_api import sync_playwright
from pathlib import Path
import sys

URL = 'https://discgolfmetrix.com/3512588?view=registration'
OUT = Path('debug_verify')
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, timeout=30000)
    try:
        page.wait_for_selector('table', timeout=5000)
    except Exception:
        pass
    rendered = page.content()
    outpath = OUT / '3512588.html'
    outpath.write_text(rendered, encoding='utf-8')
    print('Wrote', outpath)
    browser.close()
