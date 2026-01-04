import os
import json
import time
import threading
import requests
import logging
import re
import csv
from datetime import datetime, date, timedelta
from typing import Optional

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
# Testikanava, johon kaikki uudet ilmoitukset ohjataan oletuksena:
TEST_CHANNEL_ID = os.environ.get("DISCORD_TEST_CHANNEL_ID", "1456702993377267905")

DISCORD_CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", TEST_CHANNEL_ID))
DISCORD_THREAD_ID = int(os.environ.get("DISCORD_THREAD_ID", TEST_CHANNEL_ID))
DISCORD_WEEKLY_THREAD_ID = int(os.environ.get("DISCORD_WEEKLY_THREAD_ID", TEST_CHANNEL_ID))
DISCORD_DISCS_THREAD_ID = os.environ.get("DISCORD_DISCS_THREAD", TEST_CHANNEL_ID)

WEEKLY_JSON = os.environ.get("WEEKLY_JSON", "weekly_pair.json")
WEEKLY_LOCATION = os.environ.get("WEEKLY_LOCATION", "Etelä-Pohjanmaa").strip().lower()
WEEKLY_RADIUS_KM = int(os.environ.get("WEEKLY_RADIUS_KM", "100"))
WEEKLY_SEARCH_URL = os.environ.get("WEEKLY_SEARCH_URL", "https://discgolfmetrix.com/?u=competitions_all&view=1&competition_name=&period=&date1=2026-01-01&date2=2027-01-01&my_country=&registration_open=&registration_date1=&registration_date2=&country_code=FI&my_club=0&club_type=&club_id=&association_id=0&close_to_me=&area=Etelä-Pohjanmaa&city=&course_id=&division=&my=&view=1&sort_name=&sort_order=&my_all=&from=1&to=30")

METRIX_URL = os.environ.get("METRIX_URL", "https://discgolfmetrix.com/?u=competitions_all&view=2&competition_name=&period=&date1=2026-01-01&date2=2027-01-01&my_country=&registration_open=&registration_date1=&registration_date2=&country_code=FI&my_club=&club_type=&club_id=&association_id=0&close_to_me=&area=&city=&course_id=&type=C&division=&my=&view=2&sort_name=&sort_order=&my_all=")

AUTO_LIST_INTERVAL = int(os.environ.get('AUTO_LIST_INTERVAL', '86400'))
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '600'))
CHECK_REGISTRATION_INTERVAL = int(os.environ.get('CHECK_REGISTRATION_INTERVAL', '3600'))
CURRENT_CAPACITY_INTERVAL = CHECK_INTERVAL

# Päivittäisen digestin viimeisin ajopäivä (päivitetään daemon-loopissa).
# Tämä tuodaan globaaliksi, jotta admin-komennot voivat tarvittaessa
# nollata arvon ja pakottaa digestin ajettavaksi saman päivän aikana
# uuteen kellonaikaan.
LAST_DIGEST_DATE: Optional[date] = None

# Päivittäisen kilpailudigestin (PDGA + viikkarit + rekisteröinnit) kellonaika.
# Voit muuttaa näitä esim. .env-tiedostossa: DAILY_DIGEST_HOUR=4, DAILY_DIGEST_MINUTE=0
# Oletusarvo ajettu klo 04:00:00
DAILY_DIGEST_HOUR = int(os.environ.get('DAILY_DIGEST_HOUR', '4'))  # 0-23
DAILY_DIGEST_MINUTE = int(os.environ.get('DAILY_DIGEST_MINUTE', '00'))  # 0-59

CACHE_FILE = os.environ.get('CACHE_FILE', 'known_pdga_competitions.json')
REG_CHECK_FILE = os.environ.get('REG_CHECK_FILE', 'pending_registration.json')
KNOWN_WEEKLY_FILE = os.environ.get('KNOWN_WEEKLY_FILE', 'known_weekly_competitions.json')
KNOWN_DOUBLES_FILE = os.environ.get('KNOWN_DOUBLES_FILE', 'known_doubles_competitions.json')
KNOWN_PDGA_DISCS_FILE = os.environ.get('KNOWN_PDGA_DISCS_FILE', 'known_pdga_discs_specs.json')

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
    """Try to extract a date like MM/DD/YY or MM/DD/YYYY from raw_date and
    output it eurooppalaisittain DD/MM/YYYY-muodossa.

    Jos DISCORD_DATE_FORMAT == 'DDMMYYYY', palautetaan ilman erottimia
    muodossa DDMMYYYY. Muuten käytetään 'DD/MM/YYYY'.
    """
    if not raw_date:
        return ''
    # Etsi ensimmäinen "MM/DD/YY"-tyyppinen päivämääräteksti.
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', raw_date)
    if not m:
        return '' if DISCORD_DATE_FORMAT == 'DDMMYYYY' else raw_date
    mo, d, y = m.groups()  # Metrix antaa muodossa MM/DD/YY → vaihdetaan paikkaa
    if len(y) == 2:
        y = '20' + y
    d = d.zfill(2)
    mo = mo.zfill(2)
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


