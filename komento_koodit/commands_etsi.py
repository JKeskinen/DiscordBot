import os
import json
import re
from typing import Any, List
import sqlite3
from datetime import datetime

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover
    discord = None  # type: ignore[assignment]

from .date_utils import normalize_date_string
from .metrix_utils import fetch_metrix_canonical_date


async def handle_etsi(message: Any, parts: Any) -> None:
    """Handle the !etsi command (search competitions)."""
    query = " ".join(parts[1:]).strip().lower() if len(parts) > 1 else None
    if not query:
        try:
            await message.channel.send("Käyttö: !etsi <alue tai rata> — esimerkki: !etsi helsinki")
        except Exception:
            pass
        return

    base_dir = os.path.abspath(os.path.dirname(__file__))
    root = os.path.abspath(os.path.join(base_dir, ".."))

    candidate_files = [
        "PDGA.json",
        "VIIKKOKISA.json",
        "known_weekly_competitions.json",
        "known_pdga_competitions.json",
        "known_doubles_competitions.json",
        "DOUBLES.json",
    ]

    from . import data_store as _ds
    entries: List[Any] = []
    for fname in candidate_files:
        try:
            data = _ds.load_category(os.path.splitext(fname)[0])
        except Exception:
            data = []
        try:
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        item["_src_file"] = fname
                    entries.append(item)
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict):
                                item["_src_file"] = fname
                            entries.append(item)
                    else:
                        if isinstance(v, dict):
                            v["_src_file"] = fname
                        entries.append(v)
        except Exception:
            continue

    if not entries:
        await message.channel.send("Kilpailutietokantaa ei löytynyt.")
        return

    # Special case: class lookup -> !etsi luokka <code>
    # Supports both textual class codes (e.g. 'ma3') and numeric rating thresholds (e.g. '896').
    try:
        if query.startswith('luokka'):
            # extract target after 'luokka'
            parts_after = query.split()
            target = parts_after[1] if len(parts_after) > 1 else (parts[2] if len(parts) > 2 else None)
            if not target:
                await message.channel.send('Käyttö: !etsi luokka <koodi tai rating> — esim. !etsi luokka ma3 tai !etsi luokka 896')
                return

            target = str(target).strip().lower()
            is_rating_query = target.isdigit()
            rating_threshold = int(target) if is_rating_query else None

            # load cache (new scanner writes an object with 'results' and
            # a reference to 'class_definitions.json')
            cache_path = os.path.join(root, 'CAPACITY_SCAN_RESULTS.json')
            try:
                with open(cache_path, 'r', encoding='utf-8') as cf:
                    cache_raw = json.load(cf)
            except Exception:
                cache_raw = []
            # normalize to list of records
            if isinstance(cache_raw, dict) and 'results' in cache_raw:
                cache = cache_raw.get('results') or []
            elif isinstance(cache_raw, list):
                cache = cache_raw
            else:
                cache = []

            # load canonical class definitions if present
            class_defs_map = {}
            try:
                defs_path = os.path.join(root, 'class_definitions.json')
                if os.path.exists(defs_path):
                    with open(defs_path, 'r', encoding='utf-8') as df:
                        class_defs_map = json.load(df) or {}
            except Exception:
                class_defs_map = {}

            results = []
            loop = __import__('asyncio').get_running_loop()

            async def _live_check(url: str):
                try:
                    def _run():
                        try:
                            if capacity_mod is None:
                                return None
                            return capacity_mod.check_competition_capacity(url, timeout=12)
                        except Exception:
                            return None
                    return await loop.run_in_executor(None, _run)
                except Exception:
                    return None

            total_entries = len(entries)
            try:
                await message.channel.send(f'Aloitetaan luokkahaku: {total_entries} kilpailua tarkistetaan...')
            except Exception:
                pass

            processed = 0

            for e in entries:
                try:
                    processed += 1
                    if processed % 10 == 0:
                        try:
                            await message.channel.send(f'Luokkahaku: {processed}/{total_entries} käsitelty...')
                        except Exception:
                            pass
                    title = e.get('title') or e.get('name') or ''
                    url = e.get('url') or e.get('link') or ''
                    date_text = e.get('date') or e.get('start_date') or ''

                    matched = []

                    # try cache first
                    if cache and url:
                        for rec in cache:
                            try:
                                if rec.get('url') == url or str(rec.get('id')) == str(e.get('id')):
                                    # records may contain only per-event `class_counts`
                                    # and not full `class_info`; normalize accordingly.
                                    capr = (rec.get('capacity_result') or {})
                                    ci = capr.get('class_info') or rec.get('class_info') or {}
                                    if not isinstance(ci, dict):
                                        ci = {}
                                    classes_def = ci.get('classes') or []
                                    # prefer explicit class_counts field (top-level or under capacity_result)
                                    ccnts = capr.get('class_counts') or rec.get('class_counts') or ci.get('class_counts') or {}
                                    if not isinstance(ccnts, dict):
                                        ccnts = {}
                                    # if no per-event class definitions, fall back to canonical
                                    if not classes_def and class_defs_map:
                                        # convert canonical mapping to list of class dicts
                                        classes_def = []
                                        try:
                                            for code, info in class_defs_map.items():
                                                classes_def.append({'code': code, 'name': info.get('display_name') or info.get('name') or '', 'eligibility': info.get('rating_limit')})
                                        except Exception:
                                            classes_def = []
                                    # textual code match
                                    if not is_rating_query:
                                        for k, v in ccnts.items():
                                            try:
                                                if str(k).strip().lower() == target:
                                                    matched.append((k, None, int(v or 0)))
                                            except Exception:
                                                continue
                                    else:
                                        # rating threshold: inspect class definitions
                                        for cl in classes_def:
                                            try:
                                                text = ' '.join([str(cl.get('eligibility') or ''), str(cl.get('name') or ''), str(cl.get('code') or '')]).lower()
                                                nums = re.findall(r'(\d{3,4})', text)
                                                for n in nums:
                                                    try:
                                                        if rating_threshold is not None and int(n) >= rating_threshold:
                                                            key = cl.get('code') or cl.get('name') or ''
                                                            cnt = ccnts.get(key) if isinstance(ccnts, dict) else None
                                                            cnt_val = int(cnt) if cnt is not None else None
                                                            matched.append((key, cl.get('name'), cnt_val))
                                                            break
                                                    except Exception:
                                                        continue
                                            except Exception:
                                                continue
                                    break
                            except Exception:
                                continue

                    # fallback live check when no cached matches
                    if not matched and url and capacity_mod is not None:
                        cap_res = await _live_check(url)
                        if isinstance(cap_res, dict):
                            live_ci = cap_res.get('class_info') or {}
                            capr_live = (cap_res or {})
                            live_ci = capr_live.get('class_info') or {}
                            classes_def = live_ci.get('classes') or []
                            ccnts = capr_live.get('class_counts') or live_ci.get('class_counts') or {}
                            if not isinstance(ccnts, dict):
                                ccnts = {}
                            if not classes_def and class_defs_map:
                                classes_def = []
                                try:
                                    for code, info in class_defs_map.items():
                                        classes_def.append({'code': code, 'name': info.get('display_name') or info.get('name') or '', 'eligibility': info.get('rating_limit')})
                                except Exception:
                                    classes_def = []
                            if not is_rating_query:
                                for k, v in ccnts.items():
                                    try:
                                        if str(k).strip().lower() == target:
                                            matched.append((k, None, int(v or 0)))
                                    except Exception:
                                        continue
                            else:
                                for cl in classes_def:
                                    try:
                                        text = ' '.join([str(cl.get('eligibility') or ''), str(cl.get('name') or ''), str(cl.get('code') or '')]).lower()
                                        nums = re.findall(r'(\d{3,4})', text)
                                        for n in nums:
                                            try:
                                                if rating_threshold is not None and int(n) >= rating_threshold:
                                                    key = cl.get('code') or cl.get('name') or ''
                                                    cnt = ccnts.get(key) if isinstance(ccnts, dict) else None
                                                    cnt_val = int(cnt) if cnt is not None else None
                                                    matched.append((key, cl.get('name'), cnt_val))
                                                    break
                                            except Exception:
                                                continue
                                    except Exception:
                                        continue

                    if matched:
                        for key, name, cnt in matched:
                            cap_display = ''
                            try:
                                if url:
                                    cap_display = await _get_capacity_display_local(url)
                            except Exception:
                                cap_display = ''
                            results.append((title, url, key or name or '', cnt, cap_display, date_text))
                except Exception:
                    continue

            if not results:
                try:
                    await message.channel.send(f'Luokkaa "{target}" ei löytynyt avoimista ilmoittautumisista.')
                except Exception:
                    pass
                return

            # format output
            # map known class codes to human-friendly color names
            CODE_COLOR_MAP = {
                'RPA': 'Gold',
                'RAD': 'White',
                'RAE': 'Red',
                'RAF': 'Green',
                'RAG': 'Purple'
            }
            # map codes to PDGA rating thresholds or notes
            CODE_RATING_MAP = {
                'RPA': 'kaikki',
                'RAD': '<935',
                'RAE': '<900',
                'RAF': '<850',
                'RAG': '<800'
            }

            def _display_code_label(code: str) -> str:
                if not code:
                    return ''
                s = str(code).strip()
                up = s.upper()
                color = CODE_COLOR_MAP.get(up)
                rating = CODE_RATING_MAP.get(up)
                if color and rating:
                    return f'{color} ({s}): {rating}'
                if color:
                    return f'{color} ({s})'
                if rating:
                    return f'{s}: {rating}'
                return s

            out_lines = []
            if is_rating_query:
                # results elements: (title,url,key,cnt,cap_display,date)
                for title, url, key, cnt, cap_disp, date_text in sorted(results, key=lambda it: (-(it[3] or 0), it[0])):
                    date_part = f' — {date_text}' if date_text else ''
                    cap_part = f' — {cap_disp.strip()}' if cap_disp else ''
                    key_display = _display_code_label(key)
                    if url:
                        out_lines.append(f'• [{title}]({url}) — luokat, rating>={target}: {key_display} ({cnt or 0}){cap_part}{date_part}')
                    else:
                        out_lines.append(f'• {title} — luokat, rating>={target}: {key_display} ({cnt or 0}){cap_part}{date_part}')
            else:
                for title, url, cnt, cap_disp, date_text in sorted(results, key=lambda it: (-(it[2] or 0), it[0])):
                    date_part = f' — {date_text}' if date_text else ''
                    cap_part = f' — {cap_disp.strip()}' if cap_disp else ''
                    target_display = _display_code_label(target)
                    if url:
                        out_lines.append(f'• [{title}]({url}) — luokka {target_display}: {cnt} pelaajaa{cap_part}{date_part}')
                    else:
                        out_lines.append(f'• {title} — luokka {target_display}: {cnt} pelaajaa{cap_part}{date_part}')

            # send chunked
            max_len = 1900
            cur = []
            cur_len = 0
            for ln in out_lines:
                if cur_len + len(ln) + 1 > max_len and cur:
                    try:
                        Embed_cls = getattr(discord, 'Embed', None)
                        if Embed_cls:
                            embed = Embed_cls(title=f'Luokka {target} — löydöt', description='\n'.join(cur))
                            await message.channel.send(embed=embed)
                        else:
                            await message.channel.send('\n'.join(cur))
                    except Exception:
                        await message.channel.send('\n'.join(cur))
                    cur = []
                    cur_len = 0
                cur.append(ln)
                cur_len += len(ln) + 1
            if cur:
                try:
                    Embed_cls = getattr(discord, 'Embed', None)
                    if Embed_cls:
                        embed = Embed_cls(title=f'Luokka {target} — löydöt', description='\n'.join(cur))
                        await message.channel.send(embed=embed)
                    else:
                        await message.channel.send('\n'.join(cur))
                except Exception:
                    await message.channel.send('\n'.join(cur))
            return
    except Exception:
        # continue to normal text/area search on any failure
        pass

    fields = [
        "title",
        "name",
        "location",
        "venue",
        "track",
        "area",
        "place",
        "city",
        "region",
        "kind",
    ]
    matches: List[Any] = []
    q = query.lower()
    for e in entries:
        try:
            hay = " ".join(str(e.get(f, "") or "") for f in fields).lower()
            if q in hay:
                matches.append(e)
        except Exception:
            continue

    # remove duplicates: prefer unique by (url or title, normalized date)
    try:
        # normalize dates using Finnish day-first convention
        prefer_month_first_global = False
        unique: List[Any] = []
        seen = set()
        for e in matches:
            url = e.get("url") or ""
            title = (e.get("title") or e.get("name") or "").strip()
            date_field = e.get("date") or e.get("start_date") or ""
            if date_field:
                date_norm = normalize_date_string(str(date_field))
            else:
                date_norm = ""
            key = (url or title, date_norm)
            if key in seen:
                continue
            seen.add(key)
            unique.append(e)
        matches = unique
    except Exception:
        # if dedupe fails for any reason, keep original matches
        pass

    if not matches:
        await message.channel.send("Ei kilpailuja löytynyt haulla.")
        return

    lines: List[str] = []
    for e in matches:
        title = e.get("title") or e.get("name") or ""
        url = e.get("url") or ""
        date_text = ""
        try:
            if e.get("opening_soon") and e.get("opens_in_days") is not None:
                date_text = f'avautuu {int(e.get("opens_in_days"))} pv'
            else:
                date_field = e.get("date") or e.get("start_date")
                if date_field:
                    # Try to normalize existing date; if ambiguous or missing, fetch canonical date from Metrix
                    date_text = normalize_date_string(str(date_field))
                    # If the date_text still looks like year with two-digit or ambiguous form, prefer fetching
                    if (not date_text) and e.get("url"):
                        fetched = fetch_metrix_canonical_date(str(e.get("url") or ""))
                        if fetched:
                            date_text = fetched
                    # If normalization produced MM/DD/YYYY accidentally (e.g. 01/03/2026 meaning Jan 3), still prefer Metrix
                    if e.get("url") and re.search(r"\d{1,2}/\d{1,2}/\d{4}", str(date_field)):
                        fetched = fetch_metrix_canonical_date(str(e.get("url") or ""))
                        if fetched:
                            date_text = fetched
                else:
                    m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{2,4})", title)
                    if m:
                        date_text = normalize_date_string(m.group(1))
        except Exception:
            date_text = ""

        kind = (e.get("kind") or "").strip()
        if "VIIKKOKISA" in kind.upper():
            kind_display = ""
        else:
            kind_display = f" ({kind})" if kind else ""
        date_display = f" — {date_text}" if date_text else ""

        if url:
            lines.append(f"• [{title}]({url}){kind_display}{date_display}")
        else:
            lines.append(f"• {title}{kind_display}{date_display}")

    # send results chunked
    max_len = 1900
    cur: List[str] = []
    cur_len = 0
    for ln in lines:
        if cur_len + len(ln) + 1 > max_len and cur:
            try:
                Embed_cls = getattr(discord, "Embed", None)
                if Embed_cls:
                    embed = Embed_cls(title="Löydetyt kilpailut:", description="\n".join(cur))
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send("\n".join(cur))
            except Exception:
                await message.channel.send("\n".join(cur))
            cur = []
            cur_len = 0
        cur.append(ln)
        cur_len += len(ln) + 1

    if cur:
        try:
            Embed_cls = getattr(discord, "Embed", None)
            if Embed_cls:
                embed = Embed_cls(title="Löydetyt kilpailut:", description="\n".join(cur))
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("\n".join(cur))
        except Exception:
            await message.channel.send("\n".join(cur))


