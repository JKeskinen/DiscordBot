import os
from typing import Any

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover
    discord = None  # type: ignore[assignment]

try:
    # metrixbotin orkestrointiskripti, jossa ajastuksen asetukset
    import metrixbot_verifiedWorking as orchestrator
except Exception:  # pragma: no cover
    orchestrator = None  # type: ignore[assignment]

try:
    import settings
except Exception:  # pragma: no cover
    settings = None  # type: ignore[assignment]

async def _require_admin(message: Any) -> bool:
    """Palauta True jos lähettäjällä on ylläpitäjäoikeudet, muuten vastaa virheellä."""
    author = getattr(message, "author", None)
    is_admin = False
    try:
        perms = getattr(getattr(author, "guild_permissions", None), "administrator", False)
        if perms:
            is_admin = True
    except Exception:
        is_admin = False

    if not is_admin:
        await message.channel.send("Admin-komennon käyttö vaatii ylläpitäjäoikeudet.")
        return False
    return True


def _get_current_digest_time() -> str:
    # Prefer the running orchestrator's values, then settings module, then environment.
    hour = None
    minute = None
    try:
        if orchestrator is not None:
            hour = getattr(orchestrator, "DAILY_DIGEST_HOUR", None)
            minute = getattr(orchestrator, "DAILY_DIGEST_MINUTE", None)
    except Exception:
        hour = minute = None
    if not (isinstance(hour, int) and isinstance(minute, int)) and settings is not None:
        try:
            hour = getattr(settings, "DAILY_DIGEST_HOUR", hour)
            minute = getattr(settings, "DAILY_DIGEST_MINUTE", minute)
        except Exception:
            pass
    try:
        if isinstance(hour, int) and isinstance(minute, int):
            return f"{hour:02d}:{minute:02d}"
    except Exception:
        pass
    # fallback env / oletus
    env_hour = os.environ.get("DAILY_DIGEST_HOUR")
    env_minute = os.environ.get("DAILY_DIGEST_MINUTE")
    try:
        if env_hour is not None and env_minute is not None:
            return f"{int(env_hour):02d}:{int(env_minute):02d}"
    except Exception:
        pass
    return "(ei asetettu, käytössä oletus)"


def _get_current_capacity_interval() -> str:
    # Yritä lukea juokseva arvo orkestroijalta, muuten ympäristöstä.
    interval = None
    if orchestrator is not None:
        interval = getattr(orchestrator, "CURRENT_CAPACITY_INTERVAL", None)
    if not isinstance(interval, int) and settings is not None:
        try:
            interval = getattr(settings, "CAPACITY_CHECK_INTERVAL", interval)
        except Exception:
            interval = None
    if not isinstance(interval, int):
        try:
            interval = int(os.environ.get("CAPACITY_CHECK_INTERVAL", "600"))
        except Exception:
            interval = None
    if isinstance(interval, int) and interval > 0:
        minutes = interval / 60.0
        return f"{interval} s (~{minutes:.1f} min)"
    return "tuntematon"


