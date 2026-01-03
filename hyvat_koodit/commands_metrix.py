import asyncio
import re
from typing import Any, Optional

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover
    discord = None  # type: ignore[assignment]

try:
    from .metrix_stats import fetch_player_stats, PlayerStats
except Exception:  # pragma: no cover
    fetch_player_stats = None  # type: ignore[assignment]
    PlayerStats = None  # type: ignore[assignment]

try:
    from .player_store import get_metrix_for_user, set_metrix_for_user
except Exception:  # pragma: no cover
    get_metrix_for_user = None  # type: ignore[assignment]
    set_metrix_for_user = None  # type: ignore[assignment]


def _extract_metrix_id(raw: str) -> str:
    text = (raw or "").strip()
    m = re.search(r"(\d{3,})", text)
    return m.group(1) if m else ""


async def handle_metrix(message: Any, parts: Any) -> None:
    """!metrix – hae Metrix-rating ja kierroshistoria.

    Käyttö:
      - !metrix 12345         → hakee annetulla Metrix-ID:llä ja tallentaa sen käyttäjälle
      - !metrix https://...   → poimii ID:n annetusta Metrix-linkistä
      - !metrix               → käyttää aiemmin talletettua Metrix-ID:tä (pelaaja.json)
    """

    if fetch_player_stats is None:
        try:
            await message.channel.send("Virhe: Metrix-moduuli ei ole käytettävissä.")
        except Exception:
            pass
        return

    user_id = getattr(getattr(message, "author", None), "id", None)
    user_key = str(user_id) if user_id is not None else ""

    used_saved_id = False
    save_this_id = False

    if not parts or len(parts) < 2:
        saved_id: Optional[str] = None
        if user_key and get_metrix_for_user is not None:
            saved_id = get_metrix_for_user(user_key)

        if not saved_id:
            desc = (
                "Hae Metrix-pelaajan perustiedot ja rating-historian.\n\n"
                "Käyttöesimerkkejä:\n"
                "!metrix lisää 12345 – tallenna oma MetrixID\n"
                "!metrix 12345 – hae annetun ID:n tiedot\n"
                "!metrix https://discgolfmetrix.com/player/12345 – poimii ID:n linkistä\n"
                "!metrix poista – poista tallennettu MetrixID\n"
                "Pelkkä !metrix käyttää aiemmin tallennettua ID:tä, jos sellainen on."
            )
            try:
                Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
                title = "Käyttö: !metrix"
                if Embed_cls:
                    embed = Embed_cls(title=title, description=desc)
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send(f"{title}\n{desc}")
            except Exception:
                pass
            return

        raw = str(saved_id).strip()
        used_saved_id = True
    else:
        sub = str(parts[1] or "").strip().lower()
        # Alakomento "poista": !metrix poista → poista tallennettu ID
        if sub == "poista":
            if user_key and set_metrix_for_user is not None:
                try:
                    set_metrix_for_user(user_key, "")
                except Exception:
                    pass
            try:
                await message.channel.send("Poistettu metrixID")
            except Exception:
                pass
            return

        # Alakomento "lisää": !metrix lisää 12345 → tallenna oma ID
        if sub in ("lisaa", "lisää") and len(parts) >= 3:
            raw = str(parts[2] or "").strip()
            save_this_id = True
        else:
            # Pelkkä numerosarja tai linkki → hae tiedot, älä tallenna
            raw = str(parts[1] or "").strip()

    metrix_id = _extract_metrix_id(raw)
    if not metrix_id:
        try:
            if save_this_id:
                await message.channel.send("Anna Metrix-ID komennon muodossa: !metrix lisää 12345")
            else:
                await message.channel.send("Anna Metrix-ID (numerot) tai Metrix-linkki.")
        except Exception:
            pass
        return

    try:
        if hasattr(message.channel, "trigger_typing"):
            await message.channel.trigger_typing()
    except Exception:
        pass

    loop = asyncio.get_running_loop()

    def _do_fetch() -> Any:
        return fetch_player_stats(metrix_id)  # type: ignore[func-returns-value]

    stats = await loop.run_in_executor(None, _do_fetch)

    if stats is None:
        try:
            await message.channel.send(
                f"Metrix-tietojen haku epäonnistui ID:llä {metrix_id}. "
                "Tarkista ID sekä METRIX_*-ympäristömuuttujat."
            )
        except Exception:
            pass
        return

    if save_this_id and user_key and set_metrix_for_user is not None:
        try:
            set_metrix_for_user(user_key, metrix_id)
            try:
                await message.channel.send("Lisätty metrixID")
            except Exception:
                pass
        except Exception:
            pass

    name = stats.name or "(tuntematon)"
    rating = stats.rating
    rating_change = stats.rating_change
    profile_url = stats.profile_url
    change_int: Optional[int] = None

    # Viimeisimmän rating-pisteen päivämäärä (oranssin käyrän uusin piste).
    last_rating_date: Optional[str] = None
    if getattr(stats, "rating_curve", None):
        try:
            curve_all_for_date = list(stats.rating_curve)
            for pt in reversed(curve_all_for_date):
                d = getattr(pt, "date", None)
                if d:
                    last_rating_date = str(d)
                    break
        except Exception:
            last_rating_date = None

    lines = []
    lines.append(f"**{name}**")

    # Rating-rivi: otsikko boldattuna, luvut normaalina, muutos kokonaislukuna samassa rivissä.
    if rating is not None:
        try:
            rating_int = int(round(float(rating)))
        except Exception:
            rating_int = int(rating) if isinstance(rating, (int, float)) else 0

        # Muutos samaan riviin, ilman erillistä koodiblokkia.
        if rating_change is not None:
            try:
                change_int = int(round(float(rating_change)))
            except Exception:
                change_int = 0
            line_rating = f"{rating_int} (muutos: {change_int:+d})"
        else:
            line_rating = f"{rating_int}"

        lines.append(f"**Rating:** {line_rating}")
    else:
        lines.append("**Rating:** ?")

    # Kilpailujen kokonaismäärä rating-analyysin taulukosta + viimeisin kisapäivä.
    if stats.competitions_count is not None:
        if stats.last_competition_date:
            lines.append(
                f"**Kilpailut:** {stats.competitions_count} (viimeisin {stats.last_competition_date})"
            )
        else:
            lines.append(f"**Kilpailut:** {stats.competitions_count}")
    else:
        # Näytä silti rivi, vaikka määrää ei saatu Metrixistä ulos.
        lines.append("**Kilpailut:** ?")

    # Paras peli vihreän course based rating -janan perusteella, jos saatavilla.
    best_value: Optional[float] = None
    best_date: Optional[str] = None
    best_course = getattr(stats, "best_course_rating", None)
    if best_course is not None:
        best_course_date = getattr(stats, "best_course_date", None)
        if best_course_date:
            lines.append(f"**Paras peli:** {best_course:.1f} ({best_course_date})")
            best_value = float(best_course)
            best_date = str(best_course_date)
        else:
            lines.append(f"**Paras peli:** {best_course:.1f}")
            best_value = float(best_course)
    elif stats.best_round_rating is not None:
        if stats.best_round_date:
            lines.append(f"**Paras peli:** {stats.best_round_rating:.1f} ({stats.best_round_date})")
            best_value = float(stats.best_round_rating)
            best_date = str(stats.best_round_date)
        else:
            lines.append(f"**Paras peli:** {stats.best_round_rating:.1f}")
            best_value = float(stats.best_round_rating)

    # Metrix rating -käyrä (oranssi viiva) – PDGA-tyylinen kehitysketju yhdellä rivillä.
    rating_trend = ""
    trend_values: list[float] = []
    if getattr(stats, "rating_curve", None):
        curve_all = list(stats.rating_curve)
        if len(curve_all) >= 2:
            # Otetaan enintään 6 viimeistä pistettä (5 muutosta), aikajärjestyksessä.
            last_points = curve_all[-6:]
            values = []
            for pt in last_points:
                if pt is None or getattr(pt, "rating", None) is None:
                    continue
                try:
                    values.append(float(pt.rating))
                except Exception:
                    continue

            if len(values) >= 2:
                parts = [f"{values[0]:.0f}"]
                for idx in range(1, len(values)):
                    delta = values[idx] - values[idx - 1]
                    if abs(delta) < 0.05:
                        arrow = "→"
                    elif delta > 0:
                        arrow = "↗"
                    else:
                        arrow = "↘"
                    parts.append(f" {arrow}{values[idx]:.0f}")
                rating_trend = "".join(parts)
                trend_values = values

    # Kevyt ANSI-codeblock: ei taustalaattoja, vain pehmeät värit.
    # Käytetään dim-värejä: harmaa, teal (ylös), punainen (alas).
    esc = "\x1b"
    reset = f"{esc}[0m"
    label_col = f"{esc}[0;37m"          # otsikot normaalilla valkoisella
    col_flat = f"{esc}[2;37m"           # dim harmaa
    # Ylös-väri: käytä samaa komboa kuin antamassasi esimerkissä
    # "\x1b[2;36m\x1b[2;32m↗898\x1b[0m\x1b[2;36m\x1b[0m"
    col_up = f"{esc}[2;36m{esc}[2;32m"  # dim teal + dim vihreä -kombo
    col_down = f"{esc}[2;31m"           # dim punainen

    ansi_block: list[str] = []

    # Rating-historia nuolineen ja väreineen (teal ylös, punainen alas)
    # Itse codeblockissa ei ole tekstiä, vain numerot ja nuolet väreillä.
    if trend_values:
        base_val = int(round(trend_values[0]))

        parts: list[str] = []
        parts.append(f"{col_flat}{base_val}{reset}")

        for idx in range(1, len(trend_values)):
            cur = trend_values[idx]
            prev = trend_values[idx - 1]
            delta = cur - prev
            cur_int = int(round(cur))
            if abs(delta) < 0.05:
                arrow = "→"
                col = col_flat
            elif delta > 0:
                arrow = "↗"
                col = col_up
            else:
                arrow = "↘"
                col = col_down
            parts.append(f"{col}{arrow}{cur_int}{reset}")

        history_line = " ".join(parts)
        ansi_block.append(history_line)

    if ansi_block:
        # Otsikko normaalilla tekstillä, vain numerot/nuolet codeblockiin.
        lines.append("**Rating-historia**")
        lines.append("```ansi")
        lines.extend(ansi_block)
        lines.append("```")

    # Profiililinkki loppuun lyhyellä ankkuritekstillä.
    if profile_url:
        lines.append(f"**Linkki:** [Metrix]({profile_url})")

    desc = "\n".join(lines)

    try:
        Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
        if Embed_cls:
            # Valitaan upotteen väri rating-muutoksen suunnan mukaan.
            colour = None
            if isinstance(rating_change, (int, float)):
                if rating_change > 0.05:
                    colour = 0x00FF00  # vihreä
                elif rating_change < -0.05:
                    colour = 0xFF0000  # punainen

            if colour is not None:
                embed = Embed_cls(description=desc, colour=colour)
            else:
                embed = Embed_cls(description=desc)
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(desc)
    except Exception:
        try:
            await message.channel.send(desc)
        except Exception:
            pass
