import json
import time
import requests
from bs4 import BeautifulSoup as BS

from komento_koodit import check_capacity as cc


def main():
    with open('pending_registration.json', 'r', encoding='utf-8') as f:
        pending = json.load(f)

    results = []

    for idx, comp in enumerate(pending, 1):
        url = comp.get('url')
        print(f"[{idx}/{len(pending)}] Checking: {url}")
        try:
            res = cc.check_competition_capacity(url, timeout=10)
        except Exception as e:
            res = {'url': url, 'error': str(e)}
        res_record = {
            'id': comp.get('id'),
            'name': comp.get('name'),
            'url': url,
            'capacity_result': res,
        }
        # detect if Metrix page shows an empty main-header-meta (no visible limit)
        try:
            r = requests.get(url, headers=cc.USER_AGENT, timeout=8)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding
                soup = BS(r.text, 'html.parser')
                ul = soup.find('ul', class_='main-header-meta')
                if ul is not None:
                    # consider header empty unless it contains an explicit max-players label
                    try:
                        header_found, header_limit = cc._parse_metrix_main_header_meta(soup)
                        empty_meta = not bool(header_found)
                        # if not found in static HTML, try rendered DOM via Playwright (if available)
                        if empty_meta and getattr(cc, 'sync_playwright', None) is not None:
                            try:
                                with cc.sync_playwright() as p:
                                    browser = p.chromium.launch(headless=True)
                                    page = browser.new_page()
                                    page.goto(url, timeout=8000)
                                    content = page.content()
                                    browser.close()
                                try:
                                    from bs4 import BeautifulSoup as _BS
                                    rendered = _BS(content or '', 'html.parser')
                                    r_found, r_limit = cc._parse_metrix_main_header_meta(rendered)
                                    if r_found:
                                        empty_meta = False
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    except Exception:
                        empty_meta = not bool(ul.find('li'))
                    # attach flag into capacity_result
                    try:
                        res_record['capacity_result']['metrix_header_empty'] = bool(empty_meta)
                    except Exception:
                        res_record['capacity_result'] = dict(res_record.get('capacity_result') or {})
                        res_record['capacity_result']['metrix_header_empty'] = bool(empty_meta)
                    # If the main-header-meta is present but empty, treat this as
                    # "no visible limit" and clear any parsed numeric limit/remaining
                    # to avoid false positive limits coming from other DOM areas.
                    if empty_meta:
                        try:
                            res_record['capacity_result']['limit'] = None
                            res_record['capacity_result']['remaining'] = None
                            # annotate the note
                            note = res_record['capacity_result'].get('note') or ''
                            if 'no-visible-limit' not in note:
                                res_record['capacity_result']['note'] = (note + ' no-visible-limit').strip()
                        except Exception:
                            pass
        except Exception:
            pass
        results.append(res_record)
        # be polite
        time.sleep(0.25)

    out_name = 'CAPACITY_SCAN_RESULTS.json'
    with open(out_name, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(results)} results to {out_name}")


if __name__ == '__main__':
    main()
