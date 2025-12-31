import os
import json
import requests
from bs4 import BeautifulSoup as BS

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PDGA_PATH = os.path.join(BASE_DIR, 'PDGA.json')
WEEKLY_PATH = os.path.join(BASE_DIR, 'VIIKKOKISA.json')
OUT_PATH = os.path.join(BASE_DIR, 'pending_registration.json')
USER_AGENT = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS_OPEN = [
    'registration open',
    'registrationis open',
    'ilmoittautuminen avoinna',
    'ilmoittautuminen auki',
    'registration closes',
    'register',
    'ilmoittaudu',
    'register now',
]

def text_contains_open(text: str) -> bool:
    t = text.lower()
    for k in KEYWORDS_OPEN:
        if k in t:
            return True
    return False


def check_competition(comp: dict) -> dict:
    url = comp.get('url') or comp.get('link') or ''
    result = {
        'id': comp.get('id'),
        'name': comp.get('name') or comp.get('title'),
        'url': url,
        'kind': comp.get('kind') or comp.get('tier') or '',
        'registration_open': False,
        'note': ''
    }
    if not url:
        result['note'] = 'no url'
        return result
    try:
        r = requests.get(url, headers=USER_AGENT, timeout=15)
        if r.status_code != 200:
            result['note'] = f'http {r.status_code}'
            return result
        r.encoding = r.apparent_encoding
        soup = BS(r.text, 'html.parser')
        # Check visible page text first
        page_text = soup.get_text(separator=' ', strip=True)
        if text_contains_open(page_text):
            result['registration_open'] = True
            result['note'] = 'keyword in page text'
            return result
        # Look for register links/buttons
        for a in soup.select('a'):
            href = (a.get('href') or '').lower()
            txt = (a.get_text() or '').lower()
            if 'register' in href or 'register' in txt or 'ilmoittaudu' in href or 'ilmoittaudu' in txt:
                result['registration_open'] = True
                result['note'] = 'register link/button'
                return result
        # look for input/button elements that imply registration
        for btn in soup.select('button'):
            txt = (btn.get_text() or '').lower()
            if 'register' in txt or 'ilmoittaudu' in txt or 'ilmoittautu' in txt:
                result['registration_open'] = True
                result['note'] = 'register button'
                return result
        # fallback: check meta tags
        meta = ' '.join([m.get('content','') for m in soup.select('meta') if m.get('content')])
        if text_contains_open(meta):
            result['registration_open'] = True
            result['note'] = 'keyword in meta'
            return result
        # not found
        result['note'] = 'no registration indicators'
        return result
    except Exception as e:
        result['note'] = 'error: ' + str(e)
        return result


if __name__ == '__main__':
    comps = []
    # load PDGA and weekly lists
    for path, label in ((PDGA_PATH, 'PDGA'), (WEEKLY_PATH, 'VIIKKOKISA')):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lst = json.load(f)
                for c in lst:
                    # ensure kind field for weekly entries
                    if label == 'VIIKKOKISA':
                        c.setdefault('kind', 'VIIKKOKISA')
                    comps.append(c)
        except FileNotFoundError:
            print(f'{label} file not found at {path}; skipping')
        except Exception as e:
            print(f'Failed to read {label} list:', e)

    results = []
    for c in comps:
        r = check_competition(c)
        results.append(r)
        print(f"{r.get('id')} | {r.get('name')} | {r.get('kind')} -> registration_open={r.get('registration_open')} ({r.get('note')})")

    # filter only open
    open_comps = [r for r in results if r.get('registration_open')]
    try:
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(open_comps, f, ensure_ascii=False, indent=2)
        print(f'Saved {len(open_comps)} open registrations to', OUT_PATH)
    except Exception as e:
        print('Failed to save pending_registration.json:', e)