try:
    from . import check_capacity as capacity_mod
except Exception:
    capacity_mod = None


async def _get_capacity_display_local(url: str) -> str:
    """Return capacity string like " (35/72)" or " (35)" using check_capacity helper."""
    if not url:
        return ""
    if capacity_mod is None or not hasattr(capacity_mod, "check_competition_capacity"):
        return ""

    try:
        loop = __import__('asyncio').get_running_loop()
    except Exception:
        return ""

    def _run():
        try:
            if capacity_mod is None or not hasattr(capacity_mod, 'check_competition_capacity'):
                return None
            return capacity_mod.check_competition_capacity(url, timeout=10)
        except Exception:
            return None

    cap = await loop.run_in_executor(None, _run)
    if not isinstance(cap, dict):
        return ""

    reg = cap.get('registered')
    lim = cap.get('limit')
    try:
        reg_int = int(reg) if reg is not None else None
    except Exception:
        reg_int = None
    try:
        lim_int = int(lim) if lim is not None else None
    except Exception:
        lim_int = None

    # If registered is unknown but limit exists, show 0/limit per user request
    if reg_int is None:
        if lim_int is not None and lim_int > 0:
            return f" (0/{lim_int})"
        return ""
    if lim_int is not None and lim_int > 0:
        return f" ({reg_int}/{lim_int})"
    return f" ({reg_int})"


