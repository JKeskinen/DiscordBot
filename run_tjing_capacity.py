#!/usr/bin/env python3
import os
import json
from komento_koodit.check_capacity import scan_pdga_for_tjing, fetch_tjing_capacity

BASE = os.path.abspath(os.path.dirname(__file__))
TJ_REG = os.path.join(BASE, 'TJING_REGISTRATIONS.json')
OUT = os.path.join(BASE, 'TJING_CAPACITY.json')


def main():
    # prefer existing registrations file if present
    if os.path.exists(TJ_REG):
        try:
            with open(TJ_REG, 'r', encoding='utf-8') as f:
                regs = json.load(f)
        except Exception:
            regs = scan_pdga_for_tjing()
    else:
        regs = scan_pdga_for_tjing()

    # dedupe by tjing url
    seen = set()
    uniq = []
    for r in regs:
        tj = r.get('tjing') or ''
        if not tj or tj in seen:
            continue
        seen.add(tj)
        uniq.append(r)

    results = []
    for r in uniq:
        tj = r.get('tjing')
        if '/event/' not in tj.lower():
            # skip generic site root or non-event links
            results.append({
                'id': r.get('id'),
                'title': r.get('title'),
                'tjing': tj,
                'note': 'no-event-path'
            })
            continue
        cap = fetch_tjing_capacity(tj)
        results.append({
            'id': r.get('id'),
            'title': r.get('title'),
            'tjing': tj,
            'capacity': cap
        })

    try:
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
