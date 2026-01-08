import sys
import pathlib
import json

# ensure project root on path
ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from komento_koodit import post_pending_registration as ppr


def build_dummy():
    # Dummy competition as requested
    item = {
        'id': '9999999',
        'name': 'NurmosOpen',
        'title': 'NurmosOpen',
        'date': '30.04.2026 10:00',
        'registration_open': False,
        'opening_soon': True,  # opens 12.01.2026, today 05.01.2026 -> opening soon
        'opens_on': '12.01.2026',
        'registration_end': '01.04.2026',
        'kind': 'L - PDGA',
        'note': 'Luokat: MA1,MA3,PRO',
        'url': 'https://discgolfmetrix.com/9999999',
        'capacity': {'limit': 72}
    }
    return item


def build_embed_for_dummy(item):
    lines = []
    # Event date
    if item.get('date'):
        lines.append(f"Aika: {item.get('date')}")
    # Registration open info
    if item.get('registration_open'):
        lines.append('REKISTERÖINTI: AUKI')
    elif item.get('opening_soon'):
        # Use requested Finnish phrasing for opening date
        opens = item.get('opens_on') or item.get('opens') or ''
        if opens:
            lines.append(f'Ilmoittautuminen aukeaa: {opens}')
        else:
            lines.append('REKISTERÖINTI: AVAUTUU PIAN')
    else:
        lines.append('REKISTERÖINTI: SULJETTU')
    # Registration end
    if item.get('registration_end'):
        lines.append(f"Ilmoittautuminen päättyy: {item.get('registration_end')}")
    # Capacity
    cap = item.get('capacity') or {}
    lim = cap.get('limit')
    if lim is not None:
        lines.append(f'Paikat: {lim}')
    # Classes / note
    if item.get('note'):
        lines.append(item.get('note'))
    # Link
    if item.get('url'):
        lines.append(f'Linkki: {item.get("url")}')

    desc = '\n'.join(lines)
    embed = {
        'title': f"UUSI KILPAILU JULKAISTU: {item.get('name')}",
        'description': desc,
        'color': 5763714
    }
    return embed


def main():
    item = build_dummy()
    embed = build_embed_for_dummy(item)
    print('Posting dummy sample to', ppr.TEST_THREAD)
    ok = ppr.post_embeds(ppr.TEST_THREAD, [embed])
    if ok:
        print('Posted dummy sample')
    else:
        print('Failed to post dummy sample')


if __name__ == '__main__':
    main()
