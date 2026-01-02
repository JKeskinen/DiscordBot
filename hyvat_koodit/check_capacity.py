import os
import re
import json
import time
import logging
import requests
from bs4 import BeautifulSoup as BS
from datetime import datetime
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

USER_AGENT = {'User-Agent': 'Mozilla/5.0 (metrixbot-capacity)'}

logger = logging.getLogger(__name__)


def _sanitize_capacity(res: dict) -> dict:
    """If a parsed capacity result has an impossible negative remaining value,
    mark the result as invalid and clear numeric fields so callers can
    attempt alternate strategies.
    """
    try:
        if not isinstance(res, dict):
            return res
        rem = res.get('remaining')
        if isinstance(rem, int) and rem < 0:
            # Interpret negative remaining as: registered > limit -> queued/waitlist.
            # Preserve registered/limit, set remaining to 0 and expose queued count.
            try:
                queued = int(-rem)
            except Exception:
                queued = None
            logger.info('Parsed negative remaining (%s) from source %s; marking as waitlist (queued=%s)', rem, res.get('note'), queued)
            out = {
                'registered': res.get('registered'),
                'limit': res.get('limit'),
                'remaining': 0,
                'note': (res.get('note') or '') + '-waitlist'
            }
            if queued is not None:
                out['queued'] = queued
            return out
    except Exception:
        pass
    return res


def _parse_metrix_main_header_meta(soup: BS):
    """Parse Metrix main-header-meta container for explicit max-players label/value.
    Prefer '#content_auto > ul.main-header-meta', fallback to '#content > div.row.align-center > div > ul',
    then generic 'ul.main-header-meta'. Returns (found: bool, limit: int|None).
    """
    try:
        ul = None
        try:
            ul = soup.select_one('#content_auto > ul.main-header-meta')
        except Exception:
            ul = None
        if not ul:
            try:
                ul = soup.select_one('#content > div.row.align-center > div > ul')
            except Exception:
                ul = None
        if not ul:
            ul = soup.find('ul', class_='main-header-meta')
        if not ul:
            return (False, None)

        phrases = [
            r'Pelaajien maksimäärä', r'Pelaajien maksimämäärä', r'Maksimi', r'Maksimi osallistujamäärä',
            r'Maximum number of players', r'Max players', r'max antal spelare', r'maxspelare'
        ]
        for li in ul.find_all('li'):
            txt = (li.get_text(' ', strip=True) or '')
            if not txt:
                continue
            # Prefer the numeric token that follows an explicit max-players phrase
            for p in phrases:
                m = re.search(p, txt, re.I)
                if m:
                    # search for number after the phrase
                    try:
                        after = txt[m.end():]
                        mnum = re.search(r'(\d{1,4})', after)
                        if mnum:
                            return (True, int(mnum.group(1)))
                        # try fallback: find any number in the li if none after phrase
                        many = re.search(r'(\d{1,4})', txt)
                        if many:
                            return (True, int(many.group(1)))
                        return (True, None)
                    except Exception:
                        return (True, None)
            # fallback: if li explicitly mentions players and contains a number,
            # prefer the last numeric token (often the max)
            if re.search(r'pelaaj|player|spelare|participants', txt, re.I) and re.search(r'\d{1,4}', txt):
                nums = re.findall(r'(\d{1,4})', txt)
                try:
                    return (True, int(nums[-1]))
                except Exception:
                    return (True, None)
        return (False, None)
    except Exception:
        return (False, None)

def _find_tjing_link(soup: BS, page_text: str, base_url: str = '') -> str:
    # Look for anchor hrefs that point to tjing
    try:
        for a in soup.find_all('a', href=True):
            href = str(a.get('href') or '')
            if 'tjing.' in href:
                # make absolute if needed
                if href.startswith('http'):
                    return href
                if href.startswith('/') and base_url:
                    return base_url.rstrip('/') + href
                return 'https://' + href.lstrip('/')
    except Exception:
        pass
    # also try to find a raw URL in text
    m = re.search(r'https?://[\w./-]*tjing\.[\w/\-?=&%]+', str(page_text))
    if m:
        return m.group(0)
    # look for non-protocol tjing mentions (e.g. "tjing.fi/event/..." or plain tjing root)
    m2 = re.search(r'(?:https?://)?(?:www\.)?tjing\.(?:fi|se|no|com)[^\s"\'"<>]*', str(page_text), re.I)
    if m2:
        raw = m2.group(0)
        if raw.startswith('http'):
            return raw
        if raw.startswith('www.'):
            return 'https://' + raw
        return 'https://' + raw.lstrip('/')
    # also inspect onclick/data-* attributes that may contain tjing url
    try:
        for a in soup.find_all(True):
            for attr in ('onclick', 'data-href', 'data-url', 'data-registration', 'data-target'):
                val = str(a.get(attr) or '')
                if val and 'tjing.' in val:
                    m3 = re.search(r'https?://[\w./-]*tjing\.[\w/\-?=&%]+', val)
                    if m3:
                        return m3.group(0)
                    # fallback: return raw value as possible path
                    if 'tjing.' in val:
                        return ('https://' + val.lstrip('/')) if not val.startswith('http') else val
    except Exception:
        pass
    return ''


