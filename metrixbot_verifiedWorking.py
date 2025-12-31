import os
import json
import time
import threading
import requests
import logging
import re

# Module base dir
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Configure structured logging similar to discord.py examples
LOG_FMT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
# Keep discord related loggers at INFO level
logging.getLogger('discord').setLevel(logging.INFO)
logging.getLogger('discord.client').setLevel(logging.INFO)
logging.getLogger('discord.gateway').setLevel(logging.INFO)

# Load .env if present (optional helper from original)
try:
    # Pylance may report missing import if python-dotenv isn't installed in the analysis
    # environment; silence the analyzer while still attempting to load at runtime.
    from dotenv import load_dotenv  # type: ignore[reportMissingImports]
    load_dotenv()
except Exception:
    # if python-dotenv not installed, ignore at runtime
    pass

# Configuration copied from metrixbot.py
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

# Primary channel and thread IDs (fall back to env overrides)
DISCORD_CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "1241453177979797584"))
DISCORD_THREAD_ID = int(os.environ.get("DISCORD_THREAD_ID", "1241493648080764988"))
DISCORD_WEEKLY_THREAD_ID = int(os.environ.get("DISCORD_WEEKLY_THREAD_ID", "1455647584583417889"))

WEEKLY_JSON = os.environ.get("WEEKLY_JSON", "weekly_pair.json")
WEEKLY_LOCATION = os.environ.get("WEEKLY_LOCATION", "Etelä-Pohjanmaa").strip().lower()
WEEKLY_RADIUS_KM = int(os.environ.get("WEEKLY_RADIUS_KM", "100"))
WEEKLY_SEARCH_URL = os.environ.get("WEEKLY_SEARCH_URL", "https://discgolfmetrix.com/?u=competitions_all&view=1&competition_name=&period=&date1=2026-01-01&date2=2027-01-01&my_country=&registration_open=&registration_date1=&registration_date2=&country_code=FI&my_club=0&club_type=&club_id=&association_id=0&close_to_me=&area=Etelä-Pohjanmaa&city=&course_id=&division=&my=&view=1&sort_name=&sort_order=&my_all=&from=1&to=30")

METRIX_URL = os.environ.get("METRIX_URL", "https://discgolfmetrix.com/?u=competitions_all&view=2&competition_name=&period=&date1=2026-01-01&date2=2027-01-01&my_country=&registration_open=&registration_date1=&registration_date2=&country_code=FI&my_club=&club_type=&club_id=&association_id=0&close_to_me=&area=&city=&course_id=&type=C&division=&my=&view=2&sort_name=&sort_order=&my_all=")

AUTO_LIST_INTERVAL = int(os.environ.get('AUTO_LIST_INTERVAL', '86400'))
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '600'))
CHECK_REGISTRATION_INTERVAL = int(os.environ.get('CHECK_REGISTRATION_INTERVAL', '3600'))

CACHE_FILE = os.environ.get('CACHE_FILE', 'known_pdga_competitions.json')
REG_CHECK_FILE = os.environ.get('REG_CHECK_FILE', 'pending_registration.json')
KNOWN_WEEKLY_FILE = os.environ.get('KNOWN_WEEKLY_FILE', 'known_weekly_competitions.json')
KNOWN_DOUBLES_FILE = os.environ.get('KNOWN_DOUBLES_FILE', 'known_doubles_competitions.json')

