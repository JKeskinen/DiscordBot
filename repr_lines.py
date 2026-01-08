with open('komento_koodit/commands_etsi.py','r',encoding='utf-8') as f:
    for i,line in enumerate(f, start=1):
        if 136<=i<=188:
            print(f"{i:04d}: {line!r}")
