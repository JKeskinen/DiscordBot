import os
import json
import requests
import pathlib


def _load_dotenv(path='.env'):
    p = pathlib.Path(path)
    if not p.exists():
        return
    try:
        with p.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"\'"')
                os.environ.setdefault(k, v)
    except Exception:
        pass

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PENDING_PATH = os.path.join(BASE_DIR, 'pending_registration.json')
KNOWN_PDGA = os.path.join(BASE_DIR, 'known_pdga_competitions.json')
KNOWN_WEEKLY = os.path.join(BASE_DIR, 'known_weekly_competitions.json')

_load_dotenv()
TOKEN = os.environ.get('DISCORD_TOKEN')

# Testikanava, johon kaikki rekisteröinti-ilmoitukset ohjataan oletuksena.
TEST_THREAD = os.environ.get('DISCORD_TEST_THREAD') or os.environ.get('DISCORD_TEST_CHANNEL_ID') or '1456702993377267905'

# Threads: PDGA and WEEKLY (viikkarit+doubles)
# Ympäristömuuttujilla (DISCORD_PDGA_THREAD / DISCORD_WEEKLY_THREAD) voi myöhemmin ohjata
# tuotantokanaville, mutta ilman niitä kaikki menee testikanavaan.
PDGA_THREAD = os.environ.get('DISCORD_PDGA_THREAD') or os.environ.get('DISCORD_THREAD_ID') or TEST_THREAD
WEEKLY_THREAD = os.environ.get('DISCORD_WEEKLY_THREAD') or os.environ.get('DISCORD_WEEKLY_THREAD_ID') or TEST_THREAD

HEADERS = {'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'}

MAX_ITEMS_PER_EMBED = 12


