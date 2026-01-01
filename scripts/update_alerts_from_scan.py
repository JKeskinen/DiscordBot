import os
import json
import re
from datetime import datetime

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SCAN = os.path.join(BASE, 'CAPACITY_SCAN_RESULTS.json')
ALERTS = os.path.join(BASE, 'CAPACITY_ALERTS.json')
THRESHOLD = int(os.environ.get('CAPACITY_ALERT_THRESHOLD', '20'))


def parse_date_from_item(item):
    # try common fields
    for key in ('date', 'start_date', 'start'):
        val = item.get(key) or (item.get('capacity_result') or {}).get(key)
        if not val:
            continue
        try:
            # ISO format
            return datetime.fromisoformat(val)
        except Exception:
            pass
        # try dd.mm.yyyy
        m = re.search(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})', str(val))
        if m:
            d = int(m.group(1)); mo = int(m.group(2)); y = int(m.group(3))
            if y < 100:
                y += 2000
            try:
                return datetime(y, mo, d)
            except Exception:
                pass
    # try to parse date from name/title
    for fld in ('name', 'title'):
        txt = item.get(fld) or ''
        m = re.search(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})', txt)
        if m:
            d = int(m.group(1)); mo = int(m.group(2)); y = int(m.group(3))
            if y < 100:
                y += 2000
            try:
                return datetime(y, mo, d)
            except Exception:
                pass
    return None


def main():
    if not os.path.exists(SCAN):
        print('No scan results at', SCAN)
        return
    with open(SCAN, 'r', encoding='utf-8') as f:
        data = json.load(f)

    alerts = []
    remaining_scan = []
    archived = {}
    today = datetime.now()

    for item in data:
        cap = item.get('capacity_result') or {}
        rem = cap.get('remaining')
        lim = cap.get('limit')
        queued = cap.get('queued') or 0
        skip_due_to_queue = isinstance(queued, int) and queued >= 1

        # determine if this event is in the past (archive)
        dt = parse_date_from_item(item)
        is_past = False
        if dt:
            if dt.date() < today.date():
                is_past = True

        if is_past:
            year = dt.year
            hist_name = f'HISTORY_{year}.json'
            hist_path = os.path.join(BASE, hist_name)
            archived.setdefault(hist_path, []).append(item)
            # do not include in remaining_scan
            continue

        # keep item in scan results
        remaining_scan.append(item)

        # only raise alerts when remaining is known, limit exists,
        # and remaining is between 1 and the configured threshold
        if isinstance(rem, int) and lim is not None and isinstance(lim, int):
            if rem > 0 and rem <= THRESHOLD and not skip_due_to_queue:
                alerts.append({
                    'id': item.get('id'),
                    'title': item.get('name') or item.get('title'),
                    'url': item.get('url'),
                    'registered': cap.get('registered'),
                    'limit': cap.get('limit'),
                    'remaining': rem,
                    'note': cap.get('note')
                })
        else:
            # previously we alerted on 'no visible limit'; skip these now
            pass

    # write alerts
    with open(ALERTS, 'w', encoding='utf-8') as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)
    print('Wrote', len(alerts), 'alerts to', ALERTS)

    # write updated scan results (excluding archived)
    with open(SCAN, 'w', encoding='utf-8') as f:
        json.dump(remaining_scan, f, ensure_ascii=False, indent=2)
    print('Updated scan results; remaining entries:', len(remaining_scan))

    # append archived items to per-year history files
    for path, items in archived.items():
        existing = []
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    existing = json.load(f) or []
            except Exception:
                existing = []
        existing.extend(items)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print('Archived', len(items), 'items to', path)


if __name__ == '__main__':
    main()
