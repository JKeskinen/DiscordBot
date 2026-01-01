import requests
from bs4 import BeautifulSoup as BS
import re


PHRASES = [
    r'Maximum number of players', r'Maximum number', r'Maximum players',
    r'maksimi', r'maksimimäärä', r'maksimi määrä', r'max antal spelare',
    r'Maksimi pelaajien määrä'
]


def check_live_phrase(url: str, timeout: int = 20):
    """Check a Metrix page for explicit 'maximum number of players' phrases.

    Returns a dict: {
      'has_phrase': bool,
      'limit': int|None,
      'registered': int|None,
      'parent_text': str|None
    }
    """
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=timeout)
        if r.status_code != 200:
            return {'has_phrase': False, 'limit': None, 'registered': None, 'parent_text': None, 'note': f'http {r.status_code}'}
        r.encoding = r.apparent_encoding
        soup = BS(r.text, 'html.parser')
        page_text = soup.get_text(separator=' ', strip=True)

        found_node = None
        for ph in PHRASES:
            node = soup.find(string=re.compile(ph, re.I))
            if node:
                found_node = node
                break

        if not found_node:
            return {'has_phrase': False, 'limit': None, 'registered': None, 'parent_text': None}

        parent = found_node.parent
        parent_text = parent.get_text(' ', strip=True)
        nums = re.findall(r'(\d{1,4})', parent_text)
        limit = int(nums[-1]) if nums else None

        # attempt to find registered count in surrounding text
        reg = None
        mreg = re.search(r'(?:registered|ilmoittautuneet|rekisteröityneet|registered players|registered on|the number of registered players)[:\s]*?(\d{1,4})', page_text, re.I)
        if mreg:
            reg = int(mreg.group(1))
        else:
            # fallback: count rows in a likely registration table
            reg_table = None
            for table in soup.find_all('table'):
                hdrs = ' '.join([th.get_text(strip=True).lower() for th in table.find_all('th')])
                if 'name' in hdrs or 'nimi' in hdrs or 'table_name' in hdrs:
                    reg_table = table
                    break
            if reg_table:
                rows = [r for r in reg_table.find_all('tr') if r.find_all('td')]
                reg = len(rows)
            else:
                reg = 0

        return {'has_phrase': True, 'limit': limit, 'registered': reg, 'parent_text': parent_text}
    except Exception as e:
        return {'has_phrase': False, 'limit': None, 'registered': None, 'parent_text': None, 'note': str(e)}


if __name__ == '__main__':
    import sys
    u = sys.argv[1] if len(sys.argv) > 1 else 'https://discgolfmetrix.com/3512588'
    res = check_live_phrase(u)
    import json
    print(json.dumps(res, ensure_ascii=False, indent=2))
