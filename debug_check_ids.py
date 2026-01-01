import os
import re
from bs4 import BeautifulSoup as BS
from hyvat_koodit.check_capacity import check_competition_capacity

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

OUT = 'debug_verify'
os.makedirs(OUT, exist_ok=True)
IDS = ['3519179','3512047','3500547']
for id in IDS:
    url = f'https://discgolfmetrix.com/{id}?view=registration'
    print('===', id, url)
    try:
        res = check_competition_capacity(url, timeout=15)
    except Exception as e:
        res = {'error': str(e)}
    print('check_competition_capacity ->', res)
    if sync_playwright is None:
        print('Playwright not available, skipping render')
        continue
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page()
            page.goto(url, timeout=20000)
            content = page.content()
            body = page.inner_text('body') if page.query_selector('body') else ''
            b.close()
        out = os.path.join(OUT, f'{id}.html')
        with open(out,'w',encoding='utf-8') as fh:
            fh.write(content)
        print('Saved rendered HTML to', out)
        soup = BS(content,'html.parser')
        found=False
        for tr in soup.find_all('tr'):
            bnums = []
            for b in tr.find_all('b'):
                t=(b.get_text(strip=True) or '').strip()
                if re.match(r'^\d{1,4}$', t):
                    bnums.append(int(t))
            if bnums:
                print('tr bnums:', bnums)
                found=True
                break
        if not found:
            # search for labelled patterns
            text = soup.get_text(' ', strip=True)
            m = re.search(r'(\d{1,3})\s*/\s*(\d{1,3})', text)
            if m:
                print('pattern X/Y found in text:', m.group(1), '/', m.group(2))
            else:
                print('No numeric <b> rows or X/Y pattern found; text snippet:', text[:300])
    except Exception as e:
        print('Render failed:', e)
print('Done')
