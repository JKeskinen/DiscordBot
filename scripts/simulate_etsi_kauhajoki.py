import asyncio
import importlib.util
import os
import sys

# Load commands_etsi module by file path to avoid package import issues
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODULE_DIR = os.path.join(ROOT, "komento_koodit")
MODULE_PATH = os.path.join(MODULE_DIR, "commands_etsi.py")
# ensure a package module exists for relative imports
pkg_name = "komento_koodit"
if pkg_name not in sys.modules:
    pkg = importlib.util.module_from_spec(importlib.util.spec_from_loader(pkg_name, loader=None))
    pkg.__path__ = [MODULE_DIR]
    sys.modules[pkg_name] = pkg

spec = importlib.util.spec_from_file_location(f"{pkg_name}.commands_etsi", MODULE_PATH)
commands_etsi = importlib.util.module_from_spec(spec)
sys.modules[f"{pkg_name}.commands_etsi"] = commands_etsi
spec.loader.exec_module(commands_etsi)

class FakeChannel:
    async def send(self, content=None, **kwargs):
        print("--- SEND START ---")
        if content is None and kwargs.get('embed') is not None:
            e = kwargs['embed']
            # try common Embed attrs
            try:
                if hasattr(e, "to_dict"):
                    d = e.to_dict()
                    print(f"Title: {d.get('title')}")
                    print(f"Description:\n{d.get('description')}")
                    fields = d.get('fields') or []
                    for f in fields:
                        print(f"- {f.get('name')}: {f.get('value')}")
                else:
                    print(f"Embed title: {getattr(e, 'title', None)}")
                    print(f"Embed desc: {getattr(e, 'description', None)}")
            except Exception:
                print(repr(e))
        else:
            print(content)
        print("--- SEND END ---\n")

class FakeMessage:
    def __init__(self):
        self.channel = FakeChannel()

async def run():
    msg = FakeMessage()
    await commands_etsi.handle_etsi(msg, ["!etsi", "kauhajoki"]) 

if __name__ == '__main__':
    asyncio.run(run())
