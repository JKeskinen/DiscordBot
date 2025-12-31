import threading
import time
import os
import json
import re

try:
    import discord  # type: ignore[import]
except Exception:
    discord = None

Intents = getattr(discord, 'Intents', None)
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
