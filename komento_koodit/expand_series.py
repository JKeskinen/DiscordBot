"""Helpers to expand Metrix series/league pages into child event items.

Function: expand_series(url, timeout=10)
- Fetches the given Metrix series page and returns a list of child events
  found on the page. Each item is a dict: {id, url, name, date_str} where
  date_str may be empty if not found.

Heuristics:
- Collect anchors that point to /<digits> event pages on discgolfmetrix.com
- Use surrounding text (parent <li> or sibling text) to extract date/time
- De-duplicate links and preserve order found
"""
from typing import List, Dict
import requests
from bs4 import BeautifulSoup as BS
import re
from urllib.parse import urljoin, urlparse

USER_AGENT = {'User-Agent': 'Mozilla/5.0 (metrixbot-expand-series)'}


def _abs_metrix_url(href: str, base: str) -> str:
    if not href:
        return ''
    if href.startswith('http'):
        return href
    return urljoin(base, href)


def _extract_id_from_url(u: str) -> str:
    try:
        p = urlparse(u)
        seg = p.path.rstrip('/').split('/')[-1]
        if re.match(r'^\d+$', seg):
            return seg
    except Exception:
        pass
    return ''


def _extract_date_from_context(elem_text: str) -> str:
    # naive date patterns: dd.mm.yyyy or d.m.yyyy or yyyy-mm-dd or common english
    m = re.search(r'([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)', elem_text)
    if m:
        return m.group(1)
    m2 = re.search(r'(\d{4}-\d{2}-\d{2})', elem_text)
    if m2:
        return m2.group(1)
    return ''


def expand_series(url: str, timeout: int = 10) -> List[Dict]:
    """Return list of child events found on a Metrix series page.

    Each returned dict contains: id, url, name (anchor text), date_str (nearby text).
    """
    out = []
    seen_ids = set()
    try:
        r = requests.get(url, headers=USER_AGENT, timeout=timeout)
        if r.status_code != 200:
            return out
        soup = BS(r.text, 'html.parser')

        # Find candidate anchors pointing to numeric Metrix pages
        anchors = []
        for a in soup.find_all('a', href=True):
            href = a.get('href') or ''
            absu = _abs_metrix_url(href, url)
            if 'discgolfmetrix.com' not in absu:
                continue
            eid = _extract_id_from_url(absu)
            if not eid:
                continue
            # ignore the parent page itself
            parent_id = _extract_id_from_url(url)
            if eid == parent_id:
                continue
            anchors.append((a, absu, eid))

        # preserve order, dedupe by id
        for a, absu, eid in anchors:
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            name = (a.get_text(' ', strip=True) or '').strip()
            # try to find date in the anchor's parent (li or div) or nearby text
            date_str = ''
            try:
                parent = a.parent
                if parent is not None:
                    ptxt = parent.get_text(' ', strip=True)
                    date_str = _extract_date_from_context(ptxt)
                if not date_str:
                    # sibling text
                    sib = a.find_next_sibling(text=True)
                    if sib:
                        date_str = _extract_date_from_context(str(sib))
                if not date_str:
                    # fallback: search within the grandparent
                    gp = parent.parent if parent is not None else None
                    if gp is not None:
                        date_str = _extract_date_from_context(gp.get_text(' ', strip=True))
            except Exception:
                date_str = ''

            out.append({'id': eid, 'url': absu, 'name': name, 'date_str': date_str})
    except Exception:
        return out
    return out


if __name__ == '__main__':
    import json
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else 'https://discgolfmetrix.com/3426381'
    print('Expanding', test_url)
    items = expand_series(test_url)
    print(json.dumps(items, ensure_ascii=False, indent=2))
