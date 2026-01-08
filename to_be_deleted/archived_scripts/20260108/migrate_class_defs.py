#!/usr/bin/env python3
"""Migrate CAPACITY_SCAN_RESULTS.json:
- extract canonical class definitions into class_definitions.json
- prune spurious per-event class_counts where every class has count==1 (and there are many)
- remove per-event `summary` to avoid duplication
"""
import json
import os
import shutil
from datetime import datetime
from komento_koodit import data_store

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SCAN_PATH = os.path.join(ROOT, 'CAPACITY_SCAN_RESULTS.json')
BACKUP_PATH = SCAN_PATH + '.bak.' + datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
CANONICAL_PATH = os.path.join(ROOT, 'class_definitions.json')


def load_scan(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_canonical(defs_by_event):
    canon = {}
    for summary in defs_by_event:
        if not isinstance(summary, dict):
            continue
        for code, info in summary.items():
            if not code:
                continue
            if code in canon:
                # prefer values with display_name/rating_limit present
                for k in ('display_name', 'rating_limit', 'name'):
                    if k in info and info.get(k) and not canon[code].get(k):
                        canon[code][k] = info.get(k)
            else:
                canon[code] = {
                    'code': info.get('code') or code,
                    'name': info.get('name') or info.get('display_name') or code,
                    'display_name': info.get('display_name') or info.get('name') or code,
                    'rating_limit': info.get('rating_limit') if 'rating_limit' in info else None,
                }
    return canon


def prune_counts(ccnts):
    if not isinstance(ccnts, dict):
        return {}
    vals = list(ccnts.values())
    if not vals:
        return {}
    # If every count == 1 and there are many distinct classes, treat as spurious
    if all((v == 1 for v in vals)) and len(vals) >= 4:
        return {}
    # otherwise keep only >0 counts
    return {k: int(v) for k, v in ccnts.items() if v is not None and int(v) > 0}


def main():
    # load scan from sqlite-backed store (fallback to file)
    data = data_store.load_category(os.path.basename(SCAN_PATH))
    if not data:
        print('No CAPACITY_SCAN_RESULTS.json found')
        return
    print('Backing up scan data to', BACKUP_PATH)
    # write backup as file copy for safety
    with open(BACKUP_PATH, 'w', encoding='utf-8') as bf:
        json.dump(data, bf, ensure_ascii=False, indent=2)

    # collect all summaries
    summaries = []
    for rec in data:
        ci = rec.get('class_info') or {}
        summary = ci.get('summary') if isinstance(ci, dict) else None
        if isinstance(summary, dict) and summary:
            summaries.append(summary)

    canonical = build_canonical(summaries)
    if canonical:
        print('Writing canonical class definitions to', CANONICAL_PATH)
        data_store.save_category(os.path.basename(CANONICAL_PATH), canonical)
    else:
        print('No canonical summaries found; skipping canonical file')

    # rewrite per-event records
    for rec in data:
        ci = rec.get('class_info') or {}
        if isinstance(ci, dict):
            # prune counts
            ccnts = ci.get('class_counts') or {}
            new_cc = prune_counts(ccnts)
            rec['class_info']['class_counts'] = new_cc
            # remove summary to avoid duplication
            if 'summary' in rec['class_info']:
                rec['class_info']['summary'] = {}
        # also ensure capacity_result.class_info cleaned
        crec = rec.get('capacity_result') or {}
        if isinstance(crec, dict) and 'class_info' in crec and isinstance(crec['class_info'], dict):
            crec['class_info']['class_counts'] = prune_counts(crec['class_info'].get('class_counts') or {})
            crec['class_info']['summary'] = {}

    print('Writing cleaned', SCAN_PATH)
    data_store.save_category(os.path.basename(SCAN_PATH), data)
    print('Migration complete.')


if __name__ == '__main__':
    main()
