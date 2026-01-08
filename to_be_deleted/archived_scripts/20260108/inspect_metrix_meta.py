import sys
import requests
from bs4 import BeautifulSoup as BS

USER_AGENT = {'User-Agent': 'Mozilla/5.0 (metrixbot-inspect)'}

urls = sys.argv[1:]
if not urls:
    print('Usage: inspect_metrix_meta.py <url> [url2 ...]')
    sys.exit(1)

for url in urls:
    print('URL:', url)
    try:
        r = requests.get(url, headers=USER_AGENT, timeout=15)
        print('HTTP', r.status_code)
        r.encoding = r.apparent_encoding
        soup = BS(r.text, 'html.parser')
        ul = soup.find('ul', class_='main-header-meta')
        if ul is None:
            print('UL: not found')
        else:
            lis = ul.find_all('li')
            print('UL found; li count =', len(lis))
            for i,li in enumerate(lis[:20],1):
                txt = li.get_text(' ', strip=True)
                print(f' li[{i}]:', txt)
            # print a shortened html of ul
            print('UL HTML snippet:')
            print(str(ul)[:1000])
    except Exception as e:
        print('Error fetching', e)
    print('-' * 60)
