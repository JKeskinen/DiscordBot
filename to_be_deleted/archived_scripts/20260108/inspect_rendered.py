from pathlib import Path
p=Path('debug_tjing/metrix_rendered.html')
if p.exists():
    txt=p.read_text(encoding='utf-8')
    print('file exists, len',len(txt))
    import re
    m=re.search(r'Rekister\w+\s+alkaa', txt)
    print('Rekisteröityminen alkaa found?', bool(m))
    if m:
        start = max(0,(m.start()-200))
        end = m.end()+200
        print(txt[start:end])
else:
    print('rendered file not found')
