import requests
import os
u='https://discgolfmetrix.com/3523186&view=result'
r=requests.get(u,timeout=20)
text=r.text
os.makedirs('scripts/html_debug',exist_ok=True)
with open('scripts/html_debug/3523186.html','w',encoding='utf-8') as f:
    f.write(text)
print('saved', len(text))