def post_startup_capacity_alerts(base_dir: str, token: Optional[str]):
    """On startup, check for capacity scan artifacts and post a short summary to Discord.
    Looks for `CAPACITY_SCAN_RESULTS.json` and `CAPACITY_ALERTS.json` in `base_dir`.
    """
    if not token:
        print('No DISCORD_TOKEN; skipping startup capacity alerts')
        return
    scan_path = os.path.join(base_dir, 'CAPACITY_SCAN_RESULTS.json')
    alerts_path = os.path.join(base_dir, 'CAPACITY_ALERTS.json')

    def _load_json(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    scan = _load_json(scan_path)
    alerts = _load_json(alerts_path)

    # If neither file exists or both empty, nothing to do
    if not scan and not alerts:
        print('No capacity scan or alerts found at startup')
        return

    # Build a short message/embeds
    embeds = []
    if scan:
        try:
            total = len(scan) if isinstance(scan, list) else (len(scan.get('results', [])) if isinstance(scan, dict) else 0)
        except Exception:
            total = 0
        embeds.append({
            'title': 'Metrix: Kapasiteettiskannaus (startup)',
            'description': f'Skannattuja kohteita: {total}',
            'color': 3447003
        })

    if alerts:
        try:
            a_count = len(alerts) if isinstance(alerts, list) else (len(alerts.get('alerts', [])) if isinstance(alerts, dict) else 0)
        except Exception:
            a_count = 0
        # Build a compact embed listing up to 8 alerts with key info
        lines = []
        if isinstance(alerts, list):
            for it in alerts[:8]:
                title = it.get('title') or it.get('name') or it.get('competition') or ''
                rem = it.get('remaining')
                reg = it.get('registered')
                lim = it.get('limit')
                url = it.get('url') or it.get('link') or ''
                part = title
                if rem is not None:
                    part += f' — jäljellä: {rem}'
                if reg is not None and lim is not None:
                    part += f' ({reg}/{lim})'
                if url:
                    part = f'[{part}]({url})'
                lines.append(part)
        else:
            lines.append(f'Ilmoituksia: {a_count}')

        embeds.append({
            'title': f'Kapasiteetti-ilmoituksia: {a_count}',
            'description': '\n'.join(lines) or '(ei kohteita)',
            'color': 15105570
        })

    # Post to configured thread (use CAPACITY_THREAD_ID, DISCORD_THREAD_ID or DISCORD_CHANNEL_ID)
    target = os.environ.get('CAPACITY_THREAD_ID') or os.environ.get('DISCORD_THREAD_ID') or os.environ.get('DISCORD_CHANNEL_ID')
    if not target:
        print('No thread/channel configured for capacity alerts; skipping post')
        return
    print('Posting startup capacity summary to target:', target)
    try:
        posted = post_embeds_to_discord(target, token, embeds)
        if posted:
            print('Posted startup capacity summary to Discord')
            return
        # try fallback to main channel id if different
        fallback = os.environ.get('DISCORD_CHANNEL_ID')
        if fallback and fallback != target:
            print('Initial post failed; trying fallback channel:', fallback)
            try:
                posted2 = post_embeds_to_discord(fallback, token, embeds)
                if posted2:
                    print('Posted startup capacity summary to fallback channel')
                    return
            except Exception as e:
                print('Fallback post exception:', e)
        print('Failed to post startup capacity summary; check target ID and bot permissions')
    except Exception as e:
        print('Exception posting startup capacity summary:', e)
def run_once():
    # Import modules from komento_koodit (entinen hyvat_koodit)
    import komento_koodit.search_pdga_sfl as pdga_mod
    # Import tulokset module for competition result parsing and club detection
    import komento_koodit.commands_tulokset as tulokset_mod
    # Importing weekly module executes it and writes VIIKKOKISA.json
    import komento_koodit.search_weekly_fast as weekly_mod
    # Seutu-viikkarit (EP + naapurimaakunnat) kirjoitetaan erilliseen JSONiin
    import komento_koodit.search_weekly_areas as weekly_areas_mod
    import komento_koodit.search_pari_EP2025 as pari_mod

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

    # Seutu-viikkarit: ajetaan erillinen hakuskripti, joka kirjoittaa VIIKKARIT_SEUTU.json
    try:
        weekly_areas_mod.main()
    except Exception as e:
        print('Seutu-viikkareiden haku (VIIKKARIT_SEUTU) epäonnistui:', e)

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

    # Suodata pois pelkät "runko"-sarjat (esim. "FGK viikkarit 2026"),
    # jotta viestissä näkyvät vain varsinaiset kilpailukerrat (nuolimerkinnällä "→").
    def _is_weekly_container(item, all_items):
        try:
            title = item.get('title') or item.get('name') or ''
        except Exception:
            return False
        # Jos otsikossa on nuoli, kyse ei ole rungosta
        if '→' in title:
            return False
        prefix = f"{title} → " if title else ''
        if not prefix.strip():
            return False
        for other in all_items:
            if other is item:
                continue
            try:
                ot = other.get('title') or other.get('name') or ''
            except Exception:
                continue
            if ot.startswith(prefix):
                return True
        return False

    weekly_display_list = [w for w in weekly_list if not _is_weekly_container(w, weekly_list)]

    # Suodata vastaavalla logiikalla PDGA-puolelta pois sarjarungot, kuten
    # "WDG:n PDGA-Liiga 1/2026", jotta listalla näkyvät pääasiassa
    # yksittäiset kilpailut tai kierrokset.
    def _is_pdga_container(item, all_items):
        try:
            title = item.get('name') or item.get('title') or ''
        except Exception:
            return False
        if not title:
            return False
        # Nuolet otsikossa -> ei ole runko
        if '→' in title:
            return False
        prefix = f"{title} → "
        for other in all_items:
            if other is item:
                continue
            try:
                ot = (other.get('name') or other.get('title') or '').strip()
            except Exception:
                continue
            if ot.startswith(prefix):
                return True
        # Pitkä päivämääräväli (esim. "01/01/26 - 12/31/26") viittaa usein sarjaan.
        try:
            date_txt = str(item.get('date') or '')
        except Exception:
            date_txt = ''
        if '-' in date_txt:
            parts_dt = [p.strip() for p in date_txt.split('-')]
            if len(parts_dt) == 2 and parts_dt[0] and parts_dt[1] and parts_dt[0] != parts_dt[1]:
                return True
        return False

    pdga_display_list = [c for c in pdga_list if not _is_pdga_container(c, pdga_list)]

    # Normalize PDGA entries that are multi-round events (e.g. suffix "→ 1. Kierros", "→ 2. Kierros").
    # Keep only a single representative per multi-round event — prefer a base (non-round) entry,
    # otherwise prefer the explicit "1. Kierros" entry, or the earliest date among rounds.
    def _normalize_pdga_rounds(lst):
        by_base = {}
        others = []
        for item in lst:
            title = (item.get('name') or item.get('title') or '').strip()
            if not title:
                others.append(item)
                continue
            parts = [p.strip() for p in title.split('→')]
            last = parts[-1].lower() if parts else ''
            if 'kierros' in last:
                base_key = ' → '.join(parts[:-1]).strip()
                if not base_key:
                    base_key = title
                by_base.setdefault(base_key, []).append(item)
            else:
                # non-round entry — keep as-is, but mark base to prefer it
                base_key = title
                by_base.setdefault(base_key, []).append(item)

        normalized = []
        for base, items in by_base.items():
            if len(items) == 1:
                normalized.append(items[0])
                continue
            # If any item doesn't end with 'kierros' prefer that (base event)
            non_round = [it for it in items if 'kierros' not in ((it.get('name') or it.get('title') or '').lower())]
            if non_round:
                normalized.append(non_round[0])
                continue
            # Prefer explicit '1. Kierros'
            one_round = None
            for it in items:
                t = (it.get('name') or it.get('title') or '').lower()
                if re.search(r'\b1\.?\s*kierros\b', t):
                    one_round = it
                    break
            if one_round:
                normalized.append(one_round)
                continue
            # Fallback: pick the item with the earliest date found in the title
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

        # Preserve original order as much as possible: build index map
        seen = set()
        final = []
        for it in lst:
            if it in normalized and id(it) not in seen:
                final.append(it)
                seen.add(id(it))
        # append any normalized items that weren't preserved (rare)
        for it in normalized:
            if id(it) not in seen:
                final.append(it)
        return final

    pdga_display_list = _normalize_pdga_rounds(pdga_display_list)

    # Prepare summaries
    pdga_count = len(pdga_display_list)
    weekly_count = len(weekly_display_list)
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

    def _shorten_series_title(raw_title: str) -> str:
        """Palauta osakilpailun nimi ilman sarjan/runko-otsikkoa.

        Esim. "Luoma-ahon Lauantai Liiga → Luoma-ahon Lauantai Liigan 12 osakilpailu"
        -> "Luoma-ahon Lauantai Liigan 12 osakilpailu".
        """
        try:
            if not raw_title:
                return ''
            if '→' in raw_title:
                return raw_title.split('→')[-1].strip()
            return raw_title
        except Exception:
            return raw_title

    def fmt_weekly_and_doubles(weeks, doubles, limit=20):
        lines = []
        for i, c in enumerate(weeks[:limit]):
            # Build a single line for the competition based on configuration flags
            raw_title = c.get('title') or c.get('name') or ''
            title = _shorten_series_title(raw_title)
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
                raw_title = d.get('title') or d.get('name') or ''
                title = _shorten_series_title(raw_title)
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

    print('Yhteenveto ajosta:\n' + f"PDGA: {pdga_count}, VIIKKOKISA: {weekly_count}, DOUBLES: {doubles_count}")

    token = os.environ.get('DISCORD_TOKEN')
    # PDGA- ja viikkarikatsaukset: oletuksena testikanava, ellei ympäristömuuttujilla ohiteta
    pdga_thread = os.environ.get('DISCORD_PDGA_THREAD', TEST_CHANNEL_ID)
    weekly_thread = os.environ.get('DISCORD_WEEKLY_THREAD', TEST_CHANNEL_ID)

    if not token:
        print('DISCORD_TOKEN not set; skipping Discord posts')
        return

    # Lataa kapasiteettiskannauksen tulokset (jos olemassa), jotta voidaan näyttää
    # kisaajamäärä/limit PDGA-listan riveillä.
    capacity_by_id = {}
    capacity_by_url = {}
    try:
        cap_path = os.path.join(base_dir, 'CAPACITY_SCAN_RESULTS.json')
        with open(cap_path, 'r', encoding='utf-8') as f:
            cap_data = json.load(f) or []
        for item in cap_data:
            cid = str(item.get('id') or '')
            url = item.get('url') or ''
            cap = item.get('capacity_result') or {}
            registered = cap.get('registered')
            limit = cap.get('limit')
            queued = cap.get('queued')
            if isinstance(registered, int) and isinstance(limit, int):
                info = {'registered': registered, 'limit': limit, 'queued': queued}
                if cid:
                    capacity_by_id[cid] = info
                if url:
                    capacity_by_url[url] = info
    except FileNotFoundError:
        pass
    except Exception as e:
        print('Kapasiteettidataa ei voitu lukea PDGA-yhteenvetoa varten:', e)

    # Lataa rekisteröintitilanne pending_registration.json-tiedostosta, jotta
    # voidaan erottaa avoimet kisat niistä, joissa ilmo ei ole avoinna.
    reg_status_by_id = {}
    reg_status_by_url = {}
    have_reg_status = False
    try:
        reg_path = os.path.join(base_dir, REG_CHECK_FILE)
        with open(reg_path, 'r', encoding='utf-8') as f:
            reg_data = json.load(f) or []
        for item in reg_data:
            cid = str(item.get('id') or '')
            url = item.get('url') or ''
            is_open = bool(item.get('registration_open'))
            if cid:
                reg_status_by_id[cid] = is_open
            if url:
                reg_status_by_url[url] = is_open
        have_reg_status = True
    except FileNotFoundError:
        # Ei pending-tiedostoa vielä -> oletetaan, ettei rekisteröintitietoa ole
        have_reg_status = False
    except Exception as e:
        print('Rekisteröintistatusta ei voitu lukea PDGA-yhteenvetoa varten:', e)
        have_reg_status = False

    def _capacity_suffix(item) -> str:
        try:
            cid = str(item.get('id') or '')
            url = item.get('url') or ''
        except Exception:
            return ''
        info = None
        if cid and cid in capacity_by_id:
            info = capacity_by_id[cid]
        elif url and url in capacity_by_url:
            info = capacity_by_url[url]
        if not info:
            return ''
        registered = info.get('registered')
        limit = info.get('limit')
        queued = info.get('queued')
        if not isinstance(registered, int) or not isinstance(limit, int) or limit <= 0:
            return ''

        # Selvitä onko rekisteröinti avoinna (pending_registration.json perusteella),
        # jos dataa on saatavilla.
        is_open = None
        if have_reg_status:
            if cid and cid in reg_status_by_id:
                is_open = reg_status_by_id[cid]
            elif url and url in reg_status_by_url:
                is_open = reg_status_by_url[url]

        # Jos kisassa ei ole yhtään ilmoittautunutta pelaajaa, näytetään joko
        # "0/limit" (kun rekisteröinti on avoinna) tai "(rekisteröinti ei avoinna)"
        # jos rekisteröinti ei ole avoinna / ei vielä avoinna.
        if registered == 0:
            if have_reg_status and not is_open:
                return " (rekisteröinti ei avoinna)"
            return f" (0/{limit})"

        if isinstance(queued, int) and queued > 0:
            return f" ({registered}/{limit}, jono {queued})"
        return f" ({registered}/{limit})"

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
        new_pdga = [c for c in pdga_display_list if _unique_key(c) not in known_keys]

        pdga_detections = []
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
                    suffix = _capacity_suffix(it)
                    if url:
                        lines.append(f"• [{name}]({url}){suffix}")
                    else:
                        lines.append(f"• {name}{suffix}")
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
            # Try to detect Lakeus players in Top3 for any PDGA items that include a results URL
            try:
                for it in new_pdga:
                    url = it.get('url') or ''
                    name = it.get('name') or it.get('title') or ''
                    if not url:
                        continue
                    u = None
                    try:
                        u = tulokset_mod._ensure_results_url(url)
                        if not u or not isinstance(u, str):
                            res = None
                        else:
                            res = tulokset_mod._fetch_competition_results(u)
                    except Exception:
                        res = None
                    if not res:
                        continue
                    try:
                        if isinstance(u, str) and u:
                            hc = tulokset_mod._fetch_handicap_table(u)
                        else:
                            hc = []
                    except Exception:
                        hc = []
                    # Build trimmed top3 result
                    filtered_classes = []
                    for cls in res.get('classes', []):
                        rows = cls.get('rows') or []
                        top_rows = []
                        count_3 = 0
                        for r in rows:
                            pos = r.get('position')
                            total = str(r.get('total') or '')
                            try:
                                total_num = int(total)
                            except Exception:
                                total_num = None
                            if not isinstance(pos, int) or total_num == 0:
                                continue
                            if pos == 1 or pos == 2:
                                top_rows.append(r)
                            elif pos == 3:
                                count_3 += 1
                        if count_3 > 0:
                            for r in rows:
                                pos = r.get('position')
                                total = str(r.get('total') or '')
                                try:
                                    total_num = int(total)
                                except Exception:
                                    total_num = None
                                if isinstance(pos, int) and pos == 3 and total_num != 0 and r not in top_rows:
                                    top_rows.append(r)
                        filtered_classes.append({"class_name": cls.get("class_name"), "rows": top_rows})
                    trimmed = {"event_name": name or res.get('event_name', ''), "classes": filtered_classes}
                    dets = tulokset_mod._detect_club_memberships_for_event(trimmed, hc, name or res.get('event_name', ''))
                    if dets:
                        pdga_detections.extend(dets)
            except Exception:
                pass
        else:
            # Ei uusia PDGA-kisoja -> lähetetään silti päivittäinen yhteenveto
            print('Ei uusia PDGA-kisoja; lähetetään päivittäinen yhteenveto Discordiin')
            # Rakennetaan yksi embed kaikista tunnetuista PDGA-kisoista (rajataan tarvittaessa)
            lines = []
            for it in pdga_display_list[:40]:
                name = it.get('name') or it.get('title') or ''
                url = it.get('url') or ''
                suffix = _capacity_suffix(it)
                if url:
                    lines.append(f"• [{name}]({url}){suffix}")
                else:
                    lines.append(f"• {name}{suffix}")
            if len(pdga_display_list) > 40:
                lines.append(f"...ja {len(pdga_display_list)-40} muuta PDGA-kisaa")
            embed = {
                'title': f'PDGA-kisat (päivittäinen yhteenveto, {len(pdga_display_list)})',
                'description': "\n".join(lines) or '(ei kisoja)',
                'color': 16750848
            }
            post_embeds_to_discord(pdga_thread, token, [embed])
            # Also try detection for listed PDGA items when no new_pdga (daily summary)
            try:
                for it in pdga_display_list[:40]:
                    url = it.get('url') or ''
                    name = it.get('name') or it.get('title') or ''
                    if not url:
                        continue
                    u = None
                    try:
                        u = tulokset_mod._ensure_results_url(url)
                        if not u or not isinstance(u, str):
                            res = None
                        else:
                            res = tulokset_mod._fetch_competition_results(u)
                    except Exception:
                        res = None
                    if not res:
                        continue
                    try:
                        if isinstance(u, str) and u:
                            hc = tulokset_mod._fetch_handicap_table(u)
                        else:
                            hc = []
                    except Exception:
                        hc = []
                    filtered_classes = []
                    for cls in res.get('classes', []):
                        rows = cls.get('rows') or []
                        top_rows = []
                        count_3 = 0
                        for r in rows:
                            pos = r.get('position')
                            total = str(r.get('total') or '')
                            try:
                                total_num = int(total)
                            except Exception:
                                total_num = None
                            if not isinstance(pos, int) or total_num == 0:
                                continue
                            if pos == 1 or pos == 2:
                                top_rows.append(r)
                            elif pos == 3:
                                count_3 += 1
                        if count_3 > 0:
                            for r in rows:
                                pos = r.get('position')
                                total = str(r.get('total') or '')
                                try:
                                    total_num = int(total)
                                except Exception:
                                    total_num = None
                                if isinstance(pos, int) and pos == 3 and total_num != 0 and r not in top_rows:
                                    top_rows.append(r)
                        filtered_classes.append({"class_name": cls.get("class_name"), "rows": top_rows})
                    trimmed = {"event_name": name or res.get('event_name', ''), "classes": filtered_classes}
                    dets = tulokset_mod._detect_club_memberships_for_event(trimmed, hc, name or res.get('event_name', ''))
                    if dets:
                        pdga_detections.extend(dets)
            except Exception:
                pass

        # If any PDGA detections found, persist and post aggregated message
        try:
            if pdga_detections:
                msgs = []
                for d in pdga_detections:
                    try:
                        tulokset_mod._increment_club_success(d.get('metrix_id') or '', d.get('name') or '', d.get('club') or '', context=f"PDGA {d.get('event_name')}")
                    except Exception:
                        pass
                    pname = d.get('name') or ''
                    pos = d.get('position')
                    total = d.get('total') or ''
                    cname = d.get('class_name') or ''
                    club = d.get('club') or ''
                    msgs.append(f"{pname} — sijoitus {pos} {total} luokassa {cname} ({club})")
                try:
                    post_to_discord(pdga_thread, token, "Onnittelut Lakeus Disc Golf -seuran pelaajille!\n" + "\n".join(msgs))
                except Exception:
                    pass
        except Exception:
            pass

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
            raw_title = c.get('title') or c.get('name') or ''
            title_text = _shorten_series_title(raw_title)
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
                raw_title = d.get('title') or d.get('name') or ''
                title_text = _shorten_series_title(raw_title)
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

        new_weeklies = [w for w in weekly_display_list if _unique_key(w) not in known_weekly_keys]
        new_doubles = [d for d in doubles_list if _unique_key(d) not in known_double_keys]

        # Filter out any new weeklies that already have results available on Metrix.
        # This prevents posting items like "Uusia viikkokisoja lisätty" for events
        # that already contain results.
        try:
            import komento_koodit.commands_tulokset as ct
            import re as _re
            filtered_weeklies = []
            for w in new_weeklies:
                url_raw = str(w.get('url') or w.get('metrix') or w.get('id') or '')
                if not url_raw:
                    filtered_weeklies.append(w)
                    continue
                try:
                    url_base = ct._build_competition_url(url_raw) or url_raw
                    url = ct._ensure_results_url(url_base)
                except Exception:
                    filtered_weeklies.append(w)
                    continue

                try:
                    res = ct._fetch_competition_results(url)
                except Exception:
                    res = None

                try:
                    hc_table = ct._fetch_handicap_table(url)
                except Exception:
                    hc_table = []

                has_valid_results = False
                if res and res.get('classes'):
                    for cls in res.get('classes', []):
                        for r in (cls.get('rows') or []):
                            pos = r.get('position')
                            total_txt = str(r.get('total') or '').strip()
                            m = _re.match(r"-?\d+", total_txt)
                            total_num = int(m.group(0)) if m else None
                            if isinstance(pos, int) and total_num not in (None, 0):
                                has_valid_results = True
                                break
                        if has_valid_results:
                            break

                # If the HC table exists, consider that results are present as well.
                if has_valid_results or (hc_table and len(hc_table) > 0):
                    # skip adding this weekly to new_weeklies (results already present)
                    continue
                filtered_weeklies.append(w)

            new_weeklies = filtered_weeklies
        except Exception:
            # On error, fall back to original new_weeklies list
            pass

        # Detect known weeklies that have newly available results and notify.
        # Prepare results list and try to import the tulokset module for detection.
        results_added = []
        try:
            ct = __import__('komento_koodit.commands_tulokset', fromlist=[''])[0] if False else __import__('komento_koodit.commands_tulokset', fromlist=[''])
        except Exception:
            ct = None

        if ct is not None:
            try:
                for w in weekly_display_list:
                    key = _unique_key(w)
                    if key not in known_weekly_keys:
                        continue
                    url_raw = str(w.get('url') or w.get('metrix') or w.get('id') or '')
                    if not url_raw:
                        continue
                    try:
                        url_base = ct._build_competition_url(url_raw) or url_raw
                        url = ct._ensure_results_url(url_base)
                    except Exception:
                        continue

                    try:
                        res = ct._fetch_competition_results(url)
                    except Exception:
                        res = None
                    try:
                        hc_table = ct._fetch_handicap_table(url)
                    except Exception:
                        hc_table = []

                    has_valid_results = False
                    if res and res.get('classes'):
                        for cls in res.get('classes', []):
                            for r in (cls.get('rows') or []):
                                pos = r.get('position')
                                total_txt = str(r.get('total') or '').strip()
                                m = re.match(r"-?\d+", total_txt)
                                total_num = int(m.group(0)) if m else None
                                if isinstance(pos, int) and total_num not in (None, 0):
                                    has_valid_results = True
                                    break
                            if has_valid_results:
                                break

                    if has_valid_results or (hc_table and len(hc_table) > 0):
                        # Add to notify list
                        results_added.append((w, res, hc_table))
            except Exception:
                results_added = []

            if results_added:
                lines = []
                for w, res, hc_table in results_added:
                    title_text = _shorten_series_title(w.get('title') or w.get('name') or '')
                    url = w.get('url') or ''
                    if url:
                        lines.append(f"• [{title_text}]({url})")
                    else:
                        lines.append(f"• {title_text}")
                    # Include Top3 snippet if available
                    try:
                        if res:
                            top = ct._format_top3_lines_for_result(res, hc_present=bool(hc_table))
                            if top:
                                for t in top:
                                    lines.append(f"  {t}")
                        elif hc_table:
                            top = ct._format_hc_top3_lines(hc_table)
                            for t in top:
                                lines.append(f"  {t}")
                    except Exception:
                        continue

                desc = "\n".join(lines)
                embed = {'title': f'Uusia tuloksia saatavilla ({len(results_added)})', 'description': desc, 'color': 5763714}
                try:
                    post_embeds_to_discord(weekly_thread, token, [embed])
                except Exception:
                    try:
                        post_to_discord(weekly_thread, token, f"Uusia tuloksia saatavilla:\n\n{desc}")
                    except Exception:
                        pass

        if new_weeklies or new_doubles:
            embed = build_weekly_embed(new_weeklies, new_doubles)
            posted = post_embeds_to_discord(weekly_thread, token, [embed])
            if not posted:
                wd_msg = f"VIIKKARIT ({len(new_weeklies)}) ja PARIKISAT ({len(new_doubles)})\n\n" + fmt_weekly_and_doubles(new_weeklies, new_doubles)
                post_to_discord(weekly_thread, token, wd_msg)
        else:
            # Ei uusia viikkokisoja/parikisoja -> lähetetään silti päivittäinen yhteenveto
            print('Ei uusia viikkokisoja tai parikisoja; lähetetään päivittäinen yhteenveto Discordiin')
            embed = build_weekly_embed(weekly_display_list, doubles_list)
            posted = post_embeds_to_discord(weekly_thread, token, [embed])
            if not posted:
                wd_msg = f"VIIKKARIT ({len(weekly_display_list)}) ja PARIKISAT ({len(doubles_list)})\n\n" + fmt_weekly_and_doubles(weekly_display_list, doubles_list)
                post_to_discord(weekly_thread, token, wd_msg)

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
    This mirrors komento_koodit.check_registration + post_pending_registration logic but
    keeps it inside this process to avoid subprocesses.
    """
    try:
        import komento_koodit.check_registration as reg_mod
        import komento_koodit.post_pending_registration as post_mod
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


def _run_capacity_scan_and_alerts_once(base_dir):
    """Suorita kapasiteettiskannaus ja hälytteen päivitys kerran.

    Tämä päivittää CAPACITY_SCAN_RESULTS.json- ja CAPACITY_ALERTS.json-tiedostot
    ajankohtaisiksi, jotta PDGA-yhteenvedot ja !paikat-komento näyttävät tuoreet
    lukemat myös kertaluonteisissa ajoissa.
    """
    try:
        import run_capacity_scan as rcs
        try:
            rcs.main()
        except Exception as e:
            print('Capacity scan failed:', e)
    except Exception as e:
        print('Failed to import run_capacity_scan:', e)

    try:
        from scripts import update_alerts_from_scan as uas
        try:
            uas.main()
        except Exception as e:
            print('Update alerts from scan failed:', e)
    except Exception as e:
        print('Failed to import update_alerts_from_scan:', e)


def start_capacity_worker(base_dir, interval_seconds: int):
    """Run capacity scan + alert generation periodically in background.
    Calls `_run_capacity_scan_and_alerts_once` in a loop.
    """
    def worker():
        while True:
            try:
                _run_capacity_scan_and_alerts_once(base_dir)
            except Exception as e:
                print('Capacity worker error:', e)
            time.sleep(max(10, int(interval_seconds)))
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


def _check_new_pdga_discs_once(base_dir):
    """Check PDGA discs CSV export for newly approved discs and post to Discord.

    Uses a local JSON file (KNOWN_PDGA_DISCS_FILE) to remember which
    certification numbers/models have already been seen. On the very first run
    (no known file), it will initialise the file but will NOT post anything to
    avoid spamming historical discs.
    """
    url = 'https://www.pdga.com/technical-standards/equipment-certification/discs/export'
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print('No DISCORD_TOKEN; skipping PDGA discs check')
        return

    known_path = os.path.join(base_dir, KNOWN_PDGA_DISCS_FILE)
    first_run = False
    try:
        with open(known_path, 'r', encoding='utf-8') as f:
            known_list = json.load(f) or []
    except FileNotFoundError:
        known_list = []
        first_run = True
    except Exception:
        known_list = []

    known_keys = set(str(k) for k in known_list)

    try:
        resp = requests.get(url, timeout=30)
    except Exception as e:
        print('Failed to fetch PDGA discs CSV:', e)
        return

    if resp.status_code != 200 or not resp.text:
        print('PDGA discs CSV fetch returned status', resp.status_code)
        return

    text = resp.text
    try:
        rows = list(csv.DictReader(text.splitlines()))
    except Exception as e:
        print('Failed to parse PDGA discs CSV:', e)
        return

    all_keys = []
    new_rows = []
    for row in rows:
        manu = (row.get('Manufacturer / Distributor') or '').strip()
        model = (row.get('Disc Model') or '').strip()
        cert = (row.get('Certification Number') or '').strip()
        if not manu and not model and not cert:
            continue
        key = cert or f"{manu}|{model}"
        all_keys.append(key)
        if key not in known_keys:
            new_rows.append(row)

    # First run: initialise known file but do not post
    if first_run:
        try:
            with open(known_path, 'w', encoding='utf-8') as f:
                json.dump(all_keys, f, ensure_ascii=False, indent=2)
            print('Initialised known PDGA discs list with', len(all_keys), 'entries')
        except Exception as e:
            print('Failed to initialise known PDGA discs file:', e)
        return

    if not new_rows:
        print('No new PDGA discs found')
        return

    # Build a compact embed listing the newly approved discs (limit to 10)
    lines = []
    for row in new_rows[:10]:
        manu = (row.get('Manufacturer / Distributor') or '').strip()
        model = (row.get('Disc Model') or '').strip()
        disc_class = (row.get('Class') or '').strip()
        approved = (row.get('Approved Date') or '').strip()
        max_weight = (row.get('Max Weight (gr)') or '').strip()
        diameter = (row.get('Diameter (cm)') or '').strip()

        parts = []
        title = model or 'Tuntematon malli'
        parts.append(title)
        if manu:
            parts.append(f'Valmistaja: {manu}')
        if approved:
            parts.append(f'Hyväksytty: {approved}')
        if disc_class:
            parts.append(f'Luokka: {disc_class}')
        if max_weight:
            parts.append(f'Max paino: {max_weight} g')
        if diameter:
            parts.append(f'Halkaisija: {diameter} cm')

        lines.append('\n'.join(parts))

    if len(new_rows) > 10:
        lines.append(f'...ja {len(new_rows)-10} muuta uutta kiekkoa')

    desc = '\n\n'.join(lines)

    target = DISCORD_DISCS_THREAD_ID or os.environ.get('DISCORD_PDGA_THREAD') or os.environ.get('DISCORD_CHANNEL_ID')
    if not target:
        print('No thread/channel configured for PDGA discs alerts; skipping post')
    else:
        embed = {
            'title': 'Uusia PDGA-hyväksyttyjä kiekkoja',
            'description': desc,
            'color': 5763714,
        }
        try:
            ok = post_embeds_to_discord(target, token, [embed])
            if ok:
                print('Posted new PDGA discs alert to Discord')
            else:
                print('Failed to post new PDGA discs alert')
        except Exception as e:
            print('Exception while posting PDGA discs alert:', e)

    # Update known file with all current keys
    try:
        with open(known_path, 'w', encoding='utf-8') as f:
            json.dump(all_keys, f, ensure_ascii=False, indent=2)
        print('Updated known PDGA discs file with', len(all_keys), 'entries')
    except Exception as e:
        print('Failed to update known PDGA discs file:', e)


def start_pdga_discs_worker(base_dir, interval_seconds: int):
    """Background worker that periodically checks for new PDGA discs."""
    def worker():
        while True:
            try:
                _check_new_pdga_discs_once(base_dir)
            except Exception as e:
                print('PDGA discs worker error:', e)
            time.sleep(max(600, int(interval_seconds)))

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


def start_daily_scheduler_thread(hour: int, minute: int, interval_minutes: float = 5.0):
    """Start a background thread that runs `run_once()` once per day after the given hour:minute.

    This is used when the bot runs with presence/command listener instead of --daemon.
    The thread is a daemon and will not block process exit.
    """
    def sched_worker():
        global LAST_DIGEST_DATE
        while True:
            try:
                now = datetime.now()
                today = now.date()
                if LAST_DIGEST_DATE != today:
                    if (now.hour > hour) or (now.hour == hour and now.minute >= minute):
                        try:
                            print(f"[SCHED] Triggering daily digest at {now:%Y-%m-%d %H:%M}")
                            run_once()
                            try:
                                _run_registration_check_once(BASE_DIR)
                            except Exception as e:
                                print('Registration check failed after scheduled run_once:', e)
                            LAST_DIGEST_DATE = today
                        except Exception as e:
                            print('Scheduled run_once failed:', e)
            except Exception as e:
                print('Scheduler worker exception:', e)
            time.sleep(max(30, int(interval_minutes * 60)))

    t = threading.Thread(target=sched_worker, daemon=True)
    t.start()
    return t


def main():
    import argparse
    parser = argparse.ArgumentParser(description='metrixDiscordBot orchestrator')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--daemon', action='store_true', help='Run continuously')
    parser.add_argument('--presence', action='store_true', help='Start Discord gateway client to show bot as online (requires discord.py and valid token)')
    parser.add_argument('--interval-minutes', type=float, default=float(os.environ.get('METRIX_INTERVAL_MINUTES', '120')),
                        help='Interval between runs when --daemon (minutes)')
    parser.add_argument('--times', type=int, default=1, help='When used with --once, run the orchestrator this many times in sequence')
    args = parser.parse_args()

    # Ensure we treat LAST_DIGEST_DATE as the module-level global throughout main()
    global LAST_DIGEST_DATE

    # Run startup capacity check/posting if token configured
    token = os.environ.get('DISCORD_TOKEN')
    try:
        post_startup_capacity_alerts(BASE_DIR, token)
    except Exception as e:
        print('Startup capacity alert check failed:', e)

    # Optionally run an initial full search on startup. Controlled by env var AUTO_RUN_ON_STARTUP (default 1).
    try:
        auto_start = os.environ.get('AUTO_RUN_ON_STARTUP', '1')
        if auto_start == '1' and not args.once:
            # Run in background so presence and command listener can start quickly
            def _startup_run():
                try:
                    print('[STARTUP] Running initial competition fetch (run_once)')
                    run_once()
                except Exception as e:
                    print('Startup run_once failed:', e)

            thr = threading.Thread(target=_startup_run, daemon=True)
            thr.start()
    except Exception as e:
        print('Failed to schedule startup run:', e)

    # If presence requested, start gateway client now (works for once/daemon modes)
    presence_thread = None
    if args.presence:
        token = os.environ.get('DISCORD_TOKEN')
        if not token:
            print('DISCORD_TOKEN not set; skipping presence and command listener')
        else:
            try:
                from komento_koodit.discord_presence import start_presence
                # run_forever True for daemon mode; if --once, run_forever=False so it disconnects
                # Default status text now matches the LakeusBotti branding;
                # can be overridden with DISCORD_STATUS.
                presence_thread = start_presence(token, status_message=os.environ.get('DISCORD_STATUS', 'LakeusBotti'), run_forever=not args.once)
                try:
                    from komento_koodit.command_handler import start_command_listener
                    start_command_listener(token, prefix='!', run_forever=not args.once)
                except Exception as e:
                    print('Failed to start command listener:', e)
            except Exception as e:
                print('Failed to start presence thread:', e)

            # When presence is started (non-daemon mode), start the daily scheduler
            try:
                if args.presence and not args.daemon:
                    try:
                        start_daily_scheduler_thread(DAILY_DIGEST_HOUR, DAILY_DIGEST_MINUTE)
                    except Exception as e:
                        print('Failed to start daily scheduler thread:', e)

                    # Optionally trigger an immediate digest when presence becomes active
                    # Controlled by RUN_DIGEST_ON_PRESENCE env var (default '1').
                    try:
                        run_on_presence = os.environ.get('RUN_DIGEST_ON_PRESENCE', '1') == '1'
                        if run_on_presence:
                            today = datetime.now().date()
                            if LAST_DIGEST_DATE != today:
                                def _presence_trigger():
                                    try:
                                        print('[PRESENCE] Presence active — running immediate daily digest')
                                        run_once()
                                        try:
                                            _run_registration_check_once(BASE_DIR)
                                        except Exception as e:
                                            print('Registration check failed after presence-triggered run_once:', e)
                                        # Update module-level LAST_DIGEST_DATE without declaring global here
                                        try:
                                            globals()['LAST_DIGEST_DATE'] = datetime.now().date()
                                        except Exception:
                                            pass
                                    except Exception as e:
                                        print('Presence-triggered run_once failed:', e)

                                t = threading.Thread(target=_presence_trigger, daemon=True)
                                t.start()
                    except Exception as e:
                        print('Failed to trigger presence-based digest:', e)
            except Exception:
                pass

    if args.once:
        times = max(1, int(args.times or 1))
        for i in range(times):
            print(f'Run {i+1}/{times}')
            # Päivitä kapasiteettidata ennen jokaista kertaluonteista ajoa,
            # jotta PDGA-yhteenvedot käyttävät tuoreita pelaajamääriä.
            try:
                _run_capacity_scan_and_alerts_once(BASE_DIR)
            except Exception as e:
                print('Capacity scan (once) failed:', e)
            run_once()
            # run registration check once after each run_once when requested
            if args.check_registrations:
                _run_registration_check_once(BASE_DIR)
            if i < times - 1:
                # small delay between runs to avoid hammering upstream
                time.sleep(1)
        return

    if args.daemon:
        # Käynnistetään varsinainen ajastettu daemon-prosessi.
        print('Käynnistetään LakeusBotti')
        print('Päivittäinen kilpailuraportti (PDGA + viikkarit + rekisteröinnit) '
              f"ajetaan noin klo {DAILY_DIGEST_HOUR:02d}:{DAILY_DIGEST_MINUTE:02d}.")
        # start registration worker thread
        try:
            start_registration_worker(BASE_DIR, CHECK_REGISTRATION_INTERVAL)
        except Exception as e:
            print('Failed to start registration worker:', e)
        # start capacity scan worker thread
        try:
            # Default to 1800 seconds (30 minutes) for capacity/paikat checks
            cap_interval = int(os.environ.get('CAPACITY_CHECK_INTERVAL', '1800'))
            start_capacity_worker(BASE_DIR, cap_interval)
            # Tallenna nykyinen arvo, jotta !admin status voi raportoida sen.
            global CURRENT_CAPACITY_INTERVAL
            CURRENT_CAPACITY_INTERVAL = cap_interval
        except Exception as e:
            print('Failed to start capacity worker:', e)
        # start PDGA discs watcher worker thread (default once per day)
        try:
            discs_interval = int(os.environ.get('DISCS_CHECK_INTERVAL', '86400'))
            start_pdga_discs_worker(BASE_DIR, discs_interval)
        except Exception as e:
            print('Failed to start PDGA discs worker:', e)
        # Päivittäinen kilpailudigesti: ajetaan run_once()+rekisteröinnit kerran vuorokaudessa
        # konfiguroidussa kellonajassa (DAILY_DIGEST_HOUR/MINUTE).
        # Käytetään globaalia LAST_DIGEST_DATE-arvoa, jotta admin-komennot
        # voivat nollata tämän tarvittaessa (esim. kellonaikaa muutettaessa).
        last_digest_date = LAST_DIGEST_DATE

        while True:
            now = datetime.now()
            today = now.date()

            # Päivitä paikallinen muuttuja globaalista, jotta mahdollinen
            # admin-komennon tekemä nollaus (LAST_DIGEST_DATE = None)
            # huomioidaan seuraavalla kierroksella.
            last_digest_date = LAST_DIGEST_DATE

            should_run = False
            if last_digest_date != today:
                # Suoritetaan kun nykyinen kellonaika on asetetun ajan jälkeen.
                if (now.hour > DAILY_DIGEST_HOUR or
                        (now.hour == DAILY_DIGEST_HOUR and now.minute >= DAILY_DIGEST_MINUTE)):
                    should_run = True

            if should_run:
                print(f"Running daily digest for {today} at {now:%H:%M}")
                try:
                    run_once()
                    # After updating competition files and known caches, run registration check
                    try:
                        _run_registration_check_once(BASE_DIR)
                    except Exception as e:
                        print('Registration check failed after run_once:', e)
                    last_digest_date = today
                    LAST_DIGEST_DATE = today
                    # Tulosta yhteenvedot taustatyöntekijöiden tarkistusväleistä,
                    # kun kaikki tämän kierroksen tarkistukset on tehty.
                    try:
                        reg_interval = CHECK_REGISTRATION_INTERVAL
                        cap_interval_log = CURRENT_CAPACITY_INTERVAL or CHECK_INTERVAL
                    except Exception:
                        reg_interval = CHECK_REGISTRATION_INTERVAL
                        cap_interval_log = CHECK_INTERVAL

                    discs_interval_log = int(os.environ.get('DISCS_CHECK_INTERVAL', '86400'))
                    mins_reg = reg_interval / 60.0
                    mins_cap = cap_interval_log / 60.0
                    hours_discs = discs_interval_log / 3600.0
                    print(f"Rekisteröintien tarkistus käynnissä (väli {reg_interval} s (~{mins_reg:.1f} min).")
                    print(f"Kapasiteettiskannaus ja -hälytykset käynnissä (väli {cap_interval_log} s ~{mins_cap:.1f} min).")
                    print(f"PDGA-kiekkojen uutuustarkistus käynnissä (väli {discs_interval_log} s ~{hours_discs:.1f} h).")
                except Exception as e:
                    print('Run failed in daemon loop:', e)

            # sleep interval: tarkistetaan tilanne esim. 5–10 minuutin välein
            mins = max(0.1, args.interval_minutes)
            secs = mins * 60.0
            next_check = datetime.now() + timedelta(minutes=mins)
            print(f"Seuraava tarkistus klo {next_check:%H:%M}")
            time.sleep(secs)


if __name__ == '__main__':
    main()
