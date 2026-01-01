import requests
from bs4 import BeautifulSoup as BS
import re

URL = 'https://discgolfmetrix.com/3519179?view=registration'
HEADERS = {'User-Agent':'Mozilla/5.0 (metrixbot-capacity)'}
print('Fetching', URL)
r = requests.get(URL, headers=HEADERS, timeout=15)
print('HTTP', r.status_code)
html = r.text
soup = BS(html, 'html.parser')
# Try to find the exact row by text
row = None
for tr in soup.find_all('tr'):
    t0 = tr.find('td')
    if t0 and 'Rekisteröityneiden pelaajien määrä' in t0.get_text():
        row = tr
        break

if row is None:
    # try case-insensitive contains
    for tr in soup.find_all('tr'):
        if re.search(r'rekister\w*\s+pelaajien\s+määrä', tr.get_text(), re.I):
            row = tr
            break

if row is None:
    print('Registration row not found in static HTML.')
else:
    print('Found registration row:')
    cells = [c.get_text(strip=True) for c in row.find_all('td')]
    print('Cells:', cells)
    # extract bold numbers
    nums = [int(b.get_text(strip=True)) for b in row.find_all('b') if re.search(r'\d+', b.get_text())]
    print('Bold numbers:', nums)
    # attempt to map: registered, max, waiting from example
    if len(nums) >= 2:
        registered = nums[0]
        maxplayers = nums[1]
        waiting = nums[2] if len(nums) > 2 else 0
        print('Registered:', registered)
        print('Max players:', maxplayers)
        print('Waiting:', waiting)

# Also try the CSS selector the user gave
sel = '#content_auto > div > div > div:nth-child(1) > div > table > tbody > tr:nth-child(4) > td:nth-child(3) > b'
try:
    el = soup.select_one(sel)
    if el:
        print('Selector found (static):', el.get_text(strip=True))
    else:
        print('Selector not found in static HTML.')
except Exception as e:
    print('Selector check failed:', e)

# Save snapshot for inspection
with open('debug_tjing/registration_view.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Saved debug snapshot to debug_tjing/registration_view.html')