def _discover_tjing_event_from_metrix(metrix_url: str, soup: BS, page_text: str, timeout: int = 8) -> str:
    """Try to find a TJing event URL on a Metrix page.
    Check anchors and page text first, then render the page with Playwright if needed.
    Returns full TJing URL or empty string.
    """
    # look for explicit event paths in anchors
    try:
        for a in soup.find_all('a', href=True):
            href = str(a.get('href') or '')
            if 'tjing.' in href and ('/event/' in href or '/e/' in href or '/events/' in href):
                if href.startswith('http'):
                    return href
                if href.startswith('/'):
                    # make absolute
                    base = metrix_url.split('?')[0].rstrip('/')
                    return base + href
                return 'https://' + href.lstrip('/')
    except Exception:
        pass

    # search raw page text for event path
    m = re.search(r'https?://[\w./-]*tjing\.[\w/\-?=&%]*?(?:/event/|/e/)[\w\-\d]+', str(page_text))
    if m:
        return m.group(0)

    # if still not found, try rendering and check anchors in rendered DOM
    if sync_playwright is None:
        return ''
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(metrix_url, timeout=timeout * 1000)
            anchors = page.query_selector_all('a')
            for a in anchors:
                try:
                    href = str(a.get_attribute('href') or '')
                    if href and 'tjing.' in href and ('/event/' in href or '/e/' in href or '/events/' in href):
                        if href.startswith('http'):
                            browser.close()
                            return href
                        if href.startswith('/'):
                            browser.close()
                            return metrix_url.split('?')[0].rstrip('/') + href
                        browser.close()
                        return 'https://' + href.lstrip('/')
                except Exception:
                    continue
            browser.close()
    except Exception:
        pass
    return ''


def _check_registration_start_in_future(text: str):
    try:
        st_pat = [
            r'Rekisteröityminen alkaa[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)',
            r'Ilmoittautuminen alkaa[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)',
            r'Registration starts[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)',
            r'Registrering startar[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)'
        ]
        for pat in st_pat:
            m = re.search(pat, text, re.I)
            if m:
                date_str = m.group(1)
                try:
                    parts = date_str.split()
                    dpart = parts[0]
                    tpart = parts[1] if len(parts) > 1 else '00:00'
                    sep = '.' if '.' in dpart else ('-' if '-' in dpart else '/')
                    dfields = dpart.split(sep)
                    day = int(dfields[0]); month = int(dfields[1]); year = int(dfields[2])
                    hh, mm = (0, 0)
                    if ':' in tpart:
                        hh, mm = [int(x) for x in tpart.split(':')[:2]]
                    start_dt = datetime(year, month, day, hh, mm)
                    if start_dt > datetime.now():
                        return {'registered': None, 'limit': None, 'remaining': None, 'note': 'registration-not-open', 'start': start_dt.isoformat()}
                except Exception:
                    pass
    except Exception:
        pass
    return None


def _extract_json_confirmed_capacity(text: str):
    try:
        m_confirmed = re.search(r'"confirmed"\s*:\s*(\d{1,4})', text)
        if m_confirmed is None:
            return None
        m_capacity = re.search(r'"capacity"\s*:\s*(\d{1,4})', text)
        m_max = re.search(r'"maxPlayers"\s*:\s*(\d{1,4})', text)
        if m_capacity is None and m_max is None:
            return None
        try:
            reg = int(m_confirmed.group(1))
        except Exception:
            return None
        lim = None
        if m_capacity is not None:
            try:
                lim = int(m_capacity.group(1))
            except Exception:
                return None
        elif m_max is not None:
            try:
                lim = int(m_max.group(1))
            except Exception:
                return None
        if lim is None:
            return None
        return {'registered': reg, 'limit': lim, 'remaining': lim - reg, 'note': 'tjing-direct-json'}
    except Exception:
        pass
    return None


def _parse_labelled_b_blocks(soup: BS):
    try:
        b_tags = soup.find_all('b')
        parsed_limit = None
        parsed_remaining = None
        for b in b_tags:
            parts = [s.strip() for s in b.stripped_strings]
            if not parts:
                continue
            num = None
            if parts and re.match(r'^\d{1,4}$', parts[0]):
                num = int(parts[0])
            label = ' '.join(parts[1:]).lower() if len(parts) > 1 else ''
            if not label:
                span = b.find('span')
                if span is not None:
                    label = (span.get_text(strip=True) or '').lower()
            if num is not None and label:
                if 'max' in label or 'max spots' in label or 'maxim' in label or 'maxspelare' in label:
                    parsed_limit = num
                if 'available' in label or 'available spots' in label or 'slots left' in label or 'lediga' in label or 'paikkoja' in label:
                    parsed_remaining = num
        if parsed_limit is not None or parsed_remaining is not None:
            reg_val = None
            lim_val = parsed_limit
            rem_val = parsed_remaining
            if lim_val is not None and rem_val is not None:
                reg_val = lim_val - rem_val
            return {'registered': reg_val, 'limit': lim_val, 'remaining': rem_val, 'note': 'tjing-labelled-b'}
    except Exception:
        pass
    return None


def _extract_slots_text(page_text: str):
    try:
        m_spel = re.search(r"(\d{1,4})\s*(?:bekräftade|bekräftade spelare|spelare|deltagare)", page_text, re.I)
        m_cap = re.search(r"(\d{1,4})\s*(?:max|maximalt|kapacitet|platser|maxspelare|maxPlayers|capacity)", page_text, re.I)
        if m_spel is None and m_cap is None:
            return None
        reg = None
        lim = None
        if m_spel:
            try:
                reg = int(m_spel.group(1))
            except Exception:
                reg = None
        if m_cap:
            try:
                lim = int(m_cap.group(1))
            except Exception:
                lim = None
        if reg is not None and lim is not None:
            return {'registered': reg, 'limit': lim, 'remaining': lim - reg, 'note': 'tjing-direct-text'}
        if reg is not None and lim is None:
            return {'registered': reg, 'limit': None, 'remaining': None, 'note': 'tjing-registered'}
    except Exception:
        pass
    return None


