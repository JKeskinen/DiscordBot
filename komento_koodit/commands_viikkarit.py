import os
import asyncio
from datetime import datetime, date, timedelta
from .date_utils import normalize_date_string
from typing import Any, List
try:
    import settings
except Exception:
    settings = None

# Defaults that may be overridden by settings.py
DEFAULT_WEEKLY_LOCATION = getattr(settings, 'WEEKLY_LOCATION', 'Etelä-Pohjanmaa') if settings is not None else 'Etelä-Pohjanmaa'
DEFAULT_MAX_WEEKLY_ITEMS = int(getattr(settings, 'DEFAULT_MAX_WEEKLY_LIST', 40)) if settings is not None else 40

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover
    discord = None  # type: ignore[assignment]

try:
    from . import data_store
except Exception:  # pragma: no cover
    data_store = None  # type: ignore[assignment]

try:
    from . import check_capacity as capacity_mod
except Exception:  # pragma: no cover
    capacity_mod = None  # type: ignore[assignment]


async def _get_capacity_display(url: str) -> str:
    """Palauta osallistujamäärän näyttöteksti muodossa " (3)" tai " (3/24)".

    Käyttää check_capacity.check_competition_capacity-funktiota taustasäikeessä.
    """

    if not url:
        return ""
    if capacity_mod is None or not hasattr(capacity_mod, "check_competition_capacity"):
        return ""

    loop = asyncio.get_running_loop()

    def _run() -> Any:
        try:
            mod = capacity_mod
            if mod is None:
                return None
            return mod.check_competition_capacity(url, timeout=10)
        except Exception:
            return None

    cap = await loop.run_in_executor(None, _run)
    if not isinstance(cap, dict):
        return ""

    reg = cap.get("registered")
    lim = cap.get("limit")
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


