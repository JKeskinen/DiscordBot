import json

def main():
    with open('CAPACITY_SCAN_RESULTS.json', 'r', encoding='utf-8') as fh:
        data = json.load(fh)

    bad = []
    waitlist = []
    no_limit = []
    unknown = []

    for e in data:
        r = e.get('capacity_result', {})
        reg = r.get('registered')
        lim = r.get('limit')
        note = str(r.get('note') or '')
        if reg is None and lim is None and r.get('remaining') is None:
            unknown.append((e['id'], e['name'], note))
        if reg is not None and lim is not None and reg > lim:
            bad.append((e['id'], e['name'], reg, lim, note))
        if 'waitlist' in note or r.get('queued'):
            waitlist.append((e['id'], e['name'], reg, lim, note, r.get('queued')))
        if r.get('metrix_header_empty'):
            no_limit.append((e['id'], e['name'], reg, lim, note))

    print('Total entries:', len(data))
    print('\nEntries with registered>limit:', len(bad))
    for x in bad:
        print(' -', x)

    print('\nEntries mentioning waitlist or queued:', len(waitlist))
    for x in waitlist:
        print(' -', x)

    print('\nEntries with metrix_header_empty (no visible limit):', len(no_limit))
    for x in no_limit:
        print(' -', x)

    print('\nEntries with unknown capacity (no numbers):', len(unknown))
    for x in unknown[:20]:
        print(' -', x)

if __name__ == '__main__':
    main()
