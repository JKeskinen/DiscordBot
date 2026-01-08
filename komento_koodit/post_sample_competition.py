import sys
import os
import pathlib
import sys
import json

# ensure project root on path
ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from komento_koodit import post_pending_registration as ppr


def _format_date(s):
    # Try to canonicalize common forms into DD.MM.YYYY or DD.MM.YYYY HH:MM
    from datetime import datetime
    if not s:
        return ''
    s = str(s).strip()
    patterns = [
        '%d.%m.%Y %H:%M', '%d.%m.%Y', '%Y-%m-%d %H:%M', '%Y-%m-%d',
        '%m/%d/%y %H:%M', '%m/%d/%y', '%d/%m/%Y %H:%M', '%d/%m/%Y',
        '%m/%d/%Y %H:%M', '%m/%d/%Y'
    ]
    for p in patterns:
        try:
            dt = datetime.strptime(s, p)
            if '%H' in p:
                return dt.strftime('%d.%m.%Y %H:%M')
            return dt.strftime('%d.%m.%Y')
        except Exception:
            continue
    # fallback: return original
    return s


def build_clean_embed(item):
    # Fields to show per user's preference
    # date: show as 'Aika: ...'
    # note -> Luokat: ...
    # registration_open -> 'REKISTERÖINTI: AUKI' or 'REKISTERÖINTI: SULJETTU'
    # url -> show as link line
    lines = []
    raw_date = item.get('date') or item.get('starts') or item.get('start')
    date_str = _format_date(raw_date)
    if date_str:
        lines.append(f'Aika: {date_str}')

    # parse classes from note if present
    note = item.get('note') or ''
    if note:
        # naive: if note contains commas or class-like tokens, show as Luokat
        lines.append(f'Luokat: {note}')

    reg_open = item.get('registration_open')
    opening_soon = item.get('opening_soon')
    if reg_open:
        lines.append('REKISTERÖINTI: AUKI')
    elif opening_soon:
        lines.append('REKISTERÖINTI: AVAUTUU PIAN')
    else:
        lines.append('REKISTERÖINTI: SULJETTU')

    # capacity remaining from CAPACITY_CACHE when available
    url = item.get('url') or ''
    cap = ppr.CAPACITY_CACHE.get(url) or ppr.CAPACITY_CACHE.get(str(item.get('id')))
    if isinstance(cap, dict):
        rem = cap.get('remaining')
        lim = cap.get('limit')
        if rem is None and isinstance(cap.get('registered'), int) and isinstance(lim, int):
            rem = lim - cap.get('registered')
        if rem is not None:
            lines.append(f'Paikat: {rem}')
        elif lim is not None:
            lines.append(f'Paikat: 0/{lim}')

    # url line (link)
    if url:
        name = item.get('name') or item.get('title') or ''
        lines.append(f'Linkki: {url}')

    desc = '\n'.join(lines)
    embed = {'title': f"UUSI KILPAILU: {item.get('name') or item.get('title') or item.get('id')}",
             'description': desc, 'color': 5763714}
    return embed


def main(eid='3512586'):
    pending = ppr.load_pending()
    found = None
    for it in pending:
        if str(it.get('id')) == str(eid) or str(it.get('url') or '').endswith(str(eid)):
            found = it
            break
    if not found:
        print('Item not found in pending:', eid)
        return
    embed = build_clean_embed(found)
    print('Posting sample embed to', ppr.TEST_THREAD)
    ok = ppr.post_embeds(ppr.TEST_THREAD, [embed])
    if ok:
        print('Posted sample embed')
    else:
        print('Failed to post sample embed')


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else '3512586'
    main(arg)
