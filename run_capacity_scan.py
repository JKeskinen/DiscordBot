import json
import time
import requests
from bs4 import BeautifulSoup as BS

from komento_koodit import check_capacity as cc


def main():
    from komento_koodit import data_store
    pending = data_store.load_category('pending_registration')

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
        # Attempt to extract per-class definitions and per-class counts (Metrix pages)
        try:
            # if check_capacity already returned class_info, preserve it
            if not res_record.get('capacity_result'):
                res_record['capacity_result'] = res
            if 'class_info' not in res_record.get('capacity_result', {}):
                class_info = None
                # first try static parse from the fetched soup (if available)
                try:
                    if 'soup' in locals() and getattr(cc, '_parse_metrix_classes_and_counts', None):
                        class_info = cc._parse_metrix_classes_and_counts(soup) or None
                except Exception:
                    class_info = None
                # fallback: attempt rendered DOM via Playwright if no useful class_info
                if (not class_info or not (class_info.get('classes') or class_info.get('class_counts'))) and getattr(cc, 'sync_playwright', None) is not None:
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
                            rc = cc._parse_metrix_classes_and_counts(rendered)
                            if rc:
                                class_info = rc
                        except Exception:
                            pass
                    except Exception:
                        pass
                if class_info:
                    # Only keep per-event class counts (not full definitions).
                    # The canonical class definitions are stored separately in
                    # `class_definitions.json` and consumers should reference it.
                    counts = None
                    try:
                        if isinstance(class_info, dict):
                            counts = class_info.get('class_counts')
                    except Exception:
                        counts = None
                    if counts:
                        try:
                            res_record['capacity_result']['class_counts'] = counts
                        except Exception:
                            res_record['capacity_result'] = dict(res_record.get('capacity_result') or {})
                            res_record['capacity_result']['class_counts'] = counts
                        # also expose at top-level for convenience
                        res_record['class_counts'] = counts
        except Exception:
            pass
        results.append(res_record)
        # be polite
        time.sleep(0.25)

    out_name = 'CAPACITY_SCAN_RESULTS.json'
    output = {
        'class_definitions': 'class_definitions.json',
        'results': results,
    }
    from komento_koodit import data_store
    data_store.save_category(out_name, output)
    try:
        print(f"Saved {len(results)} results to sqlite via data_store as {os.path.splitext(out_name)[0]}")
    except Exception:
        print("Saved results to sqlite via data_store")


if __name__ == '__main__':
    main()
