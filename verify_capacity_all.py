#!/usr/bin/env python3
"""Verify all entries in CAPACITY_ALERTS.json by re-running capacity checks
and saving rendered HTML for any mismatches.
"""
import json
import os
import re
from komento_koodit.check_capacity import check_competition_capacity

OUT = 'CAPACITY_VERIFICATION.json'
ALERTS = 'CAPACITY_ALERTS.json'

os.makedirs('debug_verify', exist_ok=True)

alerts = json.load(open(ALERTS, encoding='utf-8'))
report = []

try:
    from playwright.sync_api import sync_playwright
except Exception as e:
    print('Playwright not available:', e)
    sync_playwright = None

if sync_playwright:
    p_context = sync_playwright()
    p = p_context.__enter__()
    browser = p.chromium.launch(headless=True)
else:
    p = None
    browser = None

for a in alerts:
    url = a.get('url')
    id = a.get('id') or a.get('title', 'unknown').replace(' ', '_')
    print('Checking', id, url)
    try:
        res = check_competition_capacity(url, timeout=30)
    except Exception as e:
        res = {'error': str(e)}

    mismatch = False
    notes = []

    if 'error' in res:
        mismatch = True
        notes.append('check_error')
    else:
        r = res.get('registered')
        l = res.get('limit')
        rem = res.get('remaining')
        if r is None or l is None:
            mismatch = True
            notes.append('missing_values')
        else:
            calc = l - r
            if rem is not None and rem != calc:
                notes.append('reported_remaining_mismatch')
                mismatch = True
            if a.get('remaining') != calc or a.get('registered') != r or a.get('limit') != l:
                notes.append('stored_mismatch')
                mismatch = True
            if calc < 0:
                notes.append('negative_remaining')
                mismatch = True

    html_saved = None
    extracted = {}

    if mismatch and browser:
        print('  MISMATCH — rendering page and saving HTML')
        page = browser.new_page()
        try:
            page.goto(url + '?view=registration', timeout=30000)
        except Exception:
            try:
                page.goto(url, timeout=30000)
            except Exception as e:
                print('  render failed:', e)
        html = page.content()
        fname = os.path.join('debug_verify', f"{id}.html")
        open(fname, 'w', encoding='utf-8').write(html)
        html_saved = fname
        m = re.search(r"(\d{1,4})\s*/\s*(\d{1,4})", html)
        if m:
            extracted['xy'] = (int(m.group(1)), int(m.group(2)))
        bnums = re.findall(r"<b[^>]*>\s*(\d{1,4})\s*</b>", html)
        if bnums:
            extracted['bnums'] = [int(x) for x in bnums]
        try:
            page.close()
        except Exception:
            pass

    report.append({
        'id': id,
        'url': url,
        'original': a,
        'res': res,
        'mismatch': mismatch,
        'notes': notes,
        'html_saved': html_saved,
        'extracted': extracted,
    })

if browser:
    try:
        browser.close()
    except Exception:
        pass
if p:
    try:
        p_context.__exit__(None, None, None)
    except Exception:
        pass

open(OUT, 'w', encoding='utf-8').write(json.dumps(report, ensure_ascii=False, indent=2))
print('Wrote', OUT)
