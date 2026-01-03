import os
import json
import re
from typing import Any, List

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover
    discord = None  # type: ignore[assignment]


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
                        entries.extend(data)
                    elif isinstance(data, dict):
                        # some files may be dicts mapping ids to entries or lists
                        for v in data.values():
                            if isinstance(v, list):
                                entries.extend(v)
                            else:
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
                    date_text = str(date_field)
                else:
                    m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{2,4})", title)
                    if m:
                        date_text = m.group(1)
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
