import sys
p='komento_koodit/commands_etsi.py'
with open(p,'r',encoding='utf-8') as f:
    for i,line in enumerate(f, start=1):
        if 150<=i<=180:
            sys.stdout.write(f"{i:04d}: {line}")
