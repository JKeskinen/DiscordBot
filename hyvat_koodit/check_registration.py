import os
import json
import requests
import re
from bs4 import BeautifulSoup as BS
from datetime import datetime, timedelta

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

# Phrases indicating registration will open soon or on a specific date
KEYWORDS_OPEN_SOON = [
    'registration opens',
    'opens on',
    'opens',
    'ilmoittautuminen avautuu',
    'ilmoittautuminen aukeaa',
    'avautuu pian',
    'avautuu',
    'avautuu'
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
        'opening_soon': False,
        'opens_in_days': None,
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
        page_text = str(soup.get_text(separator=' ', strip=True))
        # direct open
        if text_contains_open(page_text):
            result['registration_open'] = True
            result['note'] = 'keyword in page text'
            return result

        # check for opening-soon phrases with dates (e.g. "registration opens 01/03/26")
        lowered = page_text.lower()
        for kw in KEYWORDS_OPEN_SOON:
            if kw in lowered:
                # attempt to find a date near the keyword
                # date patterns: DD/MM/YY or DD/MM/YYYY or YYYY-MM-DD
                m = None
                # search for date after keyword
                try:
                    idx = lowered.find(kw)
                    snippet = lowered[idx: idx+80]
                    m = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})", snippet)
                    if not m:
                        # try ISO-like date elsewhere on page
                        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", lowered)
                except Exception:
                    m = None
                if m:
                    # parse matched date
                    try:
                        if len(m.groups()) == 3:
                            g1, g2, g3 = m.groups()
                            if len(g1) == 4:  # YYYY-MM-DD
                                year = int(g1); month = int(g2); day = int(g3)
                            else:
                                day = int(g1); month = int(g2); year = int(g3)
                                if year < 100:
                                    year += 2000
                            dt = datetime(year, month, day)
                            delta = (dt.date() - datetime.utcnow().date()).days
                            result['opens_in_days'] = delta
                            if delta <= 0:
                                # already opened
                                result['registration_open'] = True
                                result['note'] = 'opened (date found)'
                                return result
                            if delta <= 7:
                                result['opening_soon'] = True
                                result['note'] = f'opens in {delta} days'
                                return result
                            # found a distant opening date -> note it but not 'soon'
                            result['note'] = f'opens on {dt.date()}'
                            return result
                    except Exception:
                        pass
                else:
                    # phrase present without date -> mark opening_soon True
                    if any(p in lowered for p in ['soon', 'pian', 'avautuu', 'avautuu pian']):
                        result['opening_soon'] = True
                        result['note'] = 'opening soon (phrase found)'
                        return result
        # Look for register links/buttons
        for a in soup.select('a'):
            href = str(a.get('href') or '').lower()
            txt = str(a.get_text() or '').lower()
            if 'register' in href or 'register' in txt or 'ilmoittaudu' in href or 'ilmoittaudu' in txt:
                result['registration_open'] = True
                result['note'] = 'register link/button'
                return result
        # look for input/button elements that imply registration
        for btn in soup.select('button'):
            txt = str(btn.get_text() or '').lower()
            if 'register' in txt or 'ilmoittaudu' in txt or 'ilmoittautu' in txt:
                result['registration_open'] = True
                result['note'] = 'register button'
                return result
        # fallback: check meta tags
        meta = ' '.join(str(m.get('content','')) for m in soup.select('meta') if m.get('content'))
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
            print(f'{label} -tiedostoa ei löytynyt kohdasta {path}; ohitetaan')
        except Exception as e:
            print(f'Virhe luettaessa {label}-listaa:', e)

    results = []
    for c in comps:
        r = check_competition(c)
        results.append(r)
        print(f"{r.get('id')} | {r.get('name')} | {r.get('kind')} -> ilmoittautuminen_avoinna={r.get('registration_open')} ({r.get('note')})")

    # filter only open
    open_comps = [r for r in results if r.get('registration_open')]
    try:
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(open_comps, f, ensure_ascii=False, indent=2)
        print(f'Tallennettu {len(open_comps)} avoinna olevaa rekisteröintiä tiedostoon', OUT_PATH)
    except Exception as e:
        print('Tallennus epäonnistui tiedostoon pending_registration.json:', e)
