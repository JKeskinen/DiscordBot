import threading
import time
import os

try:
    import discord
    from discord import Intents
except Exception:
    discord = None


class PresenceThread(threading.Thread):
    def __init__(self, token, status_message=None, run_forever=True):
        super().__init__(daemon=True)
        # normalize token if it was stored with surrounding quotes in .env
        if isinstance(token, str):
            token = token.strip()
            if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
                token = token[1:-1]
        self.token = token
        self.status_message = status_message or 'MetrixBot'
        self.run_forever = run_forever
        self.client = None

    def run(self):
        if discord is None:
            print('discord.py not installed; presence disabled')
            return

        intents = Intents.none()
        client = discord.Client(intents=intents)
        self.client = client

        @client.event
        async def on_ready():
            try:
                activity = discord.Activity(type=discord.ActivityType.watching, name=self.status_message)
                await client.change_presence(status=discord.Status.online, activity=activity)
                print(f'Presence client connected as {client.user} — status set to online')
                print('Connected')
            except Exception as e:
                print('Failed to set presence:', e)
            if not self.run_forever:
                # disconnect shortly after setting presence
                await client.close()

        try:
            client.run(self.token, reconnect=True)
        except Exception as e:
            print('Presence client run error:', e)


def start_presence(token: str, status_message: str = None, run_forever: bool = True):
    # tolerate tokens with surrounding quotes from .env files
    if isinstance(token, str):
        token = token.strip()
        if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
            token = token[1:-1]

    if not token:
        print('No token provided for presence; skipping')
        return None
    pt = PresenceThread(token, status_message=status_message, run_forever=run_forever)
    pt.start()
    # give a little time for the thread to start
    time.sleep(0.5)
    return pt