def load_pending():
    try:
        with open(PENDING_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print('Failed to load pending_registration.json:', e)
        return []


def chunk(items, n):
    for i in range(0, len(items), n):
        yield items[i:i+n]


def build_embeds(items):
    # Deprecated: kept for compatibility but prefer build_embeds_with_title below
    return build_embeds_with_title(items, f"REKISTERÖINTI AVOINNA ({len(items)})", 16753920)


def build_embeds_with_title(items, title, color):
    embeds = []
    if not items:
        embeds.append({'title': title, 'description': '(ei ilmoituksia)', 'color': color})
        return embeds
    first_title = title
    for part in chunk(items, MAX_ITEMS_PER_EMBED):
        lines = []
        for it in part:
            name = it.get('name') or it.get('title') or it.get('id')
            # If name contains a parent prefix like 'Parent → Child', display only the child
            try:
                if '→' in name:
                    name = name.split('→')[-1].strip()
            except Exception:
                pass
            url = it.get('url') or ''
            extra = ''
            # include opens_in_days if present for 'opening soon' items
            if it.get('opens_in_days') is not None and not it.get('registration_open'):
                try:
                    d = int(it.get('opens_in_days'))
                    if d > 0:
                        extra = f" — avautuu {d} pv"  # Finnish: opens in X days
                except Exception:
                    pass
            if url:
                lines.append(f"• [{name}]({url}){extra}")
            else:
                lines.append(f"• {name}{extra}")
        embed = {'title': first_title, 'description': '\n'.join(lines), 'color': color}
        embeds.append(embed)
        first_title = ' '
    return embeds


def load_known(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            keys = set()
            for x in data:
                try:
                    if isinstance(x, dict):
                        k = x.get('id') or x.get('url') or x.get('name') or x.get('title')
                        if k is None:
                            # fallback to full dict string
                            keys.add(str(x))
                        else:
                            keys.add(str(k))
                    else:
                        keys.add(str(x))
                except Exception:
                    try:
                        keys.add(str(x))
                    except Exception:
                        continue
            return keys
    except Exception:
        return set()


def save_known(path, ids):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(list(ids), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('Failed to save known ids to', path, e)


def post_embeds(thread_id, embeds):
    if not TOKEN:
        print('DISCORD_TOKEN not set; cannot post')
        return False
    url = f'https://discord.com/api/v10/channels/{thread_id}/messages'
    payload = {'embeds': embeds}
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=15)
        if r.status_code in (200, 201):
            print('Posted embeds to Discord thread', thread_id)
            return True
        else:
            print('Discord post failed:', r.status_code, r.text[:400])
            return False
    except Exception as e:
        print('Exception posting to Discord:', e)
        return False


if __name__ == '__main__':
    pending = load_pending()
    if not pending:
        print('No open registrations found; nothing to post')
        exit(0)

    # Partition pending items into PDGA vs weekly/doubles
    pdga = []
    weekly = []
    for it in pending:
        kind = (it.get('kind') or it.get('tier') or '').upper()
        if 'PDGA' in kind:
            pdga.append(it)
        else:
            # treat non-PDGA as weekly/doubles
            weekly.append(it)

    # Load known caches
    known_pdga = load_known(KNOWN_PDGA)
    known_weekly = load_known(KNOWN_WEEKLY)

    # Determine new items
    pdga_ids = [str(it.get('id') or it.get('url') or it.get('name')) for it in pdga]
    weekly_ids = [str(it.get('id') or it.get('url') or it.get('name')) for it in weekly]

    new_pdga = [it for it in pdga if str(it.get('id') or it.get('url') or it.get('name')) not in known_pdga]
    new_weekly = [it for it in weekly if str(it.get('id') or it.get('url') or it.get('name')) not in known_weekly]

    # Posting logic: if known cache empty -> initial long post (post all); otherwise post only new items
    # PDGA
    to_post_pdga = pdga if not known_pdga else new_pdga
    if to_post_pdga:
        # split into currently open and opening soon
        pdga_open = [it for it in to_post_pdga if it.get('registration_open')]
        pdga_soon = [it for it in to_post_pdga if (not it.get('registration_open')) and it.get('opening_soon')]

        # Post open now
        if pdga_open:
            embeds = build_embeds_with_title(pdga_open, f"REKISTERÖINTI AVOINNA ({len(pdga_open)})", 5763714)
            if post_embeds(PDGA_THREAD, embeds):
                print(f'Posted PDGA open now: {len(pdga_open)} items')
            else:
                print('Failed to post PDGA open-now embeds')

        # Post opening soon
        if pdga_soon:
            embeds = build_embeds_with_title(pdga_soon, f"REKISTERÖINTI AVAUTUU PIAN ({len(pdga_soon)})", 16750848)
            if post_embeds(PDGA_THREAD, embeds):
                print(f'Posted PDGA opening soon: {len(pdga_soon)} items')
            else:
                print('Failed to post PDGA opening-soon embeds')

        # update known ids after posting both lists
        known_pdga.update(pdga_ids)
        save_known(KNOWN_PDGA, known_pdga)
    else:
        print('No new PDGA items to post')

    # Weekly + doubles
    to_post_weekly = weekly if not known_weekly else new_weekly
    if to_post_weekly:
        weekly_open = [it for it in to_post_weekly if it.get('registration_open')]
        weekly_soon = [it for it in to_post_weekly if (not it.get('registration_open')) and it.get('opening_soon')]

        if weekly_open:
            embeds = build_embeds_with_title(weekly_open, f"REKISTERÖINTI AVOINNA ({len(weekly_open)})", 5763714)
            if post_embeds(WEEKLY_THREAD, embeds):
                print(f'Posted weekly open now: {len(weekly_open)} items')
            else:
                print('Failed to post weekly open-now embeds')

        if weekly_soon:
            embeds = build_embeds_with_title(weekly_soon, f"REKISTERÖINTI AVAUTUU PIAN ({len(weekly_soon)})", 16750848)
            if post_embeds(WEEKLY_THREAD, embeds):
                print(f'Posted weekly opening soon: {len(weekly_soon)} items')
            else:
                print('Failed to post weekly opening-soon embeds')

        known_weekly.update(weekly_ids)
        save_known(KNOWN_WEEKLY, known_weekly)
    else:
        print('No new weekly/doubles items to post')
