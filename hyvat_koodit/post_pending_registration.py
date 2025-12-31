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
# Threads: PDGA and WEEKLY (viikkarit+doubles)
PDGA_THREAD = os.environ.get('DISCORD_PDGA_THREAD') or os.environ.get('DISCORD_THREAD_ID') or '1455713091970142270'
WEEKLY_THREAD = os.environ.get('DISCORD_WEEKLY_THREAD') or os.environ.get('DISCORD_WEEKLY_THREAD_ID') or '1455713153127026889'

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
    embeds = []
    total = len(items)
    title = f"REKISTERÖINTI AVOINNA ({total})"
    color = 16753920
    if total == 0:
        embeds.append({'title': title, 'description': '(ei avoimia ilmoittautumisia)', 'color': color})
        return embeds
    for part in chunk(items, MAX_ITEMS_PER_EMBED):
        lines = []
        for it in part:
            name = it.get('name') or it.get('title') or it.get('id')
            url = it.get('url') or ''
            if url:
                lines.append(f"• [{name}]({url})")
            else:
                lines.append(f"• {name}")
        embed = {'title': title, 'description': '\n'.join(lines), 'color': color}
        embeds.append(embed)
        # after the first embed, shorten title to avoid repetition
        title = ' '  # small blank title for subsequent embeds
    return embeds


def load_known(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set([str(x) for x in data])
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
        embeds = build_embeds(to_post_pdga)
        if post_embeds(PDGA_THREAD, embeds):
            # update known ids
            known_pdga.update(pdga_ids)
            save_known(KNOWN_PDGA, known_pdga)
            print(f'Posted PDGA: {len(to_post_pdga)} items')
        else:
            print('Failed to post PDGA embeds')
    else:
        print('No new PDGA items to post')

    # Weekly + doubles
    to_post_weekly = weekly if not known_weekly else new_weekly
    if to_post_weekly:
        embeds = build_embeds(to_post_weekly)
        if post_embeds(WEEKLY_THREAD, embeds):
            known_weekly.update(weekly_ids)
            save_known(KNOWN_WEEKLY, known_weekly)
            print(f'Posted weekly/doubles: {len(to_post_weekly)} items')
        else:
            print('Failed to post weekly embeds')
    else:
        print('No new weekly/doubles items to post')