# -------------------------
# Discord message formatting options
# You can tweak these values here or set equivalent env vars to change behaviour.
# - To remove dates from messages, set DISCORD_SHOW_DATE=0
# - To change date output to DDMMYYYY, set DISCORD_DATE_FORMAT=DDMMYYYY
# - To show/hide raw IDs, set DISCORD_SHOW_ID=1 or 0
# - To show/hide location, set DISCORD_SHOW_LOCATION=1 or 0
# - To increase spacing between lines in messages, set DISCORD_LINE_SPACING to 1 (single), 2 (double), etc.
# Note: Discord does not support changing font size. Use spacing, bold or emojis to increase visual weight.
# -------------------------
DISCORD_SHOW_DATE = os.environ.get('DISCORD_SHOW_DATE', '1') == '1'
DISCORD_DATE_FORMAT = os.environ.get('DISCORD_DATE_FORMAT', 'DD.MM.YYYY')  # or 'original'
DISCORD_SHOW_ID = os.environ.get('DISCORD_SHOW_ID', '0') == '1'
DISCORD_SHOW_LOCATION = os.environ.get('DISCORD_SHOW_LOCATION', '0') == '1'
DISCORD_LINE_SPACING = max(1, int(os.environ.get('DISCORD_LINE_SPACING', '1')))

def _format_date_field(raw_date: str) -> str:
    """Try to extract a date like DD/MM/YY or DD/MM/YYYY from raw_date and format it.
    Supported DISCORD_DATE_FORMAT: 'DDMMYYYY' or 'original'. Returns empty string if no date found.
    """
    if not raw_date:
        return ''
    # Find first date-like occurrence
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', raw_date)
    if not m:
        return '' if DISCORD_DATE_FORMAT == 'DDMMYYYY' else raw_date
    d, mo, y = m.groups()
    if len(y) == 2:
        y = '20' + y
    d = d.zfill(2); mo = mo.zfill(2)
    if DISCORD_DATE_FORMAT == 'DDMMYYYY':
        return f"{d}{mo}{y}"
    return f"{d}/{mo}/{y}"


def _load_dotenv(path='.env'):
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())


def post_to_discord(thread_id: str, token: str, content: str) -> bool:
    if not token or not thread_id:
        print('Discord token or thread id missing; skipping post')
        return False
    url = f'https://discord.com/api/v10/channels/{thread_id}/messages'
    headers = {'Authorization': f'Bot {token}', 'Content-Type': 'application/json'}
    payload = {'content': content}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code in (200, 201):
            print('Posted summary to Discord thread', thread_id)
            return True
        else:
            print('Discord post failed:', r.status_code, r.text[:200])
            return False
    except Exception as e:
        print('Discord post exception:', e)
        return False


def post_embeds_to_discord(thread_id: str, token: str, embeds: list) -> bool:
    """Post embeds array to a channel/thread. Falls back to text if embeds are rejected."""
    if not token or not thread_id:
        print('Discord token or thread id missing; skipping post')
        return False
    url = f'https://discord.com/api/v10/channels/{thread_id}/messages'
    headers = {'Authorization': f'Bot {token}', 'Content-Type': 'application/json'}
    payload = {'embeds': embeds}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code in (200, 201):
            print('Posted embeds to Discord thread', thread_id)
            return True
        else:
            print('Embed post failed, status', r.status_code, r.text[:200])
            # fallback: try to post plain text combining embed descriptions
            try:
                combined = []
                for e in embeds:
                    title = e.get('title', '')
                    desc = e.get('description', '')
                    combined.append(f"**{title}**\n{desc}")
                return post_to_discord(thread_id, token, "\n\n".join(combined))
            except Exception:
                return False
    except Exception as e:
        print('Discord embed post exception:', e)
        return False


