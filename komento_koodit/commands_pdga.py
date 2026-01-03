import asyncio
import re
from typing import Any, Dict, Optional

import requests  # type: ignore[import]

try:
    from bs4 import BeautifulSoup  # type: ignore[import]
except Exception:  # pragma: no cover - optional
    BeautifulSoup = None  # type: ignore[assignment]

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover - optional
    discord = None  # type: ignore[assignment]

try:
    from .data_store import load_category, save_category
except Exception:  # pragma: no cover - optional
    load_category = None  # type: ignore[assignment]
    save_category = None  # type: ignore[assignment]

try:
    # Yhteinen pelaajatiedosto (pelaaja.json), jossa säilytetään sekä PDGA- että Metrix-ID:t.
    from .player_store import get_pdga_for_user, set_pdga_for_user
except Exception:  # pragma: no cover - optional
    get_pdga_for_user = None  # type: ignore[assignment]
    set_pdga_for_user = None  # type: ignore[assignment]


PDGA_PLAYER_BASE = "https://www.pdga.com/player"


def _fetch_pdga_player(number: str) -> Optional[Dict[str, Any]]:
    """Fetch basic PDGA player info by PDGA number.

    Returns a dict with keys like: name, number, rating, class, membership,
    location, country, and raw_url; or None on failure.
    """
    num = re.sub(r"[^0-9]", "", str(number or ""))
    if not num:
        return None

    url = f"{PDGA_PLAYER_BASE}/{num}"
    try:
        resp = requests.get(url, timeout=10)
    except Exception:
        return None

    if getattr(resp, "status_code", 0) != 200 or not resp.text:
        return None

    html = resp.text
    name = ""
    rating = ""
    player_class = ""
    membership = ""
    location = ""
    country = ""

    # Prefer BeautifulSoup when available for more robust parsing
    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Page title usually contains player name and possibly number
            h1 = soup.find("h1")
            if h1 is not None:
                name = h1.get_text(strip=True)

            # Many player pages have definition lists or tables for details
            # Try to find common labels.
            text = soup.get_text("\n", strip=True)
            # Very loose heuristics; these may fail silently if layout changes.
            m = re.search(r"Player Rating:\s*(\d+)", text)
            if m:
                rating = m.group(1)
            m = re.search(r"Classification:\s*([^\n]+)", text)
            if m:
                player_class = m.group(1).strip()
            m = re.search(r"Membership Status:\s*([^\n]+)", text)
            if m:
                membership = m.group(1).strip()
            m = re.search(r"Location:\s*([^\n]+)", text)
            if m:
                location = m.group(1).strip()
            m = re.search(r"Country:\s*([^\n]+)", text)
            if m:
                country = m.group(1).strip()
        except Exception:
            # Fall back to regex-only parsing below
            pass

    if not name:
        # Fallback: try to grab title text directly
        m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        if m:
            name = m.group(1).strip()

    if not name:
        return None

    return {
        "name": name,
        "number": num,
        "rating": rating,
        "class": player_class,
        "membership": membership,
        "location": location,
        "country": country,
        "url": url,
    }


async def handle_pdga(message: Any, parts: Any) -> None:
    """Handle the !pdga command: lookup player by PDGA number.

    Käyttäjä voi joko antaa numeron suoraan (!pdga 123456) tai tallentaa oman
    numeronsa ensimmäisellä kutsulla, jolloin jatkossa pelkkä !pdga hakee
    hänen tietonsa tallennetun numeron perusteella.
    """

    user_id = getattr(getattr(message, "author", None), "id", None)
    user_key = str(user_id) if user_id is not None else ""

    # Päättele käytettävä raakasyöte: joko komennon argumentti tai
    # aiemmin talletettu PDGA-numero käyttäjälle.
    used_saved_number = False
    if not parts or len(parts) < 2:
        saved_num = None
        if user_key and get_pdga_for_user is not None:
            saved_num = get_pdga_for_user(user_key)

        if not saved_num:
            try:
                Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
                title = "Käyttö: !pdga"
                desc = (
                    "Hae PDGA-pelaajan perustiedot numerolla.\n\n"
                    "Voit tallentaa oman numerosi komennolla:\n!pdga 123456\n\n"
                    "Pelkkä !pdga näyttää jatkossa oman PDGA-profiilisi, jos numero on tallennettu."
                )
                if Embed_cls:
                    embed = Embed_cls(title=title, description=desc)
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send(f"{title}\n{desc}")
            except Exception:
                pass
            return

        raw = str(saved_num).strip()
        used_saved_number = True
    else:
        raw = str(parts[1] or "").strip()
    num = re.sub(r"[^0-9]", "", raw)
    if not num:
        try:
            await message.channel.send("Anna PDGA-numero (vain numerot).")
        except Exception:
            pass
        return

    try:
        if hasattr(message.channel, "trigger_typing"):
            await message.channel.trigger_typing()
    except Exception:
        pass

    loop = asyncio.get_running_loop()

    def _do_fetch() -> Optional[Dict[str, Any]]:
        return _fetch_pdga_player(num)

    info = await loop.run_in_executor(None, _do_fetch)

    if not info:
        try:
            await message.channel.send(f"Pelaajaa ei löytynyt PDGA-numerolla {num}.")
        except Exception:
            pass
        return

    name = info.get("name") or "(tuntematon)"
    number = info.get("number") or num
    rating = info.get("rating") or "?"
    player_class = info.get("class") or "?"
    membership = info.get("membership") or "?"
    location = info.get("location") or ""
    country = info.get("country") or ""
    url = info.get("url") or f"{PDGA_PLAYER_BASE}/{number}"

    # Jos käyttäjä antoi numeron itse (eikä käytetty tallennettua), päivitetään
    # linkitys hänen Discord-käyttäjälleen yhteiseen pelaaja.json-tiedostoon.
    if not used_saved_number and user_key and number and set_pdga_for_user is not None:
        try:
            set_pdga_for_user(user_key, number)
        except Exception:
            # Tallennusvirhe ei saa estää tietojen näyttämistä
            pass

    lines = [f"Nimi: {name}", f"PDGA#: {number}", f"Rating: {rating}", f"Luokka: {player_class}", f"Jäsenyys: {membership}"]
    if location:
        lines.append(f"Sijainti: {location}")
    if country:
        lines.append(f"Maa: {country}")
    lines.append(f"Profiili: {url}")

    desc = "\n".join(lines)

    try:
        Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
        if Embed_cls:
            embed = Embed_cls(title=f"PDGA-pelaaja {number}", description=desc)
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(desc)
    except Exception:
        try:
            await message.channel.send(desc)
        except Exception:
            pass