def _parse_metrix_date(value: str) -> date | None:
    """Yritä tulkita Metrixin VIIKKOKISA.jsonissa oleva päivämäärä.

    Muodot ovat tyypillisesti esim. "06/27/26 14:00" tai "06/27/26 - 06/27/26".
    Palautetaan pelkkä päivämäärä (ei kellonaikaa).
    """

    if not value:
        return None

    txt = value.strip()
    if not txt:
        return None

    # Jos on päiväysväli "MM/DD/YY - MM/DD/YY", käytä alkupäivää.
    if " - " in txt:
        txt = txt.split(" - ", 1)[0].strip()

    # Prefer day/month formats (Finnish convention)
    for fmt in ("%d/%m/%y %H:%M", "%d/%m/%y", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(txt, fmt)
            return dt.date()
        except Exception:
            continue

    return None


async def handle_viikkarit(message: Any, parts: Any) -> None:
    """!viikkarit – listaa tämän viikon viikkokisat.

    Käyttö:
        - !viikkarit              → Etelä-Pohjanmaan tämän viikon viikkokisat
        - !viikkarit ep           → sama kuin yllä (Etelä-Pohjanmaa)
        - !viikkarit pohj         → Pohjanmaa
        - !viikkarit kp           → Keski-Pohjanmaa
        - !viikkarit ks           → Keski-Suomi
        - !viikkarit pirk         → Pirkanmaa
        - !viikkarit sata         → Satakunta
        - !viikkarit mk           → lähimaakuntien viikkokisat (EP + naapurimaakunnat, WEEKLY_AREAS / VIIKKARIT_SEUTU)
        - !viikkarit suomi        → koko Suomen tämän viikon viikkokisat
    """

    # Aluevalinta: oletus Etelä-Pohjanmaa (VIIKKOKISA / VIIKKOKISA.json).
    mode = "ep"
    if parts and len(parts) >= 2:
        sub = str(parts[1] or "").strip().lower()
        if sub in ("suomi", "fi", "koko", "koko-suomi"):
            mode = "suomi"
        elif sub in ("mk",):
            mode = "seutu"
        elif sub in ("ep", "etelä-pohjanmaa", "etelapohjanmaa", "etela-pohjanmaa"):
            mode = "ep"
        elif sub in ("pohj", "pohjanmaa"):
            mode = "pohj"
        elif sub in ("kp", "keski-pohjanmaa", "keskipohjanmaa"):
            mode = "kp"
        elif sub in ("ks", "keski-suomi", "keskisuomi"):
            mode = "ks"
        elif sub in ("pirk", "pirkanmaa"):
            mode = "pirk"
        elif sub in ("sata", "satakunta"):
            mode = "sata"

    area_filter: str | None = None

    if mode == "suomi":
        # Suomi-moodi: kisahaku (search_weekly_fast / kisahaku.py) kirjoittaa
        # kaikki Suomen viikkokisat tiedostoon "viikkarit_suomi.json".
        # Käytetään samaa rakennetta kuin VIIKKOKISA.jsonissa.
        category_name = "VIIKKARIT_SUOMI"
        filename = "viikkarit_suomi.json"
        title_suffix = " – koko Suomi"
    elif mode == "seutu":
        # Seutu-moodi: EP + naapurimaakunnat (hakuskripti kirjoittaa VIIKKARIT_SEUTU.json).
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        title_suffix = " – lähimaakunnissa"
    elif mode == "pohj":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        title_suffix = " – Pohjanmaa"
        area_filter = "Pohjanmaa"
    elif mode == "kp":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        title_suffix = " – Keski-Pohjanmaa"
        area_filter = "Keski-Pohjanmaa"
    elif mode == "ks":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        title_suffix = " – Keski-Suomi"
        area_filter = "Keski-Suomi"
    elif mode == "pirk":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        title_suffix = " – Pirkanmaa"
        area_filter = "Pirkanmaa"
    elif mode == "sata":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        title_suffix = " – Satakunta"
        area_filter = "Satakunta"
    else:
        category_name = "VIIKKOKISA"
        filename = "VIIKKOKISA.json"
        # Use configured default location name when composing title
        title_suffix = f" – {DEFAULT_WEEKLY_LOCATION}"

    # Ladataan keskitetystä data_storesta, jos mahdollista.
    entries: list[dict]
    if data_store is not None and hasattr(data_store, "load_category"):
        try:
            entries = data_store.load_category(category_name)  # type: ignore[assignment]
        except Exception:
            entries = []
    else:
        # Fallback: lue suoraan projektijuuren JSON-tiedosto.
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__) or "", ".."))
            path = os.path.join(base_dir, filename)
            import json

            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            entries = []

    if not entries:
        try:
            if mode == "seutu":
                await message.channel.send(
                    "Viikkokisoja päivitetään (lähimaakunnat). Yritä hetken päästä uudelleen komennolla !viikkarit mk."
                )
            elif mode == "suomi":
                await message.channel.send(f"VIIKKOKISA-dataa ei löytynyt ({filename}).")
            else:
                await message.channel.send(f"VIIKKOKISA-dataa ei löytynyt ({filename}).")
        except Exception:
            pass
        return

    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # maanantai
    week_end = week_start + timedelta(days=7)  # seuraavan viikon maanantai (eksklusiivinen)

    week_entries: list[tuple[date, dict]] = []

    # Decide parsing preference based on source filename: some weekly JSONs use MM/DD
    month_first_files = ("known_weekly_competitions.json", "VIIKKOKISA.json", "VIIKKARIT_SEUTU.json", "viikkarit_suomi.json")
    month_first = str(filename or "").lower() in [p.lower() for p in month_first_files]

    for e in entries:
        kind = (e.get("kind") or "").upper()
        if "VIIKKOKISA" not in kind:
            continue

        if area_filter:
            entry_area = str(e.get("area") or "").strip()
            if not entry_area:
                continue
            if entry_area.lower() != area_filter.lower():
                continue

        d_raw = str(e.get("date") or "")
        # Normalize ambiguous dates to DD/MM/YYYY. If JSON date seems ambiguous
        # and we have a Metrix URL, fetch the canonical date from Metrix.
        try:
            d_norm = normalize_date_string(d_raw, prefer_month_first=month_first)
        except Exception:
            d_norm = d_raw
        if (not d_norm or re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", d_raw)) and isinstance(e, dict) and e.get('url'):
            try:
                from .metrix_utils import fetch_metrix_canonical_date

                fetched = fetch_metrix_canonical_date(str(e.get('url') or ''))
                if fetched:
                    d_norm = fetched
            except Exception:
                pass
        loc_raw = str(e.get("location") or "")

        # Pudotetaan pois "runko"-rivit, jotka kuvaavat koko kauden sarjaa eivätkä
        # yksittäistä viikkokisaa. Tyypillisiä piirteitä:
        #  - päivämäärä on pitkä väli (esim. 01/01/26 - 12/31/26)
        #  - location on muotoa "Players: X" tai "Registration open".
        is_root = False
        txt = d_raw.strip()
        if " - " in txt:
            start_s, end_s = [p.strip() for p in txt.split(" - ", 1)]
            # Yritetään tulkita molemmat päät ja katsoa välin pituutta.
            for fmts in (("%m/%d/%y", "%m/%d/%y"), ("%m/%d/%Y", "%m/%d/%Y")):
                try:
                    d1 = datetime.strptime(start_s, fmts[0]).date()
                    d2 = datetime.strptime(end_s, fmts[1]).date()
                    if (d2 - d1).days > 1:
                        is_root = True
                        break
                except Exception:
                    continue

        loc_l = loc_raw.lower()
        if "players:" in loc_l or "registration open" in loc_l:
            is_root = True

        if is_root:
            continue

        # Parse normalized date (expect DD/MM/YYYY or ISO)
        d_parsed = None
        try:
            if d_norm:
                d_only = d_norm.split()[0]
                d_parsed = datetime.strptime(d_only, "%d/%m/%Y").date()
        except Exception:
            try:
                d_parsed = _parse_metrix_date(d_raw)
            except Exception:
                d_parsed = None
        if d_parsed is None:
            continue

        if week_start <= d_parsed < week_end:
            week_entries.append((d_parsed, e))

    if not week_entries:
        try:
            if mode == "suomi":
                await message.channel.send("Tälle viikolle ei löytynyt viikkokisoja (koko Suomi).")
            elif mode == "seutu":
                await message.channel.send("Tälle viikolle ei löytynyt viikkokisoja (lähimaakunnat).")
            elif mode == "pohj":
                await message.channel.send("Tälle viikolle ei löytynyt viikkokisoja (Pohjanmaa).")
            elif mode == "kp":
                await message.channel.send("Tälle viikolle ei löytynyt viikkokisoja (Keski-Pohjanmaa).")
            elif mode == "ks":
                await message.channel.send("Tälle viikolle ei löytynyt viikkokisoja (Keski-Suomi).")
            elif mode == "pirk":
                await message.channel.send("Tälle viikolle ei löytynyt viikkokisoja (Pirkanmaa).")
            elif mode == "sata":
                await message.channel.send("Tälle viikolle ei löytynyt viikkokisoja (Satakunta).")
            else:
                await message.channel.send("Tälle viikolle ei löytynyt viikkokisoja (Etelä-Pohjanmaa).")
        except Exception:
            pass
        return

    # Järjestetään päivämäärän mukaan.
    week_entries.sort(key=lambda t: t[0])

    # Rajataan pitkiä listoja, jottei yhdelle viikolle tule satoja rivejä.
    max_items = DEFAULT_MAX_WEEKLY_ITEMS
    omitted_count = 0
    if mode in ("suomi", "seutu") and len(week_entries) > max_items:
        omitted_count = len(week_entries) - max_items
        week_entries = week_entries[:max_items]

    lines: List[str] = []

    if mode == "seutu":
        # Ryhmitellään seutu-viikkokisat maakunnittain.
        from collections import defaultdict

        groups: dict[str, list[tuple[date, dict]]] = defaultdict(list)
        for d_parsed, e in week_entries:
            area_name = str(e.get("area") or "Muu seutu").strip() or "Muu seutu"
            groups[area_name].append((d_parsed, e))

        preferred_order = [
            "Etelä-Pohjanmaa",
            "Pohjanmaa",
            "Keski-Pohjanmaa",
            "Keski-Suomi",
            "Pirkanmaa",
            "Satakunta",
        ]

        def _area_sort_key(name: str) -> tuple[int, str]:
            try:
                idx = preferred_order.index(name)
            except ValueError:
                idx = len(preferred_order)
            return (idx, name.lower())

        first = True
        for area_name in sorted(groups.keys(), key=_area_sort_key):
            area_entries = sorted(groups[area_name], key=lambda t: t[0])
            if not first:
                lines.append("")
            first = False
            lines.append(f"**{area_name}**")
            for d_parsed, e in area_entries:
                title = str(e.get("title") or "")
                url = str(e.get("url") or "")
                loc = str(e.get("location") or "")
                raw_date = str(e.get("date") or "")

                try:
                    friendly_date = d_parsed.strftime("%d.%m.%Y")
                except Exception:
                    friendly_date = raw_date

                capacity_str = ""
                if url:
                    try:
                        capacity_str = await _get_capacity_display(url)
                    except Exception:
                        capacity_str = ""

                suffix_parts: list[str] = []
                if friendly_date:
                    suffix_parts.append(friendly_date)
                if loc:
                    suffix_parts.append(loc)
                suffix = " — " + " | ".join(suffix_parts) if suffix_parts else ""

                if url:
                    lines.append(f"• [{title}]({url}){capacity_str}{suffix}")
                else:
                    lines.append(f"• {title}{capacity_str}{suffix}")
    else:
        for d_parsed, e in week_entries:
            title = str(e.get("title") or "")
            url = str(e.get("url") or "")
            loc = str(e.get("location") or "")
            raw_date = str(e.get("date") or "")

            # Näytetään päiväys muodossa DD.MM.YYYY (tai käytetään raakaa jos ei tulkintaa).
            try:
                friendly_date = d_parsed.strftime("%d.%m.%Y")
            except Exception:
                friendly_date = raw_date

            # Osallistujamäärä: näytetään EP- ja yksittäisissä maakuntamoodissa.
            capacity_str = ""
            if mode in ("ep", "pohj", "kp", "ks", "pirk", "sata") and url:
                try:
                    capacity_str = await _get_capacity_display(url)
                except Exception:
                    capacity_str = ""

            suffix_parts: list[str] = []
            if friendly_date:
                suffix_parts.append(friendly_date)
            if loc:
                suffix_parts.append(loc)
            suffix = " — " + " | ".join(suffix_parts) if suffix_parts else ""

            if url:
                lines.append(f"• [{title}]({url}){capacity_str}{suffix}")
            else:
                lines.append(f"• {title}{capacity_str}{suffix}")

    if omitted_count > 0:
        lines.append(f"…ja {omitted_count} muuta viikkokisaa tällä viikolla.")

    desc = "\n".join(lines)

    try:
        Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
        if Embed_cls:
            title = "Tämän viikon viikkokisat" + title_suffix
            embed = Embed_cls(title=title, description=desc)
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(desc)
    except Exception:
        try:
            await message.channel.send(desc)
        except Exception:
            pass