async def handle_kisa(message: Any, parts: Any) -> None:
    """Handle !kisa subcommands. Supported: `pdga` (list PDGA events by tier+area), `viikkari` (delegate to viikkarit)."""
    if not parts or len(parts) < 2:
        try:
            await message.channel.send("Käyttö: !kisa pdga | !kisa viikkari")
        except Exception:
            pass
        return

    sub = str(parts[1] or '').strip().lower()
    # delegate viikkari to existing module if available
    if sub in ('viikkari', 'viikkokisa', 'viikkokisat'):
        try:
            from . import commands_viikkarit as viikkarit_mod

            if hasattr(viikkarit_mod, 'handle_viikkarit'):
                await viikkarit_mod.handle_viikkarit(message, parts[1:])
                return
        except Exception:
            pass

        # fallback: tell user it's unavailable
        try:
            await message.channel.send('Viikkarit-komentoa ei voi suorittaa (moduuli puuttuu).')
        except Exception:
            pass
        return

    if sub == 'pdga':
        # list PDGA.json competitions grouped by tier and area/region
        base_dir = os.path.abspath(os.path.dirname(__file__))
        root = os.path.abspath(os.path.join(base_dir, '..'))
        # prefer reading PDGA list from sqlite json_store for speed
        try:
            from . import data_store as _ds
            data = _ds.load_category('PDGA')
        except Exception:
            # fallback to file if sqlite not available
            path = os.path.join(root, 'PDGA.json')
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                try:
                    await message.channel.send('PDGA-dataa ei löytynyt.')
                except Exception:
                    pass
                return

        if not isinstance(data, list):
            try:
                await message.channel.send('PDGA-data on odottamatonta muotoa.')
            except Exception:
                pass
            return

        # Group by tier only and present in user-defined order (A,B,C,L,X,Other)
        from collections import defaultdict

        tiers_map: dict[str, list[dict]] = defaultdict(list)
        for e in data:
            title = str(e.get('title') or e.get('name') or '')
            # skip per-round entries
            if 'kierros' in title.lower():
                continue
            raw_tier = str(e.get('tier') or '').strip()
            if not raw_tier:
                code = 'Other'
            else:
                code = raw_tier.split('-')[0].strip()
                if not code:
                    code = raw_tier
            tiers_map[code].append(e)

        # prepare quick DB lookup for existing capacity snapshots (file fallback)
        db_path = os.path.join(root, 'data', 'discordbot.db')
        try:
            db_conn = sqlite3.connect(db_path)
            db_cur = db_conn.cursor()
        except Exception:
            db_conn = None
            db_cur = None
        # also load CAPACITY_SCAN_RESULTS.json for more reliable counts when available
        capacity_by_url = {}
        capacity_by_id = {}
        try:
            cap_path = os.path.join(root, 'CAPACITY_SCAN_RESULTS.json')
            with open(cap_path, 'r', encoding='utf-8') as f:
                cap_data = json.load(f) or []
            for item in cap_data:
                cid = str(item.get('id') or '')
                url = item.get('url') or ''
                cap = item.get('capacity_result') or {}
                try:
                    reg = int(cap.get('registered')) if cap.get('registered') is not None else None
                except Exception:
                    reg = None
                try:
                    lim = int(cap.get('limit')) if cap.get('limit') is not None else None
                except Exception:
                    lim = None
                info = {'registered': reg, 'limit': lim}
                if cid:
                    capacity_by_id[cid] = info
                if url:
                    capacity_by_url[url] = info
        except Exception:
            pass

        # desired tier order and ordering key
        preferred = ['A', 'B', 'C', 'L', 'X']

        def tier_order_key(k: str) -> tuple[int, str]:
            if k in preferred:
                return (0, preferred.index(k))
            if k == 'Other':
                return (2, k)
            return (1, k)

        # For each tier, send a separate message (title contains tier). This ensures one tier per message.
        max_len = 1900
        Embed_cls = getattr(discord, 'Embed', None)

        sent_any = False
        # For consistent output order, sort events within a tier by date (future first)
        for tier_code in sorted(tiers_map.keys(), key=tier_order_key):
            events = tiers_map[tier_code]
            if not events:
                continue
            header = f"{tier_code}-tier" if tier_code != 'Other' else 'Other'
            # Build list of (date_obj, event) for sorting and filtering (only future events)
            evs_with_dates = []
            for e in events:
                raw_date_text = str(e.get('date') or '')
                date_text = ''
                date_obj = None
                if raw_date_text:
                    try:
                        date_norm = normalize_date_string(raw_date_text, prefer_month_first=True)
                        date_text = date_norm
                        # parse date part (ignore time)
                        ds = date_norm.split()[0]
                        try:
                            date_obj = datetime.strptime(ds, '%d.%m.%Y').date()
                        except Exception:
                            date_obj = None
                    except Exception:
                        date_text = raw_date_text
                # Only include upcoming events (today or later)
                today = datetime.now().date()
                if date_obj is not None and date_obj < today:
                    continue
                evs_with_dates.append((date_obj or datetime.max.date(), e, date_text))

            # sort by date then title
            evs_with_dates.sort(key=lambda x: (x[0], str(x[1].get('title') or x[1].get('name') or '')))

            lines = [f"**{header}:**"]
            for _date_obj, e, date_text in evs_with_dates:
                title = str(e.get('title') or e.get('name') or '')
                url = str(e.get('url') or '')
                # Determine capacity display: prefer CAPACITY_SCAN_RESULTS.json, then DB.
                # If those are missing, attempt a live capacity check (may add latency).
                cap_part = ''
                try:
                    cid = str(e.get('id') or '')
                    info = None
                    if url and url in capacity_by_url:
                        info = capacity_by_url.get(url)
                    elif cid and cid in capacity_by_id:
                        info = capacity_by_id.get(cid)
                    elif db_cur is not None and url:
                        db_cur.execute('SELECT registered, cap_limit FROM competitions WHERE url = ? LIMIT 1', (url,))
                        row = db_cur.fetchone()
                        if row:
                            try:
                                reg_i = int(row[0]) if row[0] is not None else None
                            except Exception:
                                reg_i = None
                            try:
                                lim_i = int(row[1]) if row[1] is not None else None
                            except Exception:
                                lim_i = None
                            info = {'registered': reg_i, 'limit': lim_i}
                    # If still missing, try a live capacity check using check_capacity module
                    if not info:
                        try:
                            from . import check_capacity as capacity_mod_local
                        except Exception:
                            capacity_mod_local = None
                        if url and capacity_mod_local is not None and hasattr(capacity_mod_local, 'check_competition_capacity'):
                            try:
                                loop = __import__('asyncio').get_running_loop()
                                def _run_live():
                                    try:
                                        return capacity_mod_local.check_competition_capacity(url, timeout=10)
                                    except Exception:
                                        return None
                                live = await loop.run_in_executor(None, _run_live)
                                if isinstance(live, dict):
                                    try:
                                        reg_live = int(live.get('registered')) if live.get('registered') is not None else None
                                    except Exception:
                                        reg_live = None
                                    try:
                                        lim_live = int(live.get('limit')) if live.get('limit') is not None else None
                                    except Exception:
                                        lim_live = None
                                    info = {'registered': reg_live, 'limit': lim_live}
                            except Exception:
                                pass
                    if info:
                        reg_i = info.get('registered')
                        lim_i = info.get('limit')
                        if reg_i is None and lim_i is not None:
                            cap_part = f" ({0}/{lim_i})"
                        elif reg_i is not None and lim_i is not None:
                            cap_part = f" ({reg_i}/{lim_i})"
                        elif reg_i is not None:
                            cap_part = f" ({reg_i})"
                except Exception:
                    cap_part = ''
                # Format line: include date_text inline
                if date_text:
                    date_disp = date_text
                else:
                    date_disp = ''
                line = f"- {title}{cap_part}"
                if date_disp:
                    line += f" — {date_disp}"
                if url:
                    # make title a link if possible
                    if cap_part:
                        # replace title in line with link
                        line = line.replace(title, f"[{title}]({url})", 1)
                    else:
                        line = f"- [{title}]({url})"
                        if date_disp:
                            line += f" — {date_disp}"
                lines.append(line)
            # chunk and send this tier's message(s)
            cur = []
            cur_len = 0
            for ln in '\n'.join(lines).split('\n'):
                if cur_len + len(ln) + 1 > max_len and cur:
                    try:
                        if Embed_cls:
                            embed = Embed_cls(title=f'PDGA - {header}', description='\n'.join(cur))
                            await message.channel.send(embed=embed)
                        else:
                            await message.channel.send('\n'.join(cur))
                    except Exception:
                        await message.channel.send('\n'.join(cur))
                    cur = []
                    cur_len = 0
                cur.append(ln)
                cur_len += len(ln) + 1
            if cur:
                try:
                    if Embed_cls:
                        embed = Embed_cls(title=f'PDGA - {header}', description='\n'.join(cur))
                        await message.channel.send(embed=embed)
                    else:
                        await message.channel.send('\n'.join(cur))
                except Exception:
                    await message.channel.send('\n'.join(cur))
            sent_any = True

        if not sent_any:
            try:
                await message.channel.send('Ei PDGA-kisoja löydetty.')
            except Exception:
                pass
        # close DB connection if opened
        try:
            if db_conn is not None:
                db_conn.close()
        except Exception:
            pass
        return

    # unknown subcommand
    try:
        await message.channel.send('Tuntematon alikomento. Käyttö: !kisa pdga | !kisa viikkari')
    except Exception:
        pass
