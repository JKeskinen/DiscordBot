import json
import os
import sys
import pathlib
import textwrap

# Ensure project root is on sys.path so we can import package modules when
# this script is executed from the project root or from inside the package dir.
ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from komento_koodit import post_pending_registration as ppr

# Use test thread to avoid spamming production
thread = getattr(ppr, 'TEST_THREAD', None) or os.environ.get('DISCORD_TEST_THREAD')
if not thread:
    print('No TEST_THREAD configured; aborting')
    exit(1)

pending = ppr.load_pending()
if not pending:
    print('No pending items')
    exit(0)

# Build debug entries: one embed per item, truncate long values to avoid
# exceeding Discord embed size limits.
embeds = []
for idx, it in enumerate(pending, 1):
    title = f"DEBUG: {it.get('id') or it.get('name') or idx}"
    lines = []
    for k in sorted(it.keys()):
        try:
            v = it.get(k)
            if isinstance(v, (dict, list)):
                txt = json.dumps(v, ensure_ascii=False)
            else:
                txt = str(v)
            if len(txt) > 250:
                txt = txt[:250] + '...'
            lines.append(f'{k}: {txt}')
        except Exception:
            lines.append(f'{k}: <error>')
    # capacity cache
    try:
        url = it.get('url') or str(it.get('id') or '')
        cap = ppr.CAPACITY_CACHE.get(url) or ppr.CAPACITY_CACHE.get(str(it.get('id')))
        cap_txt = json.dumps(cap, ensure_ascii=False) if cap is not None else 'None'
        if len(cap_txt) > 250:
            cap_txt = cap_txt[:250] + '...'
        lines.append(f'capacity_cache: {cap_txt}')
    except Exception:
        lines.append('capacity_cache: <error>')

    desc = '\n'.join(lines)
    if len(desc) > 3500:
        desc = desc[:3500] + '\n... (truncated)'
    embeds.append({'title': title, 'description': desc, 'color': 0x888888})

# Post via existing helper
print('Posting', len(embeds), 'debug embeds to', thread)
def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

success = True
for batch in chunks(embeds, 10):
    ok = ppr.post_embeds(thread, batch)
    if not ok:
        print('Failed to post one batch of embeds')
        success = False
    else:
        print(f'Posted batch of {len(batch)} embeds')

if success:
    print('Posted all debug variables')
else:
    print('Some batches failed')
