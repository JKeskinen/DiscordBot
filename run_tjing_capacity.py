#!/usr/bin/env python3
import os
import json
from komento_koodit.check_capacity import scan_pdga_for_tjing, fetch_tjing_capacity
from komento_koodit import data_store

BASE = os.path.abspath(os.path.dirname(__file__))
TJ_REG = os.path.join(BASE, 'TJING_REGISTRATIONS.json')
OUT = os.path.join(BASE, 'TJING_CAPACITY.json')


def main():
    # prefer existing registrations file if present
    # prefer existing registrations from sqlite-backed store (fallback to file)
    regs = data_store.load_category(os.path.basename(TJ_REG))
    if not regs:
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
        data_store.save_category(os.path.basename(OUT), results)
    except Exception:
        pass

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
