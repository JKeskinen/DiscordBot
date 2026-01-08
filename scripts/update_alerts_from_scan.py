import os
import json
import re
from datetime import datetime
from komento_koodit import data_store

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SCAN = os.path.join(BASE, 'CAPACITY_SCAN_RESULTS.json')
ALERTS = os.path.join(BASE, 'CAPACITY_ALERTS.json')

# Prosenttipohjaiset hälytyskynnykset: kun paikkoja on jäljellä
# enintään 50 %, 25 %, 10 % tai 5 % kokonaiskapasiteetista.
THRESHOLDS_PERCENT = (50, 25, 10, 5)


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
    # load scan results from sqlite-backed store (fallback to file)
    data = data_store.load_category(os.path.basename(SCAN))
    if not data:
        print('Ei kapasiteettiskannauksen tuloksia tiedostossa', SCAN)
        return

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
        if dt is not None and dt.date() < today.date():
            is_past = True

        if is_past and dt is not None:
            year = dt.year
            hist_name = f'HISTORY_{year}.json'
            hist_path = os.path.join(BASE, hist_name)
            archived.setdefault(hist_path, []).append(item)
            # do not include in remaining_scan
            continue

        # keep item in scan results
        remaining_scan.append(item)

        # only raise alerts when remaining and limit are known and there is
        # at least one paikka jäljellä.
        if isinstance(rem, int) and lim is not None and isinstance(lim, int):
            if rem > 0 and not skip_due_to_queue and lim > 0:
                # Laske montako prosenttia paikkoja on jäljellä.
                try:
                    percent_left = (rem / float(lim)) * 100.0
                except Exception:
                    percent_left = None

                if percent_left is not None:
                    # Määritä "tasokynnys": 50 %, 25 %, 10 % tai 5 %.
                    level = None
                    if percent_left <= 5:
                        level = 5
                    elif percent_left <= 10:
                        level = 10
                    elif percent_left <= 25:
                        level = 25
                    elif percent_left <= 50:
                        level = 50

                    if level is not None:
                        alerts.append({
                            'id': item.get('id'),
                            'title': item.get('name') or item.get('title'),
                            'url': item.get('url'),
                            'registered': cap.get('registered'),
                            'limit': cap.get('limit'),
                            'remaining': rem,
                            'remaining_percent': round(percent_left, 1),
                            'level': level,
                            'note': cap.get('note')
                        })
        else:
            # previously we alerted on 'no visible limit'; skip these now
            pass

    # write alerts
    data_store.save_category(os.path.basename(ALERTS), alerts)
    try:
        print('Kirjoitettiin', len(alerts), 'kapasiteetti-ilmoitusta sqlite:', os.path.splitext(os.path.basename(ALERTS))[0])
    except Exception:
        print('Kirjoitettiin', len(alerts), 'kapasiteetti-ilmoitusta')

    # write updated scan results (excluding archived)
    data_store.save_category(os.path.basename(SCAN), remaining_scan)
    try:
        print('Päivitettiin kapasiteettiskannauksen tulokset sqlite:', os.path.splitext(os.path.basename(SCAN))[0], '; rivejä jäljellä:', len(remaining_scan))
    except Exception:
        print('Päivitettiin kapasiteettiskannauksen tulokset; rivejä jäljellä:', len(remaining_scan))

    # append archived items to per-year history files
    for path, items in archived.items():
        # `path` was originally a filesystem path; convert to basename for DB key
        hist_name = os.path.basename(path)
        existing = data_store.load_category(hist_name) or []
        existing.extend(items)
        data_store.save_category(hist_name, existing)
        try:
            print('Arkistoitiin', len(items), 'tapahtumaa historioihin sqlite:', hist_name)
        except Exception:
            print('Arkistoitiin', len(items), 'tapahtumaa historioihin', hist_name)


if __name__ == '__main__':
    main()
