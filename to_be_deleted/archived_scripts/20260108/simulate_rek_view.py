import json
import os
import sys
# ensure project root is on sys.path so komento_koodit can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from komento_koodit import post_pending_registration as post


def main():
    pending = post.load_pending()
    if not pending:
        print('No pending registrations found.')
        return

    pdga = [it for it in pending if 'PDGA' in (it.get('kind') or '').upper()]
    weekly = [it for it in pending if 'PDGA' not in (it.get('kind') or '').upper()]

    if pdga:
        pdga_open = [it for it in pdga if it.get('registration_open')]
        if pdga_open:
            embeds = post.build_embeds_with_title(pdga_open, f"REKISTERÖINTI AVOINNA ({len(pdga_open)})", 5763714)
            print('--- PDGA OPEN EMBEDS ---')
            print(json.dumps(embeds, ensure_ascii=False, indent=2))

    if weekly:
        weekly_open = [it for it in weekly if it.get('registration_open')]
        if weekly_open:
            embeds = post.build_embeds_with_title(weekly_open, f"REKISTERÖINTI AVOINNA ({len(weekly_open)})", 5763714)
            print('--- WEEKLY OPEN EMBEDS ---')
            print(json.dumps(embeds, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
