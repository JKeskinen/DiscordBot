import os
import json
import re
from typing import Any, List

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover
    discord = None  # type: ignore[assignment]


async def handle_rek(message: Any, parts: Any) -> None:
    """Handle the !rek command (pending registrations listing)."""
    # The !rek command is disabled. Route users to `!kisa` instead.
    try:
        await message.channel.send("Komento `!rek` on poistettu käytöstä. Käytä `!kisa`-komentoa sen sijaan.")
    except Exception:
        pass
    return

    # parse command args (allow: !rek, !rek pdga, !rek week)
    arg = parts[1].lower() if len(parts) > 1 else None

    # Load pending registrations (prefer sqlite-backed store)
    entries = []
    try:
        from . import data_store as _ds
    except Exception:
        _ds = None
    try:
        if _ds is not None:
            entries = _ds.load_category('pending_registration') or []
        else:
            base_dir = os.path.abspath(os.path.dirname(__file__))
            # project root
            root = os.path.abspath(os.path.join(base_dir, ".."))
            pending_path = os.path.join(root, "pending_registration.json")
            try:
                with open(pending_path, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            except Exception:
                entries = []
    except Exception:
        entries = []

    if not entries:
        await message.channel.send("Rekisteröintiä ei löytynyt.")
        return

    # Filter entries based on which thread/channel the command came from
    try:
        channel_id = str(message.channel.id)
        pdga_thread = os.environ.get("DISCORD_PDGA_THREAD")
        weekly_thread = os.environ.get("DISCORD_WEEKLY_THREAD")

        def is_pdga(e: Any) -> bool:
            return "PDGA" in (e.get("kind") or "").upper()

        target = None
        # explicit arg overrides (e.g. '!rek pdga' or '!rek week')
        if arg in ("pdga", "p"):
            target = "pdga"
        elif arg in ("week", "weekly", "viikko", "viikkokisa", "v"):
            target = "weekly"

        # env var mapping
        if target is None:
            if pdga_thread and channel_id == str(pdga_thread):
                target = "pdga"
            elif weekly_thread and channel_id == str(weekly_thread):
                target = "weekly"

        # fallback: inspect channel/thread name
        if target is None:
            try:
                ch_name = (message.channel.name or "").lower()
                if "viikko" in ch_name or "week" in ch_name:
                    target = "weekly"
                elif "pdga" in ch_name:
                    target = "pdga"
            except Exception:
                pass

        # default to weekly if still unknown (safer for !rek used in weekly threads)
        if target is None:
            target = "weekly"

        if target == "pdga":
            entries = [e for e in entries if is_pdga(e)]
        else:
            entries = [e for e in entries if not is_pdga(e)]

        # Suodata viikkarikomennossa pois "sarjan rungot" kuten
        # "Luoma-ahon Lauantai Liiga" ja "FGK viikkarit 2026",
        # jotta listalla näkyvät vain varsinaiset osakilpailut.
        if target == "weekly" and entries:
            def _is_series_container(item: Any, all_items: Any) -> bool:
                try:
                    title = (item.get("title") or item.get("name") or "").strip()
                except Exception:
                    return False
                if not title:
                    return False
                # Jos otsikossa on nuoli, kyse ei ole rungosta
                if "→" in title:
                    return False
                prefix = f"{title} → "
                # Jos jokin toinen rivi alkaa samalla otsikolla + nuolimerkillä,
                # tulkitaan tämä sarjarungoksi.
                for other in all_items:
                    if other is item:
                        continue
                    try:
                        ot = (other.get("title") or other.get("name") or "").strip()
                    except Exception:
                        continue
                    if ot.startswith(prefix):
                        return True
                # Lisäheuristiikka: hyvin pitkä päivämääräväli esim.
                # "01/01/26 - 12/31/26" viittaa usein kausisarjaan.
                try:
                    date_txt = str(item.get("date") or item.get("start_date") or "")
                except Exception:
                    date_txt = ""
                if "-" in date_txt:
                    # Jos merkkijono näyttää kahdelta päivämäärältä ja ne eroavat,
                    # kohdellaan sarjarunkona.
                    parts_dt = [p.strip() for p in date_txt.split('-')]
                    if len(parts_dt) == 2 and parts_dt[0] and parts_dt[1] and parts_dt[0] != parts_dt[1]:
                        return True
                return False

            entries = [e for e in entries if not _is_series_container(e, entries)]
    except Exception:
        pass

    if not entries:
        await message.channel.send("Tässä kanavassa ei löytynyt rekisteröitymisiä.")
        return

    # Build a concise reply (limit message length)
    lines: List[str] = []
    for e in entries:
        kind = (e.get("kind") or "").strip()

        title = e.get("title") or e.get("name") or ""
        # If title contains a parent prefix like "Parent → Child", display only the child
        try:
            if '→' in title:
                title = title.split('→')[-1].strip()
        except Exception:
            pass
        url = e.get("url") or ""

        # prefer a clear date: opening soon text, explicit date fields, or parse from title
        date_text = ""
        try:
            from komento_koodit.date_utils import normalize_date_string
            if e.get("opening_soon") and e.get("opens_in_days") is not None:
                date_text = f'avautuu {int(e.get("opens_in_days"))} pv'
            else:
                date_field = e.get("date") or e.get("start_date")
                if date_field:
                    date_text = normalize_date_string(str(date_field))
                else:
                    m = re.search(r"(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{2,4})", title)
                    if m:
                        date_text = normalize_date_string(m.group(1))
        except Exception:
            date_text = ""

        # hide the kind label when it's just 'VIIKKOKISA'
        if "VIIKKOKISA" in kind.upper():
            kind_display = ""
        else:
            kind_display = f" ({kind})" if kind else ""
        date_display = f" — {date_text}" if date_text else ""

        if url:
            lines.append(f"• [{title}]({url}){kind_display}{date_display}")
        else:
            lines.append(f"• {title}{kind_display}{date_display}")

    # Discord max message ~2000 chars; chunk if needed
    max_len = 1900
    cur: List[str] = []
    cur_len = 0
    for ln in lines:
        if cur_len + len(ln) + 1 > max_len and cur:
            try:
                Embed_cls = getattr(discord, "Embed", None)
                if Embed_cls:
                    embed = Embed_cls(title="Rekisteröinti avoinna:", description="\n".join(cur))
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
                embed = Embed_cls(title="Rekisteröinti avoinna:", description="\n".join(cur))
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("\n".join(cur))
        except Exception:
            await message.channel.send("\n".join(cur))
