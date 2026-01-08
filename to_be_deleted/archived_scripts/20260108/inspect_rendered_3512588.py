from bs4 import BeautifulSoup as BS
import re
html = open('debug_verify/3512588.html', encoding='utf-8').read()
soup = BS(html, 'html.parser')
content = html
body_text = soup.get_text(' ', strip=True)
# find tr candidates
candidates = []
for tr in soup.find_all('tr'):
    bnums = []
    for b in tr.find_all('b'):
        t = (b.get_text(strip=True) or '').strip()
        if re.match(r'^\d{1,4}$', t):
            bnums.append(int(t))
    if len(bnums) >= 2:
        tr_text = tr.get_text(' ', strip=True).lower()
        candidates.append((tr_text, bnums))

print('Found', len(candidates), 'candidates')
for txt,bnums in candidates:
    print('TXT:', txt)
    print('BNUMS:', bnums)
    print('---')

# find all <b> standalone labelled patterns
for b in soup.find_all('b'):
    parts = [s.strip() for s in b.stripped_strings]
    if not parts: continue
    print('B PARTS:', parts)

# print snippet around 'Maximum number'
m = re.search(r'Maximum number of players[:\s]*', body_text)
if m:
    idx = m.start()
    print('\nSNIPPET:', body_text[idx:idx+200])
