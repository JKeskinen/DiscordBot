import sys, os, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__) or '.', '..')))
from komento_koodit import commands_tulokset as ct

class FakeChannel:
    def __init__(self):
        pass
    async def send(self, *args, **kwargs):
        # Print embed content if provided
        if 'embed' in kwargs and kwargs['embed'] is not None:
            try:
                e = kwargs['embed']
                title = getattr(e, 'title', None)
                desc = getattr(e, 'description', None)
                url = getattr(e, 'url', None)
                print('\n--- EMBED ---')
                if title:
                    print('Title:', title)
                if url:
                    print('URL:', url)
                if desc:
                    print(desc)
                print('--- END EMBED ---\n')
            except Exception:
                print('Embed:', kwargs['embed'])
        else:
            # Print positional concatenation
            out = ' '.join(str(a) for a in args) if args else ''
            print(out)
    async def trigger_typing(self):
        return

class FakeMessage:
    def __init__(self):
        self.channel = FakeChannel()

async def run():
    msg = FakeMessage()
    parts = ['!tulokset', 'mk']
    await ct.handle_tulokset(msg, parts)

if __name__ == '__main__':
    asyncio.run(run())
