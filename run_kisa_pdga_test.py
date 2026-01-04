import asyncio
import sys
import os

# ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from komento_koodit import commands_etsi

class FakeChannel:
    def __init__(self):
        self.id = 'test'
        self.name = 'test-channel'
    async def send(self, *args, **kwargs):
        # emulate discord send behavior: print what would be sent
        if args and kwargs.get('embed') is None:
            print('\n[CHANNEL SEND]')
            for a in args:
                print(a)
        elif kwargs.get('embed') is not None:
            em = kwargs.get('embed')
            print('\n[CHANNEL SEND EMBED]')
            try:
                # discord.Embed-like: show title and description if available
                title = getattr(em, 'title', None)
                desc = getattr(em, 'description', None)
                if title:
                    print('Title:', title)
                if desc:
                    print('Description:\n', desc)
                # if embed has fields, try to print them
                fields = getattr(em, 'fields', None)
                if fields:
                    print('\nFields:')
                    for f in fields:
                        print('-', getattr(f, 'name', ''), ':', getattr(f, 'value', ''))
            except Exception:
                print(repr(em))
        else:
            print('\n[CHANNEL SEND] (no args)')

class FakeAuthor:
    def __str__(self):
        return 'TestUser#0001'

class FakeMessage:
    def __init__(self):
        self.channel = FakeChannel()
        self.author = FakeAuthor()

async def main():
    msg = FakeMessage()
    parts = ['!kisa', 'pdga']
    await commands_etsi.handle_kisa(msg, parts)

if __name__ == '__main__':
    asyncio.run(main())