def _extract_remaining_jsonlike(text: str):
    try:
        m_remaining_json = re.search(r'"remaining"\s*:\s*(\d{1,4})', text)
        m_remaining_alt = re.search(r'"remainingSlots"\s*:\s*(\d{1,4})', text)
        m_available = re.search(r'"available"\s*:\s*(\d{1,4})', text)
        if m_remaining_json:
            try:
                rem_val = int(m_remaining_json.group(1))
                return {'registered': None, 'limit': None, 'remaining': rem_val, 'note': 'tjing-remaining-json'}
            except Exception:
                pass
        if m_remaining_alt:
            try:
                rem_val = int(m_remaining_alt.group(1))
                return {'registered': None, 'limit': None, 'remaining': rem_val, 'note': 'tjing-remaining-json'}
            except Exception:
                pass
        if m_available:
            try:
                rem_val = int(m_available.group(1))
                return {'registered': None, 'limit': None, 'remaining': rem_val, 'note': 'tjing-remaining-json'}
            except Exception:
                pass
    except Exception:
        pass
    return None


def _playwright_tjing_fallback(tjing_url: str, timeout: int = 10):
    if sync_playwright is None:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(tjing_url, timeout=timeout * 1000)
            state = None
            try:
                state = page.evaluate("() => (window.__INITIAL_STATE__ || window.__INITIAL_DATA__ || window.__INITIAL || null)")
            except Exception:
                state = None
            content = page.content()
            body_text = page.inner_text('body') if page.query_selector('body') else ''
            browser.close()

        # check state dict for keys
        if isinstance(state, dict):
            def deep_find(obj, keys):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in keys and isinstance(v, int):
                            return v
                        res = deep_find(v, keys)
                        if res is not None:
                            return res
                elif isinstance(obj, list):
                    for it in obj:
                        res = deep_find(it, keys)
                        if res is not None:
                            return res
                return None

            reg_s = deep_find(state, ('confirmed', 'confirmedPlayers', 'playersConfirmed', 'registered'))
            lim_s = deep_find(state, ('capacity', 'maxPlayers', 'max', 'slots', 'capacityLimit'))
            if reg_s is not None or lim_s is not None:
                rem = None
                if reg_s is not None and lim_s is not None:
                    rem = int(lim_s) - int(reg_s)
                return {'registered': reg_s, 'limit': lim_s, 'remaining': rem, 'note': 'tjing-playwright-state'}

        # phrase search in rendered content
        try:
            soup_try_phrase = BS(content or '', 'html.parser')
            whole_text = soup_try_phrase.get_text(" ", strip=True)
            phrase_patterns = (
                r'Maximum number of players[:\s]*([0-9]{1,3})',
                r'Maximum number of competitors[:\s]*([0-9]{1,3})',
                r'Max participants[:\s]*([0-9]{1,3})',
                r'Maksimi(?: osallistujamäärä| osallistujamäärä)[:\s]*([0-9]{1,3})',
                r'Maksimi(?: osallistujat| osallistujamäärä)[:\s]*([0-9]{1,3})',
                r'Suurin osallistujamäärä[:\s]*([0-9]{1,3})',
                r'Enintään[:\s]*([0-9]{1,3})\s*(?:pelaaj|pelaajaa|osallistuja)'
            )
            found_lim = None
            for pat in phrase_patterns:
                mlim = re.search(pat, whole_text, re.I)
                if mlim:
                    try:
                        val = int(mlim.group(1))
                        if 0 <= val < 1000:
                            found_lim = val
                            break
                    except Exception:
                        continue

            if found_lim is not None:
                reg_patterns = (r'Registered[:\s]*([0-9]{1,4})', r'Ilmoittautuneet[:\s]*([0-9]{1,4})', r'Registrations[:\s]*([0-9]{1,4})')
                found_reg = None
                for rpat in reg_patterns:
                    mreg = re.search(rpat, whole_text, re.I)
                    if mreg:
                        try:
                            found_reg = int(mreg.group(1))
                            break
                        except Exception:
                            pass
                if found_reg is None:
                    found_reg = 0
                rem_calc = None
                try:
                    rem_calc = int(found_lim) - int(found_reg)
                except Exception:
                    rem_calc = None
                return {'registered': found_reg, 'limit': found_lim, 'remaining': rem_calc, 'note': 'metrix-direct-phrase'}
        except Exception:
            pass

        # rendered row heuristics
        try:
            soup_r = BS(content or '', 'html.parser')
            candidates = []
            for tr in soup_r.find_all('tr'):
                bnums = []
                for b in tr.find_all('b'):
                    t = (b.get_text(strip=True) or '').strip()
                    if re.match(r'^\d{1,4}$', t):
                        try:
                            bnums.append(int(t))
                        except Exception:
                            pass
                if len(bnums) >= 2:
                    tr_text = tr.get_text(' ', strip=True).lower()
                    candidates.append((tr_text, bnums))
            preferred_keywords = ('total', 'yhteensä', 'yhteensa', 'rekister', 'ilmoittau', 'määrä', 'summa', 'totalen', 'totalt', 'max')
            for txt, bnums in candidates:
                if len(bnums) > 1 and (bnums[1] is None or bnums[1] >= 1000):
                    continue
                if any(k in txt for k in preferred_keywords):
                    reg_val = bnums[0]
                    lim_val = bnums[1]
                    rem_val = (lim_val - reg_val) if (lim_val is not None and reg_val is not None) else None
                    return {'registered': reg_val, 'limit': lim_val, 'remaining': rem_val, 'note': 'metrix-playwright-row-summary'}
            if candidates:
                sane = [c for c in candidates if len(c[1])>1 and c[1][1] < 1000]
                if sane:
                    best = max(sane, key=lambda it: it[1][1])
                    bnums = best[1]
                    reg_val = bnums[0]
                    lim_val = bnums[1]
                    rem_val = (lim_val - reg_val) if (lim_val is not None and reg_val is not None) else None
                    return {'registered': reg_val, 'limit': lim_val, 'remaining': rem_val, 'note': 'metrix-playwright-row-bestcandidate'}
            # labelled b fallback
            lbl = _parse_labelled_b_blocks(soup_r)
            if lbl:
                return lbl
        except Exception:
            pass

    except Exception as e:
        logger.exception('Playwright TJing fallback failed: %s', e)
    return None


