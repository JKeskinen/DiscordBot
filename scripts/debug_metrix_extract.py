from bs4 import BeautifulSoup as BS
import re
p = 'debug_verify/3512588.html'
html = open(p, encoding='utf-8').read()
soup = BS(html, 'html.parser')
page_text = soup.get_text(separator=' ', strip=True)
phrases = [r'Maximum number of players', r'Maximum number', r'Maximum players', r'maksimi', r'maksimimäärä', r'maksimi määrä', r'max antal spelare', r'Maksimi pelaajien määrä']
found = False
for ph in phrases:
    node = soup.find(string=re.compile(ph, re.I))
    print('Phrase:', ph, '->', bool(node))
    if node:
        print('Parent text:', node.parent.get_text(' ', strip=True))
        found = True
print('Any found?', found)
print('\nSnippet around "Maximum number":\n')
# try to print nearby HTML
m = re.search(r'Maximum number of players[:\s]*', page_text)
if m:
    idx = m.start()
    print(page_text[idx:idx+200])
else:
    print('not in page_text')