def run_once():
    _load_dotenv()
    # Import modules from hyvat_koodit
    import hyvat_koodit.search_pdga_sfl as pdga_mod
    # Importing weekly module executes it and writes VIIKKOKISA.json
    import hyvat_koodit.search_weekly_fast as weekly_mod
    import hyvat_koodit.search_pari_EP2025 as pari_mod

    base_dir = os.path.abspath(os.path.dirname(__file__))

    # PDGA: fetch competitions and save PDGA.json
    try:
        comps = pdga_mod.fetch_competitions(pdga_mod.DEFAULT_URL)
        pdga_entries = [c for c in comps if pdga_mod.is_pdga_entry(c)]
        out_pdga = os.path.join(base_dir, 'PDGA.json')
        pdga_mod.save_pdga_list(pdga_entries, out_pdga)
    except Exception as e:
        print('PDGA step failed:', e)

    # Weekly: module import already attempted to save VIIKKOKISA.json; if not present, try to trigger explicitly
    out_weekly = os.path.join(base_dir, 'VIIKKOKISA.json')
    if not os.path.exists(out_weekly):
        # nothing else to call; inform user
        print('VIIKKOKISA.json not found after import of weekly script')

    # Doubles: call function and save DOUBLES.json
    try:
        doubles = pari_mod.find_doubles()
        pari_mod.save_doubles_list(doubles, os.path.join(base_dir, 'DOUBLES.json'))
    except Exception as e:
        print('Doubles step failed:', e)

    # Summarize outputs
    def _read_json(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    pdga_list = _read_json(os.path.join(base_dir, 'PDGA.json'))
    weekly_list = _read_json(os.path.join(base_dir, 'VIIKKOKISA.json'))
    doubles_list = _read_json(os.path.join(base_dir, 'DOUBLES.json'))

    # Prepare summaries
    pdga_count = len(pdga_list)
    weekly_count = len(weekly_list)
    doubles_count = len(doubles_list)

    def fmt_pdga_list(lst, limit=20):
        lines = []
        for i, c in enumerate(lst[:limit]):
            name = c.get('name') or c.get('title') or ''
            cid = c.get('id') or ''
            date = c.get('date') or ''
            lines.append(f"- {cid} | {name} | {date}")
        if len(lst) > limit:
            lines.append(f"...and {len(lst)-limit} more")
        return '\n'.join(lines) if lines else '(none)'

    def fmt_weekly_and_doubles(weeks, doubles, limit=20):
        lines = []
        for i, c in enumerate(weeks[:limit]):
            # Build a single line for the competition based on configuration flags
            title = c.get('title') or c.get('name') or ''
            raw_date = c.get('date') or ''
            date = _format_date_field(raw_date) if DISCORD_SHOW_DATE else ''
            url = c.get('url') or ''
            location = c.get('location') or ''

            parts = []
            if DISCORD_SHOW_ID:
                cid = c.get('id') or ''
                if cid:
                    parts.append(str(cid))

            # Title (link when URL available)
            if url:
                title_part = f"[{title}]({url})"
            else:
                title_part = title
            parts.append(title_part)

            # Optional location
            if DISCORD_SHOW_LOCATION and location:
                parts.append(location)

            # Optional date (already formatted)
            if date:
                parts.append(date)

            # Join with a readable separator and respect line spacing config
            line = ' — '.join(p for p in parts if p)
            lines.append(f"- {line}")
        if len(weeks) > limit:
            lines.append(f"...and {len(weeks)-limit} more weeklies")
        if doubles:
            lines.append('\nDoubles / pairs:')
            for d in doubles[:limit]:
                title = d.get('title') or d.get('name') or ''
                raw_date = d.get('date') or ''
                date = _format_date_field(raw_date) if DISCORD_SHOW_DATE else ''
                url = d.get('url') or ''
                location = d.get('location') or ''

                parts = []
                if DISCORD_SHOW_ID:
                    cid = d.get('id') or ''
                    if cid:
                        parts.append(str(cid))
                if url:
                    parts.append(f"[{title}]({url})")
                else:
                    parts.append(title)
                if DISCORD_SHOW_LOCATION and location:
                    parts.append(location)
                if date:
                    parts.append(date)
                lines.append(f"- {' — '.join(p for p in parts if p)}")
            if len(doubles) > limit:
                lines.append(f"...and {len(doubles)-limit} more doubles")
        # Respect DISCORD_LINE_SPACING: number of newline characters between lines
        sep = '\n' * DISCORD_LINE_SPACING
        return sep.join(lines) if lines else '(none)'

    print('Run summary:\n' + f"PDGA: {pdga_count}, VIIKKOKISA: {weekly_count}, DOUBLES: {doubles_count}")

    token = os.environ.get('DISCORD_TOKEN')
    pdga_thread = os.environ.get('DISCORD_PDGA_THREAD', '1455713091970142270')
    weekly_thread = os.environ.get('DISCORD_WEEKLY_THREAD', '1455713153127026889')

    if not token:
        print('DISCORD_TOKEN not set; skipping Discord posts')
        return

    # Post PDGA summary using embeds grouped by tier for only newly-discovered competitions
    try:
        def _unique_key(item) -> str:
            # Accept dicts or primitive ids/urls saved previously
            if not item and item != 0:
                return ''
            if isinstance(item, (str, int)):
                return str(item)
            # dict-like
            try:
                if item.get('id'):
                    return str(item.get('id'))
                if item.get('url'):
                    return str(item.get('url'))
                name = item.get('name') or item.get('title') or ''
                date = item.get('date') or ''
                return f"{name}|{date}".strip()
            except Exception:
                return str(item)

        # load known PDGA cache (if present)
        try:
            with open(os.path.join(base_dir, CACHE_FILE), 'r', encoding='utf-8') as f:
                known_pdga = json.load(f) or []
        except Exception:
            known_pdga = []

        known_keys = { _unique_key(x) for x in known_pdga }
        new_pdga = [c for c in pdga_list if _unique_key(c) not in known_keys]

        if new_pdga:
            groups = {}
            for c in new_pdga:
                tier = (c.get('tier') or '').strip() or 'Muut'
                groups.setdefault(tier, []).append(c)

            embeds = []
            for tier, items in sorted(groups.items(), key=lambda x: x[0]):
                t = (tier or '').strip()
                norm = re.sub(r'(?i)\s*[-–—]\s*pdga$', '', t)
                norm = re.sub(r'(?i)\bpdga\b$', '', norm).strip()
                if not norm or norm.lower() == 'muut':
                    title = "Uusia PDGA-kisoja lisätty"
                else:
                    display = norm
                    if len(norm) == 1 and norm.isalpha():
                        display = f"{norm.upper()}-tier"
                    title = f"Uusia {display} kisoja lisätty"
                lines = []
                for it in items[:40]:
                    name = it.get('name') or it.get('title') or ''
                    url = it.get('url') or ''
                    if url:
                        lines.append(f"• [{name}]({url})")
                    else:
                        lines.append(f"• {name}")
                if len(items) > 40:
                    lines.append(f"...and {len(items)-40} more")
                embed = {
                    'title': title,
                    'description': "\n".join(lines) or '(none)',
                    'color': 16750848
                }
                embeds.append(embed)
                if len(embeds) >= 10:
                    break

            if embeds:
                post_embeds_to_discord(pdga_thread, token, embeds)
            else:
                pdga_msg = f"UUSIA PDGA-KILPAILUJA LISÄTTY ({len(new_pdga)})\n\n" + fmt_pdga_list(new_pdga)
                post_to_discord(pdga_thread, token, pdga_msg)
        else:
            print('No new PDGA competitions found; skipping PDGA post')

        # Persist the current list as the known cache (overwrite)
        try:
            with open(os.path.join(base_dir, CACHE_FILE), 'w', encoding='utf-8') as f:
                json.dump(pdga_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print('Failed to update PDGA cache file:', e)
    except Exception as e:
        print('Failed to build/send PDGA embeds:', e)

    # Post weeklies + doubles as a single compact embed (falls back to plain text)
    def build_weekly_embed(weeks, doubles):
        # Friendly title: singular/plural for weeklies, include doubles if present
        if len(weeks) == 1:
            week_part = "Uusi viikkokisa lisätty"
        elif len(weeks) > 1:
            week_part = f"Uusia viikkokisoja lisätty ({len(weeks)})"
        else:
            week_part = None

        double_part = f"Parikisat ({len(doubles)})" if doubles else None

        title = " ja ".join(p for p in (week_part, double_part) if p) or f"VIIKKARIT ({len(weeks)}) ja PARIKISAT ({len(doubles)})"
        lines = []
        for c in weeks:
            title_text = c.get('title') or c.get('name') or ''
            raw_date = c.get('date') or ''
            date = _format_date_field(raw_date) if DISCORD_SHOW_DATE else ''
            url = c.get('url') or ''
            location = c.get('location') or ''

            parts = []
            if DISCORD_SHOW_ID:
                cid = c.get('id') or ''
                if cid:
                    parts.append(str(cid))
            if url:
                parts.append(f"[{title_text}]({url})")
            else:
                parts.append(title_text)
            if DISCORD_SHOW_LOCATION and location:
                parts.append(location)
            if date:
                parts.append(date)

            lines.append(f"• {' — '.join(p for p in parts if p)}")

        if doubles:
            lines.append('')
            lines.append('Parikisat:')
            for d in doubles:
                title_text = d.get('title') or d.get('name') or ''
                raw_date = d.get('date') or ''
                date = _format_date_field(raw_date) if DISCORD_SHOW_DATE else ''
                url = d.get('url') or ''
                location = d.get('location') or ''

                parts = []
                if DISCORD_SHOW_ID:
                    cid = d.get('id') or ''
                    if cid:
                        parts.append(str(cid))
                if url:
                    parts.append(f"[{title_text}]({url})")
                else:
                    parts.append(title_text)
                if DISCORD_SHOW_LOCATION and location:
                    parts.append(location)
                if date:
                    parts.append(date)

                lines.append(f"• {' — '.join(p for p in parts if p)}")

        desc = "\n".join(lines) or '(none)'
        # Discord embed color: a neutral/blurple tone
        embed = {
            'title': title,
            'description': desc,
            'color': 5763714
        }
        return embed

    try:
        def _unique_key(item) -> str:
            if not item and item != 0:
                return ''
            if isinstance(item, (str, int)):
                return str(item)
            try:
                if item.get('id'):
                    return str(item.get('id'))
                if item.get('url'):
                    return str(item.get('url'))
                name = item.get('title') or item.get('name') or ''
                date = item.get('date') or ''
                return f"{name}|{date}".strip()
            except Exception:
                return str(item)

        # load known weeklies and doubles
        try:
            with open(os.path.join(base_dir, KNOWN_WEEKLY_FILE), 'r', encoding='utf-8') as f:
                known_weeklies = json.load(f) or []
        except Exception:
            known_weeklies = []

        try:
            with open(os.path.join(base_dir, KNOWN_DOUBLES_FILE), 'r', encoding='utf-8') as f:
                known_doubles = json.load(f) or []
        except Exception:
            known_doubles = []

        known_weekly_keys = { _unique_key(x) for x in known_weeklies }
        known_double_keys = { _unique_key(x) for x in known_doubles }

        new_weeklies = [w for w in weekly_list if _unique_key(w) not in known_weekly_keys]
        new_doubles = [d for d in doubles_list if _unique_key(d) not in known_double_keys]

        if new_weeklies or new_doubles:
            embed = build_weekly_embed(new_weeklies, new_doubles)
            posted = post_embeds_to_discord(weekly_thread, token, [embed])
            if not posted:
                wd_msg = f"VIIKKARIT ({len(new_weeklies)}) ja PARIKISAT ({len(new_doubles)})\n\n" + fmt_weekly_and_doubles(new_weeklies, new_doubles)
                post_to_discord(weekly_thread, token, wd_msg)
        else:
            print('No new weekly or doubles competitions found; skipping weekly post')

        # Persist known weeklies/doubles (overwrite with current lists)
        try:
            with open(os.path.join(base_dir, KNOWN_WEEKLY_FILE), 'w', encoding='utf-8') as f:
                json.dump(weekly_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print('Failed to update known weekly file:', e)

        try:
            with open(os.path.join(base_dir, KNOWN_DOUBLES_FILE), 'w', encoding='utf-8') as f:
                json.dump(doubles_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print('Failed to update known doubles file:', e)
    except Exception as e:
        print('Failed to build/send weekly embed:', e)
        wd_msg = f"VIIKKARIT ({weekly_count}) ja PARIKISAT ({doubles_count})\n\n" + fmt_weekly_and_doubles(weekly_list, doubles_list)
        post_to_discord(weekly_thread, token, wd_msg)


def _run_registration_check_once(base_dir, out_path=None):
    """Run the registration checker once: inspect PDGA + weekly lists, write pending file,
    and call posting helpers to post new/open registrations.
    This mirrors hyvat_koodit.check_registration + post_pending_registration logic but
    keeps it inside this process to avoid subprocesses.
    """
    try:
        import hyvat_koodit.check_registration as reg_mod
        import hyvat_koodit.post_pending_registration as post_mod
    except Exception as e:
        print('Failed to import registration modules:', e)
        return

    pdga_path = os.path.join(base_dir, 'PDGA.json')
    weekly_path = os.path.join(base_dir, 'VIIKKOKISA.json')
    out_path = out_path or os.path.join(base_dir, REG_CHECK_FILE)

    comps = []
    for path, label in ((pdga_path, 'PDGA'), (weekly_path, 'VIIKKOKISA')):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lst = json.load(f)
                for c in lst:
                    if label == 'VIIKKOKISA':
                        c.setdefault('kind', 'VIIKKOKISA')
                    comps.append(c)
        except FileNotFoundError:
            # not fatal; continue
            continue
        except Exception as e:
            print('Failed to read competition list for registration check:', e)

    results = []
    for c in comps:
        try:
            r = reg_mod.check_competition(c)
            results.append(r)
        except Exception as e:
            print('check_competition error for', c.get('id') or c.get('name'), e)

    # Save pending registration file (only open or opening_soon entries)
    pending = [r for r in results if r.get('registration_open') or r.get('opening_soon')]
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)
        print(f'Saved {len(pending)} pending registrations to', out_path)
    except Exception as e:
        print('Failed to save pending registrations:', e)
        return

    # Now reuse post_pending_registration helpers to post new items
    try:
        # load pending through helper for consistency
        pending_loaded = post_mod.load_pending()
        if not pending_loaded:
            print('No open registrations to post')
            return

        # Partition pending items
        pdga = []
        weekly = []
        for it in pending_loaded:
            kind = (it.get('kind') or it.get('tier') or '').upper()
            if 'PDGA' in kind:
                pdga.append(it)
            else:
                weekly.append(it)

        # Use post_mod's functions to determine new items and post
        known_pdga = post_mod.load_known(post_mod.KNOWN_PDGA)
        known_weekly = post_mod.load_known(post_mod.KNOWN_WEEKLY)

        pdga_ids = [str(it.get('id') or it.get('url') or it.get('name')) for it in pdga]
        weekly_ids = [str(it.get('id') or it.get('url') or it.get('name')) for it in weekly]

        new_pdga = [it for it in pdga if str(it.get('id') or it.get('url') or it.get('name')) not in known_pdga]
        new_weekly = [it for it in weekly if str(it.get('id') or it.get('url') or it.get('name')) not in known_weekly]

        # PDGA posting
        to_post_pdga = pdga if not known_pdga else new_pdga
        if to_post_pdga:
            pdga_open = [it for it in to_post_pdga if it.get('registration_open')]
            pdga_soon = [it for it in to_post_pdga if (not it.get('registration_open')) and it.get('opening_soon')]

            if pdga_open:
                embeds = post_mod.build_embeds_with_title(pdga_open, f"REKISTERÖINTI AVOINNA ({len(pdga_open)})", 5763714)
                post_mod.post_embeds(post_mod.PDGA_THREAD, embeds)
            if pdga_soon:
                embeds = post_mod.build_embeds_with_title(pdga_soon, f"REKISTERÖINTI AVAUTUU PIAN ({len(pdga_soon)})", 16750848)
                post_mod.post_embeds(post_mod.PDGA_THREAD, embeds)

            known_pdga.update(pdga_ids)
            post_mod.save_known(post_mod.KNOWN_PDGA, known_pdga)

        # Weekly posting
        to_post_weekly = weekly if not known_weekly else new_weekly
        if to_post_weekly:
            weekly_open = [it for it in to_post_weekly if it.get('registration_open')]
            weekly_soon = [it for it in to_post_weekly if (not it.get('registration_open')) and it.get('opening_soon')]

            if weekly_open:
                embeds = post_mod.build_embeds_with_title(weekly_open, f"REKISTERÖINTI AVOINNA ({len(weekly_open)})", 5763714)
                post_mod.post_embeds(post_mod.WEEKLY_THREAD, embeds)
            if weekly_soon:
                embeds = post_mod.build_embeds_with_title(weekly_soon, f"REKISTERÖINTI AVAUTUU PIAN ({len(weekly_soon)})", 16750848)
                post_mod.post_embeds(post_mod.WEEKLY_THREAD, embeds)

            known_weekly.update(weekly_ids)
            post_mod.save_known(post_mod.KNOWN_WEEKLY, known_weekly)

    except Exception as e:
        print('Failed to post pending registrations via post_mod:', e)


def start_registration_worker(base_dir, interval_seconds: int):
    def worker():
        while True:
            try:
                _run_registration_check_once(base_dir)
            except Exception as e:
                print('Registration worker error:', e)
            time.sleep(max(10, int(interval_seconds)))
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


def main():
    import argparse
    parser = argparse.ArgumentParser(description='metrixDiscordBot orchestrator')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--daemon', action='store_true', help='Run continuously')
    parser.add_argument('--presence', action='store_true', help='Start Discord gateway client to show bot as online (requires discord.py and valid token)')
    parser.add_argument('--interval-minutes', type=float, default=float(os.environ.get('METRIX_INTERVAL_MINUTES', '1')),
                        help='Interval between runs when --daemon (minutes)')
    parser.add_argument('--times', type=int, default=1, help='When used with --once, run the orchestrator this many times in sequence')
    args = parser.parse_args()

    # If presence requested, start gateway client now (works for once/daemon modes)
    presence_thread = None
    if args.presence:
        token = os.environ.get('DISCORD_TOKEN')
        if not token:
            print('DISCORD_TOKEN not set; skipping presence and command listener')
        else:
            try:
                from hyvat_koodit.discord_presence import start_presence
                # run_forever True for daemon mode; if --once, run_forever=False so it disconnects
                presence_thread = start_presence(token, status_message=os.environ.get('DISCORD_STATUS', 'MetrixBot'), run_forever=not args.once)
                try:
                    from hyvat_koodit.command_handler import start_command_listener
                    start_command_listener(token, prefix='!', run_forever=not args.once)
                except Exception as e:
                    print('Failed to start command listener:', e)
            except Exception as e:
                print('Failed to start presence thread:', e)

    if args.once:
        times = max(1, int(args.times or 1))
        for i in range(times):
            print(f'Run {i+1}/{times}')
            run_once()
            # run registration check once after each run_once when requested
            if args.check_registrations:
                _run_registration_check_once(BASE_DIR)
            if i < times - 1:
                # small delay between runs to avoid hammering upstream
                time.sleep(1)
        return

    if args.daemon:
        print('Starting metrixbot daemon; first run now')
        # start registration worker thread
        try:
            start_registration_worker(BASE_DIR, CHECK_REGISTRATION_INTERVAL)
            print('Registration worker started (interval', CHECK_REGISTRATION_INTERVAL, 's)')
        except Exception as e:
            print('Failed to start registration worker:', e)
        while True:
            try:
                run_once()
                # After updating competition files and known caches, run registration check
                try:
                    _run_registration_check_once(BASE_DIR)
                except Exception as e:
                    print('Registration check failed after run_once:', e)
            except Exception as e:
                print('Run failed in daemon loop:', e)
            # sleep interval
            mins = max(0.1, args.interval_minutes)
            secs = mins * 60.0
            print(f'Next run in {mins} minutes')
            time.sleep(secs)


if __name__ == '__main__':
    main()