def fetch_tjing_capacity(tjing_url: str, timeout=10):
    """Fetch TJing players/confirmed page or related URL and extract confirmed/capacity."""
    try:
        # ensure caller passed a TJing URL — do not treat Metrix or other domains as TJing
        if 'tjing.' not in (tjing_url or '').lower():
            return {'registered': None, 'limit': None, 'remaining': None, 'note': 'not-tjing-url'}
        # prefer the confirmed players endpoint
        url = tjing_url
        if 'players' not in tjing_url and not tjing_url.rstrip('/').endswith('/players'):
            url = tjing_url.rstrip('/') + '/players/confirmed'
        r = requests.get(url, headers=USER_AGENT, timeout=timeout)
        if r.status_code != 200:
            return {'registered': None, 'limit': None, 'remaining': None, 'note': f'tjing http {r.status_code}'}
        text = r.text
        # quick check: if the static page shows registration-start in the future,
        # skip extraction early
        start_future = _check_registration_start_in_future(text)
        if start_future:
            return start_future
        # try JSON-like patterns
        json_res = _extract_json_confirmed_capacity(text)
        if json_res:
            return json_res

        # parse visible text (Swedish keywords) and check for labelled <b><span> patterns
        soup = BS(text, 'html.parser')
        page_text = soup.get_text(separator=' ', strip=True)

        # Check Metrix main-header-meta for explicit max-players label first
        try:
            header_found, header_limit = _parse_metrix_main_header_meta(soup)
            if header_found:
                # attempt to determine registered count from page (table or text)
                metrix_reg = None
                try:
                    mreg = re.search(r'(?:registered|ilmoittautuneet|rekisteröityneet|registered players|entries|participants)[:\s]*?(\d{1,4})', page_text, re.I)
                    if mreg:
                        metrix_reg = int(mreg.group(1))
                    else:
                        reg_table = None
                        for table in soup.find_all('table'):
                            hdrs = ' '.join([th.get_text(strip=True).lower() for th in table.find_all('th')])
                            if 'name' in hdrs or 'nimi' in hdrs or 'table_name' in hdrs:
                                reg_table = table
                                break
                        if reg_table:
                            rows = [r for r in reg_table.find_all('tr') if r.find_all('td')]
                            metrix_reg = len(rows)
                        else:
                            metrix_reg = 0
                except Exception:
                    metrix_reg = None
                rem = None
                if header_limit is not None:
                    try:
                        rem = (header_limit - metrix_reg) if (metrix_reg is not None) else None
                    except Exception:
                        rem = None
                note = 'metrix-header'
                if header_limit is None:
                    note += ' no-limit-value'
                return _sanitize_capacity({'registered': metrix_reg, 'limit': header_limit, 'remaining': rem, 'note': note})
        except Exception:
            pass

        # Metrix-specific direct extraction: prefer explicit "Maximum number of players" shown on the page
        try:
            metrix_limit = None
            metrix_reg = None
            phrases = [r'Maximum number of players', r'Maximum number', r'Maximum players', r'maksimi', r'maksimimäärä', r'maksimi määrä', r'max antal spelare', r'Maksimi pelaajien määrä']
            for p in phrases:
                node = soup.find(string=re.compile(p, re.I))
                if node:
                    parent = getattr(node, 'parent', None)
                    if parent is not None:
                        txt = parent.get_text(' ', strip=True)
                        nums = re.findall(r'(\d{1,4})', txt)
                        if nums:
                            metrix_limit = int(nums[-1])
                            break
            if metrix_limit is not None:
                # try to locate registered count; if none, default to 0
                mreg = re.search(r'(?:registered|ilmoittautuneet|rekisteröityneet|rekisteröityneet|registered players|registered on)[:\s]*?(\d{1,4})', page_text, re.I)
                if mreg:
                    metrix_reg = int(mreg.group(1))
                else:
                    try:
                        reg_table = None
                        for table in soup.find_all('table'):
                            hdrs = ' '.join([th.get_text(strip=True).lower() for th in table.find_all('th')])
                            if 'name' in hdrs or 'nimi' in hdrs or 'table_name' in hdrs:
                                reg_table = table
                                break
                        if reg_table:
                            rows = [r for r in reg_table.find_all('tr') if r.find_all('td')]
                            metrix_reg = len(rows)
                        else:
                            metrix_reg = 0
                    except Exception:
                        metrix_reg = 0
                rem = (metrix_limit - metrix_reg) if (metrix_limit is not None and metrix_reg is not None) else None
                logger.info('Metrix direct extraction (check): limit=%s reg=%s', metrix_limit, metrix_reg)
                return _sanitize_capacity({'registered': metrix_reg, 'limit': metrix_limit, 'remaining': rem, 'note': 'metrix-direct'})
        except Exception:
            pass

        # Quick Metrix-specific extraction: look for explicit "Maximum number of players" lines
        try:
            metrix_limit = None
            metrix_reg = None
            # search for common phrases in multiple languages near numeric values
            phrases = [r'Maximum number of players', r'Maximum number', r'Maximum players', r'maksimi', r'maksimimäärä', r'maksimi määrä', r'max antal spelare', r'Maksimi pelaajien määrä']
            for p in phrases:
                node = soup.find(string=re.compile(p, re.I))
                if node:
                    parent = getattr(node, 'parent', None)
                    if parent is not None:
                        txt = parent.get_text(' ', strip=True)
                        nums = re.findall(r'(\d{1,4})', txt)
                        if nums:
                            metrix_limit = int(nums[-1])
                            break
            # if we found a metrix limit, attempt to find registered count nearby or default to 0
            if metrix_limit is not None:
                # try to find explicit registered count in page text
                mreg = re.search(r'(?:registered|ilmoittautuneet|rekisteröityneet|rekisteröityneet|registered players|registered on)[:\s]*?(\d{1,4})', page_text, re.I)
                if mreg:
                    metrix_reg = int(mreg.group(1))
                else:
                    # look for a registration table and count rows if present
                    try:
                        # find table under registration view
                        reg_table = None
                        for table in soup.find_all('table'):
                            hdrs = ' '.join([th.get_text(strip=True).lower() for th in table.find_all('th')])
                            if 'name' in hdrs or 'nimi' in hdrs or 'table_name' in hdrs:
                                reg_table = table
                                break
                        if reg_table:
                            rows = [r for r in reg_table.find_all('tr') if r.find_all('td')]
                            metrix_reg = len(rows)
                        else:
                            metrix_reg = 0
                    except Exception:
                        metrix_reg = 0
                # compute remaining and return authoritative Metrix result
                rem = (metrix_limit - metrix_reg) if (metrix_limit is not None and metrix_reg is not None) else None
                logger.info('Metrix direct extraction: limit=%s reg=%s', metrix_limit, metrix_reg)
                return _sanitize_capacity({'registered': metrix_reg, 'limit': metrix_limit, 'remaining': rem, 'note': 'metrix-direct'})
        except Exception:
            pass

        # Parse Metrix-style registration statistics tables (prefer explicit Määrä / Max)
        try:
            for table in soup.find_all('table'):
                # normalize header text of table (if present)
                headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
                header_text = ' '.join(headers)
                # prefer tables that have Määrä and Max columns (Finnish)
                if 'määrä' in header_text and ('max' in header_text or 'max' in header_text):
                    # look for a row that contains registration summary keywords
                    for tr in table.find_all('tr'):
                        cells = [c.get_text(strip=True) for c in tr.find_all(['th', 'td'])]
                        if not cells:
                            continue
                        first = cells[0].lower()
                        if any(k in first for k in ('rekisteröityneiden', 'rekisteröityneiden pelaajien määrä', 'rekisteröityneet', 'rekisteröityneiden pelaajien määrä:', 'rekisteröityminen')):
                            nums = [int(m.group(1)) for c in cells for m in [re.search(r'(\d{1,4})', c)] if m]
                            # typical layout: per-class counts then total, max, waiting
                            if len(nums) >= 2:
                                # assume last two numbers are total_registered and max
                                reg = nums[-3] if len(nums) >= 3 else nums[0]
                                lim = nums[-2] if len(nums) >= 2 else None
                                remaining = (lim - reg) if (reg is not None and lim is not None) else None
                                return {'registered': reg, 'limit': lim, 'remaining': remaining, 'note': 'metrix-table'}
                            elif len(nums) == 1:
                                return {'registered': nums[0], 'limit': None, 'remaining': None, 'note': 'metrix-table-single'}
                # fallback: if table contains columns 'määrä' and 'max' anywhere, try to extract a summary row
                cols = ' '.join([c.get_text(strip=True).lower() for c in table.find_all(['th','td'])])
                if 'määrä' in cols and 'max' in cols:
                    # find any row mentioning 'rekister' and pull numbers
                    for tr in table.find_all('tr'):
                        cells = [c.get_text(strip=True) for c in tr.find_all(['th','td'])]
                        if not cells:
                            continue
                        if any('rekister' in c.lower() for c in cells):
                            nums = [int(m.group(1)) for c in cells for m in [re.search(r'(\d{1,4})', c)] if m]
                            if len(nums) >= 2:
                                reg = nums[-3] if len(nums) >= 3 else nums[0]
                                lim = nums[-2] if len(nums) >= 2 else None
                                remaining = (lim - reg) if (reg is not None and lim is not None) else None
                                return {'registered': reg, 'limit': lim, 'remaining': remaining, 'note': 'metrix-table-heuristic'}
        except Exception:
            pass

        # If the page shows a registration start date and it is in the future,
        # treat the competition as not open yet and skip capacity extraction.
        try:
            # Finnish / English / Swedish keywords
            start_patterns = [
                r'Rekisteröityminen alkaa[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)',
                r'Ilmoittautuminen alkaa[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)',
                r'Registration starts[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)',
                r'Registrering startar[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)'
            ]
            for pat in start_patterns:
                mstart = re.search(pat, page_text, re.I)
                if mstart:
                    date_str = mstart.group(1)
                    # parse common dd.mm.yyyy and optional time HH:MM
                    try:
                        parts = date_str.split()
                        dpart = parts[0]
                        tpart = parts[1] if len(parts) > 1 else '00:00'
                        sep = '.' if '.' in dpart else ('-' if '-' in dpart else '/')
                        dfields = dpart.split(sep)
                        day = int(dfields[0])
                        month = int(dfields[1])
                        year = int(dfields[2])
                        hh, mm = (0, 0)
                        if ':' in tpart:
                            hh, mm = [int(x) for x in tpart.split(':')[:2]]
                        start_dt = datetime(year, month, day, hh, mm)
                        now = datetime.now()
                        if start_dt > now:
                            return {'registered': None, 'limit': None, 'remaining': None, 'note': 'registration-not-open', 'start': start_dt.isoformat()}
                    except Exception:
                        # if parsing fails, continue to other heuristics
                        pass
        except Exception:
            pass

        # check for labelled <b> blocks like: <b>72 <span>Max spots</span></b>
        lbl = _parse_labelled_b_blocks(soup)
        if lbl:
            return lbl
        # direct text patterns like 'confirmed players' and 'max'
        slots = _extract_slots_text(page_text)
        if slots:
            return slots

        # fallback to earlier heuristics on page text
        reg2, lim2 = _extract_registered_and_limit(page_text)
        if reg2 is not None or lim2 is not None:
            rem = None
            if reg2 is not None and lim2 is not None:
                rem = lim2 - reg2
            elif reg2 is None and lim2 is not None:
                rem = lim2
                return {'registered': reg2, 'limit': lim2, 'remaining': rem, 'note': 'tjing-fallback'}

        # explicit remaining fields in embedded JS/HTML
        rem_js = _extract_remaining_jsonlike(text)
        if rem_js:
            return rem_js

        # Look for phrases like 'X slots left', Swedish/Finnish variants
        m_slots = re.search(r"(\d{1,4})\s*(?:available spots|slots left|places left|platser kvar|lediga platser|ledig plats|paikkoja jäljellä|paikkoja kvar|vapaita paikkoja)", page_text, re.I)
        if m_slots:
            try:
                rem_val = int(m_slots.group(1))
                return {'registered': None, 'limit': None, 'remaining': rem_val, 'note': 'tjing-remaining-text'}
            except Exception:
                pass

        # data-* attributes e.g. data-remaining="12"
        m_data_attr = re.search(r'data-(?:remaining|spots|available)\s*=\s*"?(\d{1,4})"?', text)
        if m_data_attr:
            try:
                rem_val = int(m_data_attr.group(1))
                return {'registered': None, 'limit': None, 'remaining': rem_val, 'note': 'tjing-data-attr'}
            except Exception:
                pass

        # If still nothing, try headless-rendered fallback using Playwright (if available)
        play_res = _playwright_tjing_fallback(tjing_url, timeout=timeout)
        if play_res:
            # If the playwright helper returned a dict, return it
            return play_res

        return {'registered': None, 'limit': None, 'remaining': None, 'note': 'tjing-no-data'}
    except Exception as e:
        logger.exception('fetch_tjing_capacity failed: %s', e)
        return {'registered': None, 'limit': None, 'remaining': None, 'note': str(e)}


