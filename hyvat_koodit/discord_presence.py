import threading
import time
import os
from typing import Optional

try:
    import discord
except Exception:
    discord = None


class PresenceThread(threading.Thread):
    def __init__(self, token: Optional[str], status_message: Optional[str] = None, run_forever: bool = True):
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
        # At this point discord is present; help the type checker
        assert discord is not None
        discord_mod = discord
        # Resolve Intents at runtime after confirming discord is available
        Intents = getattr(discord_mod, 'Intents', None)
        if Intents is None:
            intents = None
        else:
            intents = Intents.none()
        client_kwargs = {}
        if intents is not None:
            client_kwargs['intents'] = intents
        client = discord_mod.Client(**client_kwargs)
        self.client = client

        @client.event
        async def on_ready():
            try:
                Activity = getattr(discord_mod, 'Activity', None)
                ActivityType = getattr(discord_mod, 'ActivityType', None)
                Status = getattr(discord_mod, 'Status', None)
                if Activity is not None and ActivityType is not None and Status is not None:
                    activity = Activity(type=ActivityType.watching, name=self.status_message)
                    await client.change_presence(status=Status.online, activity=activity)
                print(f'Presence client connected as {client.user} — status set to online')
                print('Connected')
            except Exception as e:
                print('Failed to set presence:', e)
            if not self.run_forever:
                # disconnect shortly after setting presence
                await client.close()

        # ensure token is present and typed as str for the client.run() call
        if not isinstance(self.token, str) or not self.token:
            print('No token available for presence client; aborting')
            return
        token_local = self.token
        try:
            client.run(token_local, reconnect=True)
        except Exception as e:
            print('Presence client run error:', e)


def start_presence(token: Optional[str], status_message: Optional[str] = None, run_forever: bool = True):
    # tolerate tokens with surrounding quotes from .env files
    if isinstance(token, str):
        token = token.strip()
        if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
            token = token[1:-1]

    if not token:
        print('Ei tokenia, läsnäolo ohitetaan')
        return None
    pt = PresenceThread(token, status_message=status_message, run_forever=run_forever)
    pt.start()
    # give a little time for the thread to start
    time.sleep(0.5)
    return pt
