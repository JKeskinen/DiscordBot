import sys
import pathlib
import requests
from collections import Counter
from bs4 import BeautifulSoup

# usage: python find_metrix_classes.py <url>
ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_URL = 'https://discgolfmetrix.com/3500547'


def extract_classes(html):
    soup = BeautifulSoup(html, 'html.parser')
    classes = []
    for tag in soup.find_all(True):
        cl = tag.get('class')
        if cl:
            for c in cl:
                if c and isinstance(c, str):
                    classes.append(c.strip())
    return classes


def main():
    url = DEFAULT_URL
    if len(sys.argv) > 1:
        url = sys.argv[1]
    print('Fetching', url)
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print('Failed to fetch URL:', e)
        return 1
    classes = extract_classes(r.text)
    cnt = Counter(classes)
    total = sum(cnt.values())
    unique = len(cnt)
    print(f'Found {unique} unique class names ({total} total occurrences)')
    print('Top classes:')
    for name, n in cnt.most_common(40):
        print(f'{n:4d}  {name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
