import threading
import time
import os
import json

try:
    import discord
    from discord import Intents
except Exception:
    discord = None


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

        intents = Intents.default()
        intents.message_content = True
        intents.messages = True
        client = discord.Client(intents=intents)
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
                if not content.lower().startswith(self.prefix + 'rek'):
                    return

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
                    if pdga_thread and channel_id == str(pdga_thread):
                        entries = [e for e in entries if (e.get('kind') or '').upper() == 'PDGA']
                    elif weekly_thread and channel_id == str(weekly_thread):
                        entries = [e for e in entries if (e.get('kind') or '').upper() != 'PDGA']
                except Exception:
                    pass

                if not entries:
                    await message.channel.send('Tässä kanavassa ei löytynyt rekisteröitymisiä.')
                    return

                # Build a concise reply (limit message length)
                lines = []
                for e in entries:
                    title = e.get('title') or e.get('name') or ''
                    url = e.get('url') or ''
                    kind = e.get('kind') or ''
                    if url:
                        lines.append(f'• [{title}]({url}) ({kind})')
                    else:
                        lines.append(f'• {title} ({kind})')

                # Discord max message ~2000 chars; chunk if needed
                max_len = 1900
                cur = []
                cur_len = 0
                for ln in lines:
                    if cur_len + len(ln) + 1 > max_len and cur:
                        await message.channel.send('\n'.join(cur))
                        cur = []
                        cur_len = 0
                    cur.append(ln)
                    cur_len += len(ln) + 1

                if cur:
                    await message.channel.send('\n'.join(cur))
            except Exception as ex:
                try:
                    await message.channel.send('Virhe tarkistaaksesi rekisteröinnit: ' + str(ex))
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
