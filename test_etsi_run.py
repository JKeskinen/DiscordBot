import asyncio
from types import SimpleNamespace
import komento_koodit.commands_etsi as ce

class MockChannel:
    async def send(self, *args, **kwargs):
        print('SEND:', args[0] if args else kwargs)

class MockMessage:
    def __init__(self):
        self.channel = MockChannel()

async def run_test():
    msg = MockMessage()
    parts = ['!etsi','luokka','900']
    await ce.handle_etsi(msg, parts)

if __name__ == '__main__':
    asyncio.run(run_test())