async def handle_admin(message: Any, parts: Any) -> None:
    """Ylläpitäjän asetukset Discordin kautta (!admin ...).

    Alakomennot:
      !admin status
        - Näytä keskeiset asetukset (päivittäisen raportin kellonaika, kapasiteettitarkistusväli, kanavat).

      !admin aika HH:MM
      !admin time HH:MM
        - Muuta päivittäisen kilpailuraportin kellonaikaa (24h-kello).

      !admin thread <tyyppi> <kanava_id>
        - Aseta kohdekanava / -säie eri ilmoituksille.
          tyyppi: pdga | viikkarit | rek | discs | capacity
    """
    if not await _require_admin(message):
        return

    channel = message.channel
    if orchestrator is None:
        await channel.send("Virhe: orkestrointimoduulia ei löytynyt (metrixbot_verifiedWorking).")
        return

    if len(parts) == 1:
        help_text = (
            "Admin-komennon käyttö:\n"
            "!admin status - näytä nykyiset asetukset\n"
            "!admin aika HH:MM - muuta päivittäisen raportin kellonaikaa\n"
            "!admin thread <pdga|viikkarit|rek|discs|capacity> <kanava_id> - muuta kohdekanavaa"
        )
        # Lähetä ohje embedded-viestinä, jos mahdollista.
        try:
            EmbedCls = getattr(discord, "Embed", None) if discord is not None else None
        except Exception:
            EmbedCls = None
        if EmbedCls is not None:
            embed = EmbedCls(title="Admin-komennon käyttö", description=help_text)
            await channel.send(embed=embed)
        else:
            await channel.send(help_text)
        return

    sub = str(parts[1]).lower()

    # --- !admin status ---
    if sub in ("status", "tila"):
        digest_time = _get_current_digest_time()
        capacity_interval = _get_current_capacity_interval()
        # Prefer values from settings module when available
        pdga_thread = None
        weekly_thread = None
        discs_thread = None
        capacity_thread = None
        try:
            if settings is not None:
                pdga_thread = getattr(settings, "DISCORD_PDGA_THREAD", None) or getattr(settings, "DISCORD_THREAD_ID", None)
                weekly_thread = getattr(settings, "DISCORD_WEEKLY_THREAD_ID", None) or getattr(settings, "DISCORD_WEEKLY_THREAD", None)
                discs_thread = getattr(settings, "DISCORD_DISCS_THREAD_ID", None) or getattr(settings, "DISCORD_DISCS_THREAD", None)
                capacity_thread = getattr(settings, "CAPACITY_THREAD_ID", None)
        except Exception:
            pdga_thread = weekly_thread = discs_thread = capacity_thread = None
        # fallback to environment / defaults
        if not pdga_thread:
            pdga_thread = os.environ.get("DISCORD_PDGA_THREAD") or os.environ.get("DISCORD_THREAD_ID") or "(oletus)"
        if not weekly_thread:
            weekly_thread = os.environ.get("DISCORD_WEEKLY_THREAD") or os.environ.get("DISCORD_THREAD_ID") or "(oletus)"
        if not discs_thread:
            discs_thread = os.environ.get("DISCORD_DISCS_THREAD") or os.environ.get("DISCORD_THREAD_ID") or "(oletus)"
        if not capacity_thread:
            capacity_thread = os.environ.get("CAPACITY_THREAD_ID") or os.environ.get("DISCORD_THREAD_ID") or "(oletus)"

        msg = (
            "Nykyiset botin asetukset:\n"
            f"- Päivittäinen raportti (PDGA + viikkarit + rek): klo {digest_time}\n"
            f"- Kapasiteettitarkistuksen väli: {capacity_interval}\n"
            f"- PDGA-ilmoitukset: {pdga_thread}\n"
            f"- Viikkarikatsaukset: {weekly_thread}\n"
            f"- PDGA-kiekkojen uutuudet: {discs_thread}\n"
            f"- Kapasiteetti-ilmoitukset: {capacity_thread}"
        )

        # Lähetä asetukset embedded-viestinä, jos mahdollista.
        try:
            EmbedCls = getattr(discord, "Embed", None) if discord is not None else None
        except Exception:
            EmbedCls = None
        if EmbedCls is not None:
            embed = EmbedCls(title="Botin asetukset", description=msg)
            await channel.send(embed=embed)
        else:
            await channel.send(msg)
        return

    # --- !admin aika HH:MM / time HH:MM ---
    if sub in ("aika", "time"):
        if len(parts) < 3:
            await channel.send("Käyttö: !admin aika HH:MM (esim. 10:30)")
            return
        value = str(parts[2]).strip()
        if ":" not in value:
            await channel.send("Virhe: kellonaika muodossa HH:MM, esim. 07:45")
            return
        hour_str, minute_str = value.split(":", 1)
        try:
            hour = int(hour_str)
            minute = int(minute_str)
        except Exception:
            await channel.send("Virhe: kellonaika muodossa HH:MM, esim. 07:45")
            return
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            await channel.send("Virhe: kellonaika oltava väliltä 00:00–23:59.")
            return

        try:
            # Päivitä juoksevan prosessin asetukset
            setattr(orchestrator, "DAILY_DIGEST_HOUR", hour)
            setattr(orchestrator, "DAILY_DIGEST_MINUTE", minute)
            # Nollaa viimeisin ajopäivä, jotta uusi kellonaika
            # voi laukaista digestin vielä saman päivän aikana.
            try:
                setattr(orchestrator, "LAST_DIGEST_DATE", None)
            except Exception:
                pass
            # Päivitä myös ympäristömuuttujat, jotta seuraava käynnistys käyttää samaa aikaa
            os.environ["DAILY_DIGEST_HOUR"] = str(hour)
            os.environ["DAILY_DIGEST_MINUTE"] = f"{minute:02d}"
            # Päivitä myös settings-moduuli, jos käytettävissä (juokseva konfiguraatio)
            try:
                if settings is not None:
                    try:
                        setattr(settings, "DAILY_DIGEST_HOUR", int(hour))
                        setattr(settings, "DAILY_DIGEST_MINUTE", int(minute))
                    except Exception:
                        setattr(settings, "DAILY_DIGEST_HOUR", hour)
                        setattr(settings, "DAILY_DIGEST_MINUTE", minute)
            except Exception:
                pass
            # Kirjaa muutos prosessin lokiin (sama konsoli kuin start_botin tulosteet)
            try:
                print(f"[ADMIN] Päivitetty päivittäisen raportin kellonaika: {hour:02d}:{minute:02d}")
            except Exception:
                pass
        except Exception as exc:  # pragma: no cover - erittäin epätodennäköinen
            await channel.send(f"Virhe asetuksia päivitettäessä: {exc}")
            return

        await channel.send(f"Päivittäisen kilpailuraportin kellonaika asetettu: {hour:02d}:{minute:02d}. (tämän päivän digest ajetaan seuraavan tarkistuksen yhteydessä, jos aika on jo saavutettu)")
        return

    # --- !admin thread <type> <id> ---
    if sub in ("thread", "kanava"):
        if len(parts) < 4:
            await channel.send(
                "Käyttö: !admin thread <pdga|viikkarit|rek|discs|capacity> <kanava_id>\n"
                "Esim.: !admin thread pdga 123456789012345678"
            )
            return
        kind = str(parts[2]).lower()
        target_id = str(parts[3]).strip()
        if not target_id.isdigit():
            await channel.send("Virhe: kanava_id tulee olla numeerinen Discord-kanavan tai -säikeen ID.")
            return

        mapping = {
            "pdga": "DISCORD_PDGA_THREAD",
            "viikkarit": "DISCORD_WEEKLY_THREAD",
            "rek": "DISCORD_THREAD_ID",  # rekisteröinti-ilmoitukset käyttävät pääsäiettä
            "discs": "DISCORD_DISCS_THREAD",
            "capacity": "CAPACITY_THREAD_ID",
        }
        env_name = mapping.get(kind)
        if not env_name:
            await channel.send("Tuntematon tyyppi. Käytä: pdga, viikkarit, rek, discs tai capacity.")
            return

        os.environ[env_name] = target_id
        # Päivitä myös settings-moduulia, jos mahdollista
        try:
            if settings is not None:
                kind_map = {
                    "pdga": "DISCORD_THREAD_ID",
                    "viikkarit": "DISCORD_WEEKLY_THREAD_ID",
                    "rek": "DISCORD_THREAD_ID",
                    "discs": "DISCORD_DISCS_THREAD_ID",
                    "capacity": "CAPACITY_THREAD_ID",
                }
                attr = kind_map.get(kind)
                if attr:
                    try:
                        setattr(settings, attr, int(target_id))
                    except Exception:
                        setattr(settings, attr, target_id)
        except Exception:
            pass
        # Kirjaa muutos prosessin lokiin
        try:
            print(f"[ADMIN] Asetettu {kind}-ilmoitusten kohdekanavaksi/säikeeksi ID {target_id} (env {env_name}).")
        except Exception:
            pass

        await channel.send(f"Asetettu {kind}-ilmoitusten kohdekanavaksi/säikeeksi ID {target_id}.")
        return

    # Tuntematon alakomento
    await channel.send("Tuntematon admin-alakomento. Käytä: status, aika, thread.")
