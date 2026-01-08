import sys
import pathlib
import sys
from datetime import datetime, timedelta

# ensure project root on path
ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from komento_koodit import post_pending_registration as ppr


def _parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    fmt_candidates = [
        '%d.%m.%Y %H:%M', '%d.%m.%Y', '%Y-%m-%d %H:%M', '%Y-%m-%d',
        '%m/%d/%y %H:%M', '%m/%d/%y', '%m/%d/%Y %H:%M', '%m/%d/%Y',
        '%d/%m/%Y %H:%M', '%d/%m/%Y', '%d.%m.%y %H:%M', '%d.%m.%y'
    ]
    for f in fmt_candidates:
        try:
            return datetime.strptime(s, f)
        except Exception:
            continue
    # try to extract numeric tokens
    try:
        toks = [t for t in s.replace('-', ' ').replace('/', ' ').replace('.', ' ').split() if any(c.isdigit() for c in t)]
        if not toks:
            return None
        parts = toks[0].split()
    except Exception:
        return None
    # fallback: try dd mm yyyy in any order
    nums = [int(''.join([c for c in t if c.isdigit()])) for t in s.replace('/', ' ').replace('.', ' ').replace('-', ' ').split() if any(c.isdigit() for c in t)]
    if len(nums) >= 3:
        # heuristic: if first >31 then probably year-first
        a, b, c = nums[0], nums[1], nums[2]
        try:
            if a > 31:
                year, month, day = a, b, c
            else:
                day, month, year = a, b, c
            if year < 100:
                year += 2000
            return datetime(year, month, day)
        except Exception:
            return None
    return None


def build_opening_soon_embed(item, open_date: datetime):
    name = item.get('name') or item.get('title') or item.get('id')
    date_str = open_date.strftime('%d.%m.%Y')
    lines = []
    lines.append(f'Ilmoittautuminen aukeaa: {date_str}')
    # capacity
    url = item.get('url') or ''
    cap = ppr.CAPACITY_CACHE.get(url) or ppr.CAPACITY_CACHE.get(str(item.get('id')))
    if isinstance(cap, dict):
        reg = cap.get('registered')
        lim = cap.get('limit')
        if reg is not None and lim is not None:
            lines.append(f'{reg}/{lim} paikkoja')
        elif lim is not None:
            lines.append(f'0/{lim} paikkoja')
    # link
    if url:
        lines.append(f'Linkki: {url}')

    desc = '\n'.join(lines)
    embed = {'title': f'{name} rekisteröinti aukeaa pian.', 'description': desc, 'color': 16750848}
    return embed


def main(days_window=7):
    now = datetime.now()
    pending = ppr.load_pending()
    to_post = []
    for it in pending:
        # skip if already open
        if it.get('registration_open'):
            continue
        # skip if we've already posted opening-soon for this item
        if it.get('opening_soon_posted'):
            continue
        # prefer explicit opens_on field or 'opens_on', 'opens'
        opens_raw = it.get('opens_on') or it.get('opens') or it.get('opens_on_date') or it.get('opening_date') or it.get('starts') or it.get('date')
        open_dt = _parse_date(opens_raw)
        if open_dt is None:
            continue
        delta = (open_dt.date() - now.date()).days
        # Only consider items opening within window
        if not (0 < delta <= days_window):
            continue
        # Only post when today's weekday equals the competition's weekday
        try:
            if open_dt.weekday() != now.weekday():
                continue
        except Exception:
            pass
        to_post.append((it, open_dt))

    if not to_post:
        print('No competitions opening within', days_window, 'days')
        return

    embeds = [build_opening_soon_embed(it, odt) for it, odt in to_post]
    # Post each embed (batch size small)
    print('Posting', len(embeds), 'opening-soon embeds to', ppr.TEST_THREAD)
    ok = ppr.post_embeds(ppr.TEST_THREAD, embeds)
    if ok:
        print('Posted opening-soon embeds')
        # mark items as posted in the pending file so we don't repost
        try:
            import json
            pending_path = ppr.PENDING_PATH
            with open(pending_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            modified = False
            for it, odt in to_post:
                for rec in raw:
                    if str(rec.get('id')) == str(it.get('id')) or str(rec.get('url')) == str(it.get('url')):
                        rec['opening_soon_posted'] = True
                        modified = True
            if modified:
                with open(pending_path, 'w', encoding='utf-8') as f:
                    json.dump(raw, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print('Failed to mark opening-soon posted in pending file:', e)
    else:
        print('Failed to post opening-soon embeds')


if __name__ == '__main__':
    main()
