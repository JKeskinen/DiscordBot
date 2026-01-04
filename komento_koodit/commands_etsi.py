import os
import json
import re
from typing import Any, List

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

    entries: List[Any] = []
    for fname in candidate_files:
        path = os.path.join(root, fname)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                item["_src_file"] = fname
                            entries.append(item)
                    elif isinstance(data, dict):
                        # some files may be dicts mapping ids to entries or lists
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
            # ignore bad files
            continue

    if not entries:
        await message.channel.send("Kilpailutietokantaa ei löytynyt.")
        return

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

    if reg_int is None:
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

        # Group by region/area (maakunta) and filter out per-round entries like '1. Kierros' / '2. Kierros'.
        from collections import defaultdict

        groups: dict[str, list[dict]] = defaultdict(list)
        for e in data:
            title = str(e.get('title') or e.get('name') or '')
            # skip '1. Kierros' / '2. Kierros' round entries
            if 'kierros' in title.lower():
                continue
            area = str(e.get('region') or e.get('area') or '').strip() or 'Muu'
            groups[area].append(e)

        lines: list[str] = []
        # sort areas with 'Muu' last
        def area_key(n: str) -> tuple[int, str]:
            return (1, n.lower()) if n == 'Muu' else (0, n.lower())

        for area_name in sorted(groups.keys(), key=area_key):
            lines.append(f"**{area_name}**")
            area_events = sorted(groups[area_name], key=lambda ev: str(ev.get('date') or ''))
            for e in area_events:
                title = str(e.get('title') or e.get('name') or '')
                url = str(e.get('url') or '')
                date_text = str(e.get('date') or '')

                # capacity: prefer check_capacity extraction, but format without parentheses
                cap_str = ''
                if url:
                    try:
                        cap_res = await _get_capacity_display_local(url)
                        # _get_capacity_display_local returns ' (reg/lim)' or ' (reg)'
                        if cap_res:
                            cap_str = cap_res.strip()
                            if cap_str.startswith('(') and cap_str.endswith(')'):
                                cap_str = cap_str[1:-1]
                    except Exception:
                        cap_str = ''

                suffix = f' — {date_text}' if date_text else ''
                cap_suffix = f' — {cap_str}' if cap_str else ''
                if url:
                    lines.append(f"• [{title}]({url}){suffix}{cap_suffix}")
                else:
                    lines.append(f"• {title}{suffix}{cap_suffix}")
            lines.append('')

        desc = '\n'.join(lines).strip()
        if not desc:
            try:
                await message.channel.send('Ei PDGA-kisoja löydetty.')
            except Exception:
                pass
            return

        # send chunked
        max_len = 1900
        cur = []
        cur_len = 0
        for ln in desc.split('\n'):
            if cur_len + len(ln) + 1 > max_len and cur:
                try:
                    Embed_cls = getattr(discord, 'Embed', None)
                    if Embed_cls:
                        embed = Embed_cls(title='PDGA-kisat', description='\n'.join(cur))
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
                    embed = Embed_cls(title='PDGA-kisat', description='\n'.join(cur))
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send('\n'.join(cur))
            except Exception:
                await message.channel.send('\n'.join(cur))
        return

    # unknown subcommand
    try:
        await message.channel.send('Tuntematon alikomento. Käyttö: !kisa pdga | !kisa viikkari')
    except Exception:
        pass