def _extract_registered_and_limit(text: str):
    """Try multiple heuristics to find registered and limit numbers from page text.
    Returns (registered:int, limit:int) or (None, None) if not found.
    """
    if not text:
        return (None, None)
    t = text

    # 1) look for patterns like "12 / 30" or "12/30"
    m = re.search(r"(\d{1,4})\s*/\s*(\d{1,4})", t)
    if m:
        try:
            reg = int(m.group(1))
            lim = int(m.group(2))
            return (reg, lim)
        except Exception:
            pass

    # 1b) look for explicit 'Maximum number of players: 36' and variants
    m_maxphrase = re.search(r"(?:maximum(?: number of)? players|maximum players|max players|maksimi|maksimimäärä|max antal spelare)[:\s]*?(\d{1,4})", t, re.I)
    if m_maxphrase:
        try:
            lim = int(m_maxphrase.group(1))
            return (None, lim)
        except Exception:
            pass

    # 2) look for named phrases (Finnish/English)
    # registered
    reg_m = re.search(r"(?:ilmoittautuneet|ilmoittautuneita|registered|entries|participants)[:\s]*?(\d{1,4})", t, re.I)
    lim_m = re.search(r"(?:max|min|max players|capacity|paikat|paikkoja|maksimi)[:\s]*?(\d{1,4})", t, re.I)
    if reg_m and lim_m:
        try:
            return (int(reg_m.group(1)), int(lim_m.group(1)))
        except Exception:
            pass

    # 3) look for "X places left" or "paikkoja jäljellä X"
    left_m = re.search(r"(\d{1,4})\s*(?:places left|spots left|paikkoja jäljellä|paikkoja)", t, re.I)
    if left_m:
        try:
            left = int(left_m.group(1))
            # we don't know limit; return (None, None) but include left in caller via searching separately
            return (None, left)
        except Exception:
            pass

    return (None, None)


