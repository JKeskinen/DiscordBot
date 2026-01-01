from playwright.sync_api import sync_playwright
from pathlib import Path
import json

URL = 'https://discgolfmetrix.com/3519179?view=registration'
OUT = Path('debug_tjing')
OUT.mkdir(exist_ok=True)
result = {'url': URL, 'registered': None, 'max': None, 'waiting': None, 'notes': []}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, timeout=30000)
    # wait for potential table to appear
    try:
        page.wait_for_selector('table', timeout=5000)
    except Exception:
        pass
    # save rendered HTML
    rendered = page.content()
    (OUT/'registration_rendered.html').write_text(rendered, encoding='utf-8')

    # try the user's CSS selector
    sel = '#content_auto > div > div > div:nth-child(1) > div > table > tbody > tr:nth-child(4) > td:nth-child(3) > b'
    try:
        el = page.query_selector(sel)
        if el:
            txt = el.inner_text().strip()
            try:
                result['max'] = int(''.join(c for c in txt if c.isdigit()))
                result['notes'].append('selector-found')
            except Exception:
                result['notes'].append('selector-non-numeric')
        else:
            result['notes'].append('selector-not-found')
    except Exception as e:
        result['notes'].append(f'selector-error:{e}')

    # find registration summary row by text
    try:
        rows = page.query_selector_all('tr')
        for r in rows:
            txt = r.inner_text().lower()
            if 'rekister' in txt and 'pelaaj' in txt:
                # extract bold numbers from that row
                bs = r.query_selector_all('b')
                nums = []
                for b in bs:
                    try:
                        t = b.inner_text().strip()
                        n = int(''.join(c for c in t if c.isdigit()))
                        nums.append(n)
                    except Exception:
                        continue
                if nums:
                    # typical: [per-class..., total_registered, max, waiting]
                    if len(nums) >= 2:
                        # choose last two as total and max when available
                        if len(nums) >= 3:
                            result['registered'] = nums[-3]
                            result['max'] = nums[-2]
                            result['waiting'] = nums[-1] if len(nums) > 3 else 0
                        else:
                            result['registered'] = nums[0]
                            result['max'] = nums[1] if len(nums) > 1 else None
                    else:
                        result['registered'] = nums[0]
                result['notes'].append('table-row-found')
                break
        else:
            result['notes'].append('table-row-not-found')
    except Exception as e:
        result['notes'].append(f'row-parse-error:{e}')

    browser.close()

print(json.dumps(result, ensure_ascii=False, indent=2))
(OUT/'registration_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print('Rendered snapshot and result written to', OUT)
