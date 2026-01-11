import threading
import time
import logging
try:
    import discord  # type: ignore[import]
except Exception:
    discord = None
Intents = getattr(discord, 'Intents', None)
try:
    from . import commands_rek as rek_commands
except Exception:
    rek_commands = None
try:
    from . import commands_etsi as etsi_commands
except Exception:
    etsi_commands = None
try:
    from . import commands_help as help_commands
except Exception:
    help_commands = None
try:
    from . import commands_spots as spots_commands
except Exception:
    spots_commands = None
try:
    from . import commands_pdga as pdga_commands
except Exception:
    pdga_commands = None
try:
    from . import commands_metrix as metrix_commands
except Exception:
    metrix_commands = None
try:
    from . import commands_viikkarit as viikkarit_commands
except Exception:
    viikkarit_commands = None
try:
    from . import commands_tulokset as tulokset_commands
except Exception:
    tulokset_commands = None
try:
    from . import commands_disc as disc_commands
except Exception:
    disc_commands = None
try:
    from . import commands_admin as admin_commands
except Exception:
    admin_commands = None
from typing import Any, cast


logger = logging.getLogger(__name__)



class CommandListenerThread(threading.Thread):
    def __init__(self, token, prefix='!', run_forever=True):
        super().__init__(daemon=True)
        self.token = token
        self.prefix = prefix
        self.run_forever = run_forever
        self.client = None
        # (channel_id, user_id) -> list of candidate disc dicts for !kiekko
        self.pending_disc_choices = {}

    def run(self):
        if discord is None:
            print('discord.py not installed; command listener disabled')
            return

        if Intents is not None:
            intents = Intents.default()
            intents.message_content = True
            intents.messages = True
        else:
            class _FallbackIntents:
                def __init__(self):
                    self.message_content = True
                    self.messages = True

            intents = _FallbackIntents()
        client = discord.Client(intents=cast(Any, intents))
        self.client = client

        # Monkey-patch common discord.py send methods to log all outgoing messages
        try:
            def _make_send_wrapper(orig):
                async def _wrapper(self_obj, *a, **kw):
                    try:
                        ch_name = getattr(self_obj, 'name', None)
                        ch_id = getattr(self_obj, 'id', None)
                        chan_disp = f"#{ch_name}" if ch_name else f"channel_id={ch_id}"
                        author = getattr(getattr(self, 'user', None), 'name', 'Bot')
                        print(f"[Outgoing -> Discord] {author} -> {chan_disp}: send called args={len(a)} kwargs={list(kw.keys())}")
                    except Exception:
                        try:
                            print(f"[Outgoing -> Discord] send called: args={len(a)} kwargs={list(kw.keys())}")
                        except Exception:
                            pass
                    try:
                        res = await orig(self_obj, *a, **kw)
                        try:
                            print(f"[Outgoing -> Discord] send succeeded to {chan_disp}")
                        except Exception:
                            pass
                        return res
                    except Exception as e:
                        try:
                            print(f"[Outgoing -> Discord] send FAILED to {chan_disp}: {e}")
                        except Exception:
                            pass
                        raise
                return _wrapper

            # Try to patch a few common classes used for .send
            targets = []
            try:
                # discord.abc.Messageable base
                abc_mod = getattr(discord, 'abc', None)
                if abc_mod and hasattr(abc_mod, 'Messageable'):
                    targets.append(abc_mod.Messageable)
            except Exception:
                pass
            for name in ('TextChannel', 'DMChannel', 'GuildChannel', 'Thread', 'GroupChannel'):
                try:
                    cls = getattr(discord, name, None)
                    if cls:
                        targets.append(cls)
                except Exception:
                    pass

            seen = set()
            for cls in targets:
                try:
                    if cls in seen:
                        continue
                    seen.add(cls)
                    orig = getattr(cls, 'send', None)
                    if orig and not getattr(orig, '__is_wrapped_by_log__', False):
                        wrapper = _make_send_wrapper(orig)
                        setattr(wrapper, '__is_wrapped_by_log__', True)
                        setattr(cls, 'send', wrapper)
                except Exception:
                    continue
        except Exception:
            pass

        @client.event
        async def on_ready():
            print(f'Komentokuuntelija yhdistetty käyttäjänä {client.user}')
            if not self.run_forever:
                await client.close()

        @client.event
        async def on_message(message):
            try:
                if message.author.bot:
                    return
                content = (message.content or '').strip()
                if not content:
                    return

                # Log incoming Discord messages that look like commands (start with prefix)
                try:
                    if content.startswith(self.prefix):
                        chan = getattr(message.channel, 'name', None)
                        chan_disp = f"#{chan}" if chan else f"channel_id={getattr(message.channel, 'id', 'unknown')}"
                        try:
                            author = getattr(message.author, 'name', str(message.author))
                        except Exception:
                            author = str(message.author)
                        print(f"[Discord Command] {author} {chan_disp}: {content}")
                except Exception:
                    try:
                        print(f"[Discord Command] {str(message.author)}: {content}")
                    except Exception:
                        pass

                # If user has a pending disc choice from a previous !kiekko,
                # allow them to reply with a number (1..N) without prefix.
                key = None
                try:
                    key = (str(message.channel.id), str(message.author.id))
                    pending = self.pending_disc_choices.get(key)
                except Exception:
                    pending = None

                if pending:
                    sel = content.strip()
                    if sel.isdigit():
                        idx = int(sel) - 1
                        if 0 <= idx < len(pending):
                            best = pending[idx]
                            # consume the pending selection
                            try:
                                if key is not None and key in self.pending_disc_choices:
                                    del self.pending_disc_choices[key]
                            except Exception:
                                pass
                            if disc_commands is not None and hasattr(disc_commands, 'send_disc_card'):
                                await disc_commands.send_disc_card(message.channel, best, sel)
                            else:
                                await message.channel.send('Virhe: kiekko-komentoa ei voi suorittaa (moduuli puuttuu).')
                            return
                    # If content is not a digit, fall through to normal command handling

                parts = content.split()
                cmd = parts[0].lower() if parts else ''
                if not cmd.startswith(self.prefix):
                    return
                command = cmd[len(self.prefix):]

                # --- !reset: tyhjennä botin väliaikaiset muistirakenteet ---
                if command == 'reset':
                    # Salli komento vain ylläpitäjiltä (jos tieto saatavilla).
                    is_admin = False
                    try:
                        perms = getattr(getattr(message.author, 'guild_permissions', None), 'administrator', False)
                        if perms:
                            is_admin = True
                    except Exception:
                        is_admin = False

                    if not is_admin:
                        await message.channel.send('Reset-komennon käyttö vaatii ylläpitäjäoikeudet.')
                        return

                    try:
                        self.pending_disc_choices.clear()
                    except Exception:
                        pass
                    await message.channel.send('Botti resetoitu (väliaikaiset muistirakenteet tyhjennetty).')
                    return

                # --- !admin: ylläpitoasetukset ---
                if command == 'admin':
                    if admin_commands is not None and hasattr(admin_commands, 'handle_admin'):
                        await admin_commands.handle_admin(message, parts)
                    else:
                        await message.channel.send('Virhe: admin-komentoa ei voi suorittaa (moduuli puuttuu).')
                    return

                # --- !pdga: player lookup by PDGA number ---
                if command == 'pdga':
                    if pdga_commands is not None and hasattr(pdga_commands, 'handle_pdga'):
                        await pdga_commands.handle_pdga(message, parts)
                    else:
                        await message.channel.send('Virhe: pdga-komentoa ei voi suorittaa (moduuli puuttuu).')
                    return

                # --- !metrix: placeholder Metrix rating/profile command (phase 1) ---
                if command == 'metrix':
                    if metrix_commands is not None and hasattr(metrix_commands, 'handle_metrix'):
                        await metrix_commands.handle_metrix(message, parts)
                    else:
                        await message.channel.send('Virhe: metrix-komentoa ei voi suorittaa (moduuli puuttuu).')
                    return

                # --- !viikkarit: tämän viikon viikkokisat (VIIKKOKISA.json) ---
                if command == 'viikkarit':
                    # Try to import the module dynamically if it wasn't available at startup
                    try:
                        if viikkarit_commands is None:
                            try:
                                from . import commands_viikkarit as vi_mod
                                globals()['viikkarit_commands'] = vi_mod
                                viikkarit_local = vi_mod
                            except Exception as ie:
                                await message.channel.send(f'Virhe: viikkarit-komentoa ei voi suorittaa (moduuli latautui virheellisesti): {ie}')
                                return
                        else:
                            viikkarit_local = viikkarit_commands

                        if hasattr(viikkarit_local, 'handle_viikkarit'):
                            await viikkarit_local.handle_viikkarit(message, parts)
                        else:
                            await message.channel.send('Virhe: viikkarit-komennolle ei löydy käsittelijää (handle_viikkarit).')
                    except Exception as e:
                        try:
                            await message.channel.send(f'Virhe suoritettaessa viikkarit-komentoa: {e}')
                        except Exception:
                            pass
                    return

                # --- !tulokset: kilpailutulokset (esim. viikkari Top3) ---
                if command == 'tulokset':
                    # Kirjoita pyyntö terminaaliin
                    try:
                        print(f"[LakeusBotti] !tulokset-komento: {' '.join(parts)}")
                    except Exception:
                        pass
                    if tulokset_commands is not None and hasattr(tulokset_commands, 'handle_tulokset'):
                        await tulokset_commands.handle_tulokset(message, parts)
                    else:
                        await message.channel.send('Virhe: tulokset-komentoa ei voi suorittaa (moduuli puuttuu).')
                    return

                # --- !rek (existing behaviour, now delegated) ---
                if command == 'rek':
                    if rek_commands is not None and hasattr(rek_commands, 'handle_rek'):
                        await rek_commands.handle_rek(message, parts)
                    else:
                        await message.channel.send('Virhe: rek-komentoa ei voi suorittaa (moduuli puuttuu).')
                    return

                # --- !etsi: search competitions by area/track/name (delegated) ---
                if command == 'etsi':
                    if etsi_commands is not None and hasattr(etsi_commands, 'handle_etsi'):
                        await etsi_commands.handle_etsi(message, parts)
                    else:
                        await message.channel.send('Virhe: etsi-komentoa ei voi suorittaa (moduuli puuttuu).')
                    return

                # --- !kisa: list competitions (pdga / viikkari) ---
                if command == 'kisa':
                    if etsi_commands is not None and hasattr(etsi_commands, 'handle_kisa'):
                        await etsi_commands.handle_kisa(message, parts)
                    else:
                        await message.channel.send('Virhe: kisa-komentoa ei voi suorittaa (moduuli puuttuu).')
                    return

                # --- !kiekko: search PDGA disc approvals ---
                if command == 'kiekko':
                    if disc_commands is not None and hasattr(disc_commands, 'handle_kiekko'):
                        await disc_commands.handle_kiekko(message, parts, self.pending_disc_choices)
                    else:
                        await message.channel.send('Virhe: kiekko-komentoa ei voi suorittaa (moduuli puuttuu).')
                    return

                # --- !ohje: ohjekomennon käsittely (delegoidaan) ---
                if command == 'ohje':
                    if help_commands is not None and hasattr(help_commands, 'handle_help'):
                        await help_commands.handle_help(message, parts)
                    else:
                        await message.channel.send('Ohje ei ole käytettävissä.')
                    return

                # --- !seura: club / ranking commands ---
                if command == 'seura':
                    if tulokset_commands is not None and hasattr(tulokset_commands, 'handle_seura'):
                        await tulokset_commands.handle_seura(message, parts)
                    else:
                        await message.channel.send('Virhe: seura-komentoa ei voi suorittaa (moduuli puuttuu).')
                    return

                # --- !paikat: capacity alerts (delegated) ---
                if command == 'paikat':
                    if spots_commands is not None and hasattr(spots_commands, 'handle_spots'):
                        await spots_commands.handle_spots(message, parts)
                    else:
                        await message.channel.send('Virhe: paikat-komentoa ei voi suorittaa (moduuli puuttuu).')
            except Exception as ex:
                try:
                    await message.channel.send('Virhe käsitelläksesi komentoa: ' + str(ex))
                except Exception:
                    print('Failed to send error reply:', ex)

        try:
            client.run(self.token, reconnect=True)
        except Exception as e:
            print('Command listener run error:', e)


def start_command_listener(token: str, prefix='!', run_forever=True):
    if not token:
        print('No token provided for command listener; skipping')
        return None
    ct = CommandListenerThread(token, prefix=prefix, run_forever=run_forever)
    ct.start()
    time.sleep(0.5)
    return ct