def check_competition_capacity(url: str, timeout=15):
    """Fetch the competition page and attempt to determine remaining capacity.
    Returns a dict with keys: registered, limit, remaining (all ints or None).
    """
    try:
        r = requests.get(url, headers=USER_AGENT, timeout=timeout)
        if r.status_code != 200:
            return {'registered': None, 'limit': None, 'remaining': None, 'note': f'http {r.status_code}'}
        r.encoding = r.apparent_encoding
        text = r.text
        # Prefer visible page text
        soup = BS(text, 'html.parser')
        page_text = soup.get_text(separator=' ', strip=True)

        # If the Metrix page indicates TJing registration, try to follow the TJing link
        try:
            tjing_link = _find_tjing_link(soup, page_text, base_url=url)
            # If Metrix mentions Tjing somewhere (e.g. "Tjingissä"), attempt discovery
            if (not tjing_link) and re.search(r'\btjing\b|tjingissä|tjing i', page_text, re.I):
                discovered = _discover_tjing_event_from_metrix(url, soup, page_text, timeout=timeout)
                if discovered:
                    tjing_link = discovered
            if tjing_link:
                # if Metrix only links to TJing root, try to discover event-specific path
                if re.match(r'^https?://(?:www\.)?tjing\.(se|fi|no)(?:/)?$', tjing_link.rstrip('/')):
                    discovered = _discover_tjing_event_from_metrix(url, soup, page_text, timeout=timeout)
                    if discovered:
                        tjing_link = discovered
                tj = fetch_tjing_capacity(tjing_link, timeout=timeout)
                # sanitize negative/invalid results
                tj = _sanitize_capacity(tj)
                # prefer tjing result if meaningful
                if tj.get('registered') is not None or tj.get('limit') is not None or tj.get('remaining') is not None:
                    return tj
        except Exception:
            pass

        reg, lim = _extract_registered_and_limit(page_text)
        remaining = None
        note = ''
        if reg is not None and lim is not None:
            remaining = lim - reg
        elif reg is None and lim is not None:
            # treat lim as remaining when function returned (None,left)
            remaining = lim
        elif reg is not None and lim is None:
            remaining = None

        # If the Metrix page mentions TJing explicitly, prefer following TJing
        # and let TJing extraction override Metrix-extracted numbers.
        try:
            if re.search(r'\btjing\b|tjingissä|tjing i|tjing\.', page_text, re.I):
                # try to find tjing URL
                tjing_link = _find_tjing_link(soup, page_text, base_url=url)
                if not tjing_link:
                    tjing_link = _discover_tjing_event_from_metrix(url, soup, page_text, timeout=timeout)
                if tjing_link:
                    tj = fetch_tjing_capacity(tjing_link, timeout=timeout)
                    tj = _sanitize_capacity(tj)
                    if tj.get('registered') is not None or tj.get('limit') is not None or tj.get('remaining') is not None:
                        return tj
                    # if tjing was mentioned but we couldn't extract, mark as tjing-mention
                    return {'registered': None, 'limit': None, 'remaining': None, 'note': 'metrix-tjing-mention'}
        except Exception:
            pass

        # If we didn't find numbers yet, try searching for table rows or meta info
        if remaining is None:
            # try looking for numeric patterns near keywords
            m = re.search(r"(\d{1,4})\s*(?:paikkoja|places|spots|left|jäljell)", page_text, re.I)
            if m:
                try:
                    remaining = int(m.group(1))
                    note = 'heuristic remaining'
                except Exception:
                    pass

        # TJing / Swedish-specific heuristics: many TJing pages embed JSON or use Swedish words like
        # "spelare" (players) or "Bekräftade"/"Bekräftade spelare" (confirmed players).
        # Look for JSON-like fields or Swedish keywords if we still don't have a value.
        if remaining is None and ('tjing' in url.lower() or 'tjing' in getattr(r, 'url', '').lower()):
            # try JSON-like patterns first
            m_json_reg = re.search(r'"confirmed"\s*:\s*(\d{1,4})', text)
            m_json_lim = re.search(r'"capacity"\s*:\s*(\d{1,4})', text)
            m_json_max = re.search(r'"maxPlayers"\s*:\s*(\d{1,4})', text)
            if m_json_reg:
                try:
                    reg = int(m_json_reg.group(1))
                    # if we have limit too
                    if m_json_lim or m_json_max:
                        lim_val = None
                        if m_json_lim:
                            lim_val = int(m_json_lim.group(1))
                        elif m_json_max:
                            lim_val = int(m_json_max.group(1))
                        if lim_val is not None:
                            remaining = lim_val - reg
                            note = 'tjing-json'
                            # override reg/lim
                            lim = lim_val
                    else:
                        # only registered known; return registered
                        reg = int(m_json_reg.group(1))
                        remaining = None
                        note = 'tjing-registered'
                except Exception:
                    pass

            # Swedish text patterns
            if remaining is None:
                m_spelare = re.search(r'(\d{1,4})\s*(?:spelare|deltagare|bekräftade|bekräftade spelare)', page_text, re.I)
                if m_spelare:
                    try:
                        val = int(m_spelare.group(1))
                        # assume this is registered count
                        reg = val
                        remaining = None
                        note = 'tjing-spelare'
                    except Exception:
                        pass

            # generic JSON-like fallback: look for "players": {"confirmed": N}
            if remaining is None:
                m_players_confirmed = re.search(r'"players"\s*[:=]\s*\{[^}]*"confirmed"\s*[:=]\s*(\d{1,4})', text)
                if m_players_confirmed:
                    try:
                        reg = int(m_players_confirmed.group(1))
                        remaining = None
                        note = 'tjing-players-json'
                    except Exception:
                        pass

        # As a last resort, render the page (if Playwright available) and re-run heuristics
        if sync_playwright is not None:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, timeout=timeout * 1000)
                    content = page.content()
                    body_text = page.inner_text('body') if page.query_selector('body') else ''
                    browser.close()

                # check rendered body for registration start date
                try:
                    for pat in (r'Rekisteröityminen alkaa[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)',
                                r'Registration starts[:\s]*([0-3]?\d[.\-/][01]?\d[.\-/]\d{4}(?:\s+\d{1,2}:\d{2})?)'):
                        m = re.search(pat, body_text, re.I)
                        if m:
                            ds = m.group(1)
                            try:
                                parts = ds.split()
                                dpart = parts[0]
                                tpart = parts[1] if len(parts) > 1 else '00:00'
                                sep = '.' if '.' in dpart else ('-' if '-' in dpart else '/')
                                dfields = dpart.split(sep)
                                day = int(dfields[0]); month = int(dfields[1]); year = int(dfields[2])
                                hh, mm = (0, 0)
                                if ':' in tpart:
                                    hh, mm = [int(x) for x in tpart.split(':')[:2]]
                                start_dt = datetime(year, month, day, hh, mm)
                                if start_dt > datetime.now():
                                    return {'registered': None, 'limit': None, 'remaining': None, 'note': 'registration-not-open', 'start': start_dt.isoformat()}
                            except Exception:
                                pass
                except Exception:
                    pass

                # Prefer explicit phrase extraction in the rendered Metrix DOM
                try:
                    soup_r = BS(content or '', 'html.parser')
                    whole_text = soup_r.get_text(' ', strip=True)
                    # look for explicit limit phrases first
                    phrase_patterns = (
                        r'Maximum number of players[:\s]*([0-9]{1,3})',
                        r'Maximum number[:\s]*([0-9]{1,3})',
                        r'Maksimi(?: osallistujamäärä| osallistujamäärä)[:\s]*([0-9]{1,3})',
                        r'Suurin osallistujamäärä[:\s]*([0-9]{1,3})',
                    )
                    found_lim = None
                    for pat in phrase_patterns:
                        mlim = re.search(pat, whole_text, re.I)
                        if mlim:
                            try:
                                val = int(mlim.group(1))
                                if 0 <= val < 1000:
                                    found_lim = val
                                    break
                            except Exception:
                                continue
                    if found_lim is not None:
                        # find registered count if present, default 0
                        mreg = re.search(r'(?:registered|ilmoittautuneet|rekisteröityneet|registered players|the number of registered players)[:\s]*?(\d{1,4})', whole_text, re.I)
                        found_reg = int(mreg.group(1)) if mreg else 0
                        rem = None
                        try:
                            rem = int(found_lim) - int(found_reg)
                        except Exception:
                            rem = None
                        return _sanitize_capacity({'registered': found_reg, 'limit': found_lim, 'remaining': rem, 'note': 'metrix-playwright-phrase'})
                except Exception:
                    pass

                # re-run heuristics on rendered text
                reg3, lim3 = _extract_registered_and_limit(body_text or content)
                if reg3 is not None or lim3 is not None:
                    rem = None
                    if reg3 is not None and lim3 is not None:
                        rem = lim3 - reg3
                    elif reg3 is None and lim3 is not None:
                        rem = lim3
                    # mark source: if the URL is Metrix, prefer metrix-playwright
                    note_tag = 'metrix-playwright' if 'metrix' in (url or '').lower() else 'playwright-fallback'
                    return _sanitize_capacity({'registered': reg3, 'limit': lim3, 'remaining': rem, 'note': note_tag})
            except Exception:
                pass

        final = {'registered': reg, 'limit': lim, 'remaining': remaining, 'note': note}
        return _sanitize_capacity(final)
    except Exception as e:
        return {'registered': None, 'limit': None, 'remaining': None, 'note': str(e)}



