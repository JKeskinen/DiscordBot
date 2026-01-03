from dotenv import load_dotenv
load_dotenv()
import os
import time
import komento_koodit.discord_presence as dp

token = os.environ.get('DISCORD_TOKEN') or os.environ.get('BOT_TOKEN')
if not token:
    print('No DISCORD_TOKEN or BOT_TOKEN found in environment; aborting')
else:
    # Use explicit status text here so the presence matches the
    # LakeusBotti branding instead of the old MetrixBot name.
    dp.start_presence(token, 'LakeusBotti', True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
