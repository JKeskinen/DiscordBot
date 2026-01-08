import json
import re
from datetime import datetime
from komento_koodit import data_store


def load_pdga(path='PDGA.json'):
    data = data_store.load_category(path)
    return data if isinstance(data, list) else data.get('competitions', data.get('items', []))

def is_pdga_container(item, all_items):
    title = (item.get('name') or item.get('title') or '').strip()
    if not title:
        return False
    # Only treat as container when this is a top-level title (no '→')
    # and there are items that start with "title → ..." (i.e. date-specific children).
    if '→' not in title:
        prefix = f"{title} → "
        for other in all_items:
            if other is item:
                continue
            ot = (other.get('name') or other.get('title') or '').strip()
            if ot.startswith(prefix):
                return True
    date_txt = str(item.get('date') or '')
    if '-' in date_txt:
        parts_dt = [p.strip() for p in date_txt.split('-')]
        if len(parts_dt) == 2 and parts_dt[0] and parts_dt[1] and parts_dt[0] != parts_dt[1]:
            return True
    return False

def normalize_pdga_rounds(lst):
    by_base = {}
    for item in lst:
        title = (item.get('name') or item.get('title') or '').strip()
        if not title:
            by_base.setdefault('', []).append(item)
            continue
        parts = [p.strip() for p in title.split('→')]
        last = parts[-1].lower() if parts else ''
        if 'kierros' in last:
            base_key = ' → '.join(parts[:-1]).strip()
            if not base_key:
                base_key = title
            by_base.setdefault(base_key, []).append(item)
        else:
            base_key = title
            by_base.setdefault(base_key, []).append(item)

    normalized = []
    for base, items in by_base.items():
        if len(items) == 1:
            normalized.append(items[0])
            continue
        non_round = [it for it in items if 'kierros' not in ((it.get('name') or it.get('title') or '').lower())]
        if non_round:
            normalized.append(non_round[0])
            continue
        one_round = None
        for it in items:
            t = (it.get('name') or it.get('title') or '').lower()
            if re.search(r'\b1\.?\s*kierros\b', t):
                one_round = it
                break
        if one_round:
            normalized.append(one_round)
            continue

        def _extract_date_from_title(it):
            t = (it.get('name') or it.get('title') or '')
            m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{2,4})", t)
            if m:
                try:
                    parts = m.group(1).split('.')
                    d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
                    if y < 100:
                        y += 2000
                    return datetime(y, mo, d)
                except Exception:
                    return None
            return None

        items_with_dates = [(it, _extract_date_from_title(it)) for it in items]
        items_with_dates = sorted(items_with_dates, key=lambda x: (x[1] is None, x[1] or datetime.max))
        normalized.append(items_with_dates[0][0])

    # preserve original order as much as possible
    seen = set()
    final = []
    for it in lst:
        if it in normalized and id(it) not in seen:
            final.append(it); seen.add(id(it))
    for it in normalized:
        if id(it) not in seen:
            final.append(it)
    return final

def main():
    all_items = load_pdga()
    pdga_display_list = [c for c in all_items if not is_pdga_container(c, all_items)]
    norm = normalize_pdga_rounds(pdga_display_list)
    print('Normalized PDGA list (name | date):')
    for it in norm:
        name = it.get('name') or it.get('title') or ''
        date = it.get('date') or ''
        # remove leading bullet and container prefix like "Luoma-ahon Lauantai Liiga → "
        name = name.strip()
        name = re.sub(r'^\s*•\s*', '', name)  # strip leading bullet
        # strip any leading text up to the first arrow (handles '→' and '->')
        name = re.sub(r'^(?:.*?)(?:→|->)\s*', '', name, count=1).strip()
        print('- ', name, '|', date)

if __name__ == '__main__':
    main()
