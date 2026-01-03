import requests
from bs4 import BeautifulSoup as BS
import sys

url = 'https://discgolfmetrix.com/3523186&view=result'
print('Fetching', url)
r = requests.get(url, timeout=20)
if r.status_code != 200:
    print('HTTP', r.status_code)
    sys.exit(1)

soup = BS(r.text, 'html.parser')
content = soup.select_one('#content_auto') or soup

# Find tables and inspect headers
for i, table in enumerate(content.find_all('table')):
    headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
    print('\nTable', i, 'headers:', headers[:10])
    # check if looks like HC table
    if any('muutos' in h for h in headers) or any('metrix' in h for h in headers) and any('rating' in h for h in headers):
        print('-> Possible HC/raw table')
    # print first 8 rows
    rows = table.find_all('tr')
    for r in rows[:8]:
        cells = [td.get_text(' ', strip=True) for td in r.find_all(['td','th'])]
        print('|'.join(cells))

print('\nDone')
