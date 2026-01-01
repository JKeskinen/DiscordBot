import threading
import time
import os
import json
import re
import asyncio
import concurrent.futures
import logging

try:
    import discord  # type: ignore[import]
except Exception:
    discord = None
Intents = getattr(discord, 'Intents', None)
try:
    from . import check_capacity as capacity_mod
except Exception:
    capacity_mod = None
from typing import Any, cast


class CommandListenerThread(threading.Thread):
    def __init__(self, token, prefix='!', run_forever=True):
        super().__init__(daemon=True)
        self.token = token
        self.prefix = prefix
        self.run_forever = run_forever
        self.client = None

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

        @client.event
        async def on_ready():
            print(f'Command listener connected as {client.user}')
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

                parts = content.split()
                cmd = parts[0].lower() if parts else ''
                if not cmd.startswith(self.prefix):
                    return
                command = cmd[len(self.prefix):]

                # --- !rek (existing behaviour) ---
                if command == 'rek':
                    # parse command args (allow: !rek, !rek pdga, !rek week)
                    arg = parts[1].lower() if len(parts) > 1 else None

                    # Load pending registrations
                    base_dir = os.path.abspath(os.path.dirname(__file__))
                    # project root
                    root = os.path.abspath(os.path.join(base_dir, '..'))
                    pending_path = os.path.join(root, 'pending_registration.json')
                    entries = []
                    try:
                        with open(pending_path, 'r', encoding='utf-8') as f:
                            entries = json.load(f)
                    except Exception:
                        entries = []

                    if not entries:
                        await message.channel.send('Rekisteröintiä ei löytynyt.')
                        return

                    # Filter entries based on which thread/channel the command came from
                    try:
                        channel_id = str(message.channel.id)
                        pdga_thread = os.environ.get('DISCORD_PDGA_THREAD')
                        weekly_thread = os.environ.get('DISCORD_WEEKLY_THREAD')

                        def is_pdga(e):
                            return 'PDGA' in (e.get('kind') or '').upper()

                        target = None
                        # explicit arg overrides (e.g. '!rek pdga' or '!rek week')
                        if arg in ('pdga', 'p'):
                            target = 'pdga'
                        elif arg in ('week', 'weekly', 'viikko', 'viikkokisa', 'v'):
                            target = 'weekly'

                        # env var mapping
                        if target is None:
                            if pdga_thread and channel_id == str(pdga_thread):
                                target = 'pdga'
                            elif weekly_thread and channel_id == str(weekly_thread):
                                target = 'weekly'

                        # fallback: inspect channel/thread name
                        if target is None:
                            try:
                                ch_name = (message.channel.name or '').lower()
                                if 'viikko' in ch_name or 'week' in ch_name:
                                    target = 'weekly'
                                elif 'pdga' in ch_name:
                                    target = 'pdga'
                            except Exception:
                                pass

                        # default to weekly if still unknown (safer for !rek used in weekly threads)
                        if target is None:
                            target = 'weekly'

                        if target == 'pdga':
                            entries = [e for e in entries if is_pdga(e)]
                        else:
                            entries = [e for e in entries if not is_pdga(e)]
                    except Exception:
                        pass

                    if not entries:
                        await message.channel.send('Tässä kanavassa ei löytynyt rekisteröitymisiä.')
                        return

                    # Build a concise reply (limit message length)
                    lines = []
                    for e in entries:
                        kind = (e.get('kind') or '').strip()

                        title = e.get('title') or e.get('name') or ''
                        url = e.get('url') or ''

                        # prefer a clear date: opening soon text, explicit date fields, or parse from title
                        date_text = ''
                        try:
                            if e.get('opening_soon') and e.get('opens_in_days') is not None:
                                date_text = f'avautuu {int(e.get("opens_in_days"))} pv'
                            else:
                                date_field = e.get('date') or e.get('start_date')
                                if date_field:
                                    date_text = str(date_field)
                                else:
                                    m = re.search(r'(\d{1,2}\.\d{1,2}\.\d{2,4})', title)
                                    if m:
                                        date_text = m.group(1)
                        except Exception:
                            date_text = ''

                        # hide the kind label when it's just 'VIIKKOKISA'
                        if 'VIIKKOKISA' in kind.upper():
                            kind_display = ''
                        else:
                            kind_display = f' ({kind})' if kind else ''
                        date_display = f' — {date_text}' if date_text else ''

                        if url:
                            lines.append(f'• [{title}]({url}){kind_display}{date_display}')
                        else:
                            lines.append(f'• {title}{kind_display}{date_display}')

                    # Discord max message ~2000 chars; chunk if needed
                    max_len = 1900
                    cur = []
                    cur_len = 0
                    for ln in lines:
                        if cur_len + len(ln) + 1 > max_len and cur:
                            try:
                                Embed_cls = getattr(discord, 'Embed', None)
                                if Embed_cls:
                                    embed = Embed_cls(title='Rekisteröinti avoinna:', description='\n'.join(cur))
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
                                embed = Embed_cls(title='Rekisteröinti avoinna:', description='\n'.join(cur))
                                await message.channel.send(embed=embed)
                            else:
                                await message.channel.send('\n'.join(cur))
                        except Exception:
                            await message.channel.send('\n'.join(cur))
                    return

                # --- !etsi: search competitions by area/track/name ---
                if command == 'etsi':
                    query = ' '.join(parts[1:]).strip().lower() if len(parts) > 1 else None
                    if not query:
                        try:
                            await message.channel.send('Käyttö: !etsi <alue tai rata> — esimerkki: !etsi helsinki')
                        except Exception:
                            pass
                        return

                    base_dir = os.path.abspath(os.path.dirname(__file__))
                    root = os.path.abspath(os.path.join(base_dir, '..'))

                    candidate_files = [
                        'PDGA.json',
                        'VIIKKOKISA.json',
                        'known_weekly_competitions.json',
                        'known_pdga_competitions.json',
                        'known_doubles_competitions.json',
                        'DOUBLES.json'
                    ]

                    entries = []
                    for fname in candidate_files:
                        path = os.path.join(root, fname)
                        try:
                            if os.path.exists(path):
                                with open(path, 'r', encoding='utf-8') as f:
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
                        await message.channel.send('Kilpailutietokantaa ei löytynyt.')
                        return

                    fields = ['title', 'name', 'location', 'venue', 'track', 'area', 'place', 'city', 'region', 'kind']
                    matches = []
                    q = query.lower()
                    for e in entries:
                        try:
                            hay = ' '.join(str(e.get(f, '') or '') for f in fields).lower()
                            if q in hay:
                                matches.append(e)
                        except Exception:
                            continue

                    if not matches:
                        await message.channel.send('Ei kilpailuja löytynyt haulla.')
                        return

                    lines = []
                    for e in matches:
                        title = e.get('title') or e.get('name') or ''
                        url = e.get('url') or ''
                        date_text = ''
                        try:
                            if e.get('opening_soon') and e.get('opens_in_days') is not None:
                                date_text = f'avautuu {int(e.get("opens_in_days"))} pv'
                            else:
                                date_field = e.get('date') or e.get('start_date')
                                if date_field:
                                    date_text = str(date_field)
                                else:
                                    m = re.search(r'(\d{1,2}\.\d{1,2}\.\d{2,4})', title)
                                    if m:
                                        date_text = m.group(1)
                        except Exception:
                            date_text = ''

                        kind = (e.get('kind') or '').strip()
                        if 'VIIKKOKISA' in kind.upper():
                            kind_display = ''
                        else:
                            kind_display = f' ({kind})' if kind else ''
                        date_display = f' — {date_text}' if date_text else ''

                        if url:
                            lines.append(f'• [{title}]({url}){kind_display}{date_display}')
                        else:
                            lines.append(f'• {title}{kind_display}{date_display}')

                    # send results chunked
                    max_len = 1900
                    cur = []
                    cur_len = 0
                    for ln in lines:
                        if cur_len + len(ln) + 1 > max_len and cur:
                            try:
                                Embed_cls = getattr(discord, 'Embed', None)
                                if Embed_cls:
                                    embed = Embed_cls(title='Löydetyt kilpailut:', description='\n'.join(cur))
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
                                embed = Embed_cls(title='Löydetyt kilpailut:', description='\n'.join(cur))
                                await message.channel.send(embed=embed)
                            else:
                                await message.channel.send('\n'.join(cur))
                        except Exception:
                            await message.channel.send('\n'.join(cur))
                    return

                # --- !help: competition-related commands ---
                if command == 'help':
                    try:
                        title = 'LakeusBotti — APPI — 3.06'
                        desc = (
                            'Kilpailukomennot:\n'
                            '\n'
                            '!rek — näytä avoimet rekisteröinnit (PDGA / viikon kilpailut)\n'
                            '!etsi <hakusana> — etsi kilpailuja nimen/alueen/radan perusteella\n'
                            '!spots — tarkista kilpailujen jäljellä olevat paikat (alle 20 ilmoittaa)'
                        )
                        Embed_cls = getattr(discord, 'Embed', None)
                        if Embed_cls:
                            embed = Embed_cls(title=title, description=desc)
                            embed.set_footer(text='Käytä komentoja kirjoittamalla viestiin esimerkiksi: !rek')
                            await message.channel.send(embed=embed)
                        else:
                            # fallback to a concise plain text message
                            await message.channel.send(f"**{title}**\n" + desc)
                    except Exception:
                        pass
                    return

                # --- !spots: show competitions with few remaining spots ---
                if command in ('spots', 'paikat', 'capacity'):
                    logger = logging.getLogger(__name__)
                    channel = message.channel

                    # Allow passing JSON via three methods (in priority):
                    # 1) Attachment with a .json file
                    # 2) Inline JSON text following the command
                    # 3) Literal keyword requesting the project's CAPACITY_ALERTS.json
                    provided_res = None
                    arg_text = ' '.join(parts[1:]).strip() if len(parts) > 1 else ''

                    # 1) attachments
                    try:
                        if getattr(message, 'attachments', None):
                            att = message.attachments[0]
                            if att.filename.lower().endswith('.json'):
                                raw = await att.read()
                                try:
                                    provided_res = json.loads(raw.decode('utf-8'))
                                except Exception:
                                    try:
                                        provided_res = json.loads(raw)
                                    except Exception:
                                        provided_res = None
                    except Exception:
                        provided_res = None

                    # 2) inline JSON
                    if provided_res is None and arg_text:
                        if arg_text.startswith('{') or arg_text.startswith('['):
                            try:
                                provided_res = json.loads(arg_text)
                            except Exception:
                                provided_res = None
                        # allow requesting the stored alerts file by name
                        elif arg_text.lower() in ('alerts', 'capacity_alerts.json', 'capacity_alerts', 'capalerts', 'file'):
                            try:
                                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                                alert_path = os.path.join(base_dir, 'CAPACITY_ALERTS.json')
                                if os.path.exists(alert_path):
                                    with open(alert_path, 'r', encoding='utf-8') as f:
                                        provided_res = json.load(f)
                            except Exception:
                                provided_res = None

                    # If no inline/attachment JSON was provided, prefer a recent cached
                    # CAPACITY_ALERTS.json in the project root to avoid running a slow
                    # live scan when the user simply typed `!spots`.
                    try:
                        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                        alert_path = os.path.join(base_dir, 'CAPACITY_ALERTS.json')
                        if provided_res is None and not arg_text and os.path.exists(alert_path):
                            age = time.time() - os.path.getmtime(alert_path)
                            # prefer cache younger than 1 hour (3600s)
                            if age < 3600:
                                try:
                                    with open(alert_path, 'r', encoding='utf-8') as f:
                                        provided_res = json.load(f)
                                    minutes = int(age // 60)
                                    try:
                                        await channel.send(f'Using cached alerts (updated {minutes} minutes ago).')
                                    except Exception:
                                        pass
                                except Exception:
                                    provided_res = None
                    except Exception:
                        provided_res = None

                    # If a JSON payload was provided, use it directly and skip background scan
                    if provided_res is not None:
                        res = provided_res if isinstance(provided_res, list) else (provided_res.get('alerts') if isinstance(provided_res, dict) and provided_res.get('alerts') else [])
                        if not res:
                            await channel.send('Ei paikkoja ilmoituksissa (JSON tyhjä).')
                            return

                        # Build lines and send immediately (no background task)
                        lines = []
                        for c in res[:200]:
                            name = c.get('title') or c.get('name') or c.get('name_en') or c.get('event') or ''
                            url = c.get('url') or ''
                            reg = c.get('registered')
                            lim = c.get('limit')
                            rem = c.get('remaining')
                            # prefer computing remaining from reg/lim when possible
                            if reg is not None and lim is not None:
                                try:
                                    calc_rem = int(lim) - int(reg)
                                except Exception:
                                    calc_rem = rem
                                if calc_rem is None:
                                    rem_txt = '?'
                                elif calc_rem >= 0:
                                    rem_txt = f'{calc_rem} left'
                                else:
                                    rem_txt = f'over by {abs(int(calc_rem))}'
                                disp = f'{reg}/{lim} ({rem_txt})'
                            elif reg is not None and lim is None:
                                disp = f'{reg}/?'
                            elif reg is None and lim is not None:
                                disp = f'?/{lim} ({rem if rem is not None else "?"} left)'
                            else:
                                disp = f'järjellä {rem if rem is not None else "?"} paikkaa'

                            if url:
                                lines.append(f'• [{name}]({url}) — {disp}')
                            else:
                                lines.append(f'• {name} — {disp}')

                        max_len = 1900
                        cur = []
                        cur_len = 0
                        for ln in lines:
                            if cur and cur_len + len(ln) + 1 > max_len:
                                try:
                                    Embed_cls = getattr(discord, 'Embed', None)
                                    if Embed_cls:
                                        embed = Embed_cls(title='Kilpailut, joissa vähän paikkoja:', description='\n'.join(cur))
                                        await channel.send(embed=embed)
                                    else:
                                        await channel.send('\n'.join(cur))
                                except Exception:
                                    await channel.send('\n'.join(cur))
                                cur = []
                                cur_len = 0
                            cur.append(ln)
                            cur_len += len(ln) + 1

                        if cur:
                            try:
                                Embed_cls = getattr(discord, 'Embed', None)
                                if Embed_cls:
                                    embed = Embed_cls(title='Kilpailut, joissa vähän paikkoja:', description='\n'.join(cur))
                                    await channel.send(embed=embed)
                                else:
                                    await channel.send('\n'.join(cur))
                            except Exception:
                                await channel.send('\n'.join(cur))
                        return

                    # Otherwise perform the background capacity check as before
                    await channel.send('Checking spot availability (this runs in background)...')

                    loop = asyncio.get_running_loop()

                    def run_check():
                        try:
                            return capacity_mod.find_low_capacity()
                        except Exception as e:
                            logger.exception('Error in capacity check: %s', e)
                            return e

                    future = loop.run_in_executor(None, run_check)

                    async def handle_result(fut):
                        res = await fut
                        if isinstance(res, Exception):
                            await channel.send(f'Error checking spots: {res}')
                            return
                        if not res:
                            await channel.send('No low-capacity events found.')
                            return

                        # Build lines and chunk into Discord-safe messages (<= ~2000 chars)
                        lines = []
                        for c in res[:200]:
                            name = c.get('title') or c.get('name') or c.get('name_en') or c.get('event') or ''
                            url = c.get('url') or ''
                            reg = c.get('registered')
                            lim = c.get('limit')
                            rem = c.get('remaining')
                            if reg is not None and lim is not None:
                                try:
                                    calc_rem = int(lim) - int(reg)
                                except Exception:
                                    calc_rem = rem
                                if calc_rem is None:
                                    rem_txt = '?'
                                elif calc_rem >= 0:
                                    rem_txt = f'{calc_rem} left'
                                else:
                                    rem_txt = f'over by {abs(int(calc_rem))}'
                                disp = f'{reg}/{lim} ({rem_txt})'
                            elif reg is not None and lim is None:
                                disp = f'{reg}/?'
                            elif reg is None and lim is not None:
                                disp = f'?/{lim} ({rem if rem is not None else "?"} left)'
                            else:
                                disp = f'järjellä {rem if rem is not None else "?"} paikkaa'
                            lines.append(f'• {name} — {disp} — {url}')

                        max_len = 1900
                        cur = []
                        cur_len = 0
                        for ln in lines:
                            if cur and cur_len + len(ln) + 1 > max_len:
                                try:
                                    Embed_cls = getattr(discord, 'Embed', None)
                                    if Embed_cls:
                                        embed = Embed_cls(title='Kilpailut, joissa vähän paikkoja:', description='\n'.join(cur))
                                        await channel.send(embed=embed)
                                    else:
                                        await channel.send('\n'.join(cur))
                                except Exception:
                                    await channel.send('\n'.join(cur))
                                cur = []
                                cur_len = 0
                            cur.append(ln)
                            cur_len += len(ln) + 1

                        if cur:
                            try:
                                Embed_cls = getattr(discord, 'Embed', None)
                                if Embed_cls:
                                    embed = Embed_cls(title='Kilpailut, joissa vähän paikkoja:', description='\n'.join(cur))
                                    await channel.send(embed=embed)
                                else:
                                    await channel.send('\n'.join(cur))
                            except Exception:
                                await channel.send('\n'.join(cur))

                    asyncio.create_task(handle_result(future))
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