def find_low_capacity(files=None, threshold=20):
    """Read competition lists from JSON files (list of paths) and return entries
    where registration is open and remaining <= threshold.
    If files is None, default to PDGA.json, VIIKKOKISA.json, DOUBLES.json in project root.
    """
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    default_files = [os.path.join(base, n) for n in ('PDGA.json', 'VIIKKOKISA.json', 'DOUBLES.json')]
    files = files or default_files

    comps = []
    for p in files:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    comps.extend(data)
                elif isinstance(data, dict):
                    for v in data.values():
                        if isinstance(v, list):
                            comps.extend(v)
                        else:
                            comps.append(v)
        except Exception:
            continue

    # Pre-scan for TJing registrations so we can follow TJing when Metrix only mentions it
    try:
        tjings = scan_pdga_for_tjing()
        tjing_map = {t.get('metrix'): t.get('tjing') for t in tjings if t.get('metrix') and t.get('tjing')}
    except Exception:
        tjing_map = {}

    alerts = []
    for c in comps:
        url = c.get('url') or c.get('link') or ''
        if not url:
            continue
        cap = check_competition_capacity(url)
        # If Metrix explicitly mentioned TJing but we returned no numbers, try to follow TJing
        if cap.get('note') == 'metrix-tjing-mention':
            # try map from pre-scan
            try:
                tj = None
                if url in tjing_map:
                    tj = tjing_map.get(url)
                else:
                    # attempt to discover from Metrix page
                    try:
                        r = requests.get(url, headers=USER_AGENT, timeout=12)
                        if r.status_code == 200:
                            soup = BS(r.text, 'html.parser')
                            page_text = soup.get_text(separator=' ', strip=True)
                            tj = _discover_tjing_event_from_metrix(url, soup, page_text, timeout=8)
                    except Exception:
                        tj = None
                if tj:
                    tjcap = fetch_tjing_capacity(tj)
                    tjcap = _sanitize_capacity(tjcap)
                    if tjcap and (tjcap.get('registered') is not None or tjcap.get('limit') is not None or tjcap.get('remaining') is not None):
                        cap = tjcap
            except Exception:
                pass
        rem = cap.get('remaining')
        if rem is None:
            continue
        if rem <= threshold:
            entry = {
                'id': c.get('id') or c.get('name') or c.get('title'),
                'title': c.get('title') or c.get('name') or '',
                'url': url,
                'remaining': rem,
                'registered': cap.get('registered'),
                'limit': cap.get('limit'),
                'note': cap.get('note')
            }
            alerts.append(entry)

    # persist alerts
    out = os.path.join(base, 'CAPACITY_ALERTS.json')
    try:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(alerts, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return alerts


def scan_pdga_for_tjing(files=None, out_name='TJING_REGISTRATIONS.json'):
    """Scan PDGA/known competitions for Metrix pages that mention TJing registration.
    Writes a JSON file with entries that contain the discovered TJing registration URL.
    """
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    default_files = [os.path.join(base, 'known_pdga_competitions.json'), os.path.join(base, 'PDGA.json')]
    files = files or default_files

    comps = []
    for p in files:
        try:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        comps.extend(data)
                    elif isinstance(data, dict):
                        for v in data.values():
                            if isinstance(v, list):
                                comps.extend(v)
                            else:
                                comps.append(v)
        except Exception:
            continue

    results = []
    for c in comps:
        metrix = c.get('url') or c.get('link') or ''
        if not metrix:
            continue
        try:
            r = requests.get(metrix, headers=USER_AGENT, timeout=12)
            if r.status_code != 200:
                continue
            r.encoding = r.apparent_encoding
            soup = BS(r.text, 'html.parser')
            page_text = soup.get_text(separator=' ', strip=True)
            tj = _find_tjing_link(soup, page_text, base_url=metrix)
            if tj:
                results.append({
                    'id': c.get('id') or c.get('name') or c.get('title'),
                    'title': c.get('title') or c.get('name') or '',
                    'metrix': metrix,
                    'tjing': tj
                })
        except Exception as e:
            logger.exception('scan_pdga_for_tjing failed for %s: %s', metrix, e)

    out = os.path.join(base, out_name)
    try:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return results


if __name__ == '__main__':
    start = time.time()
    alerts = find_low_capacity()
    print(f'Found {len(alerts)} low-capacity competitions in {time.time()-start:.2f}s')
    for a in alerts:
        print(f"- {a['id']} | {a['title']} -> remaining={a['remaining']} | {a['url']}")
