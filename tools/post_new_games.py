"""Detect new PDGA games and post them to Discord using existing helper.

Usage:
  python tools/post_new_games.py [--dry-run]

By default runs in dry-run mode and will not call Discord when `--dry-run` is set.
"""
import os
import sys
import json
import sqlite3
import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from komento_koodit import post_pending_registration as ppr
from komento_koodit import search_pdga_sfl as pdga_mod

DB = os.path.join(ROOT, 'data', 'discordbot.db')

def load_pdga_from_db(conn):
    cur = conn.cursor()
    cur.execute("SELECT content FROM json_store WHERE name='PDGA'")
    r = cur.fetchone()
    if not r or not r[0]:
        return []
    try:
        return json.loads(r[0])
    except Exception:
        return []

def mark_published(conn, rec):
    # rec is PDGA entry dict; insert minimal columns into PUBLISHED_GAMES
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    title = rec.get('name') or rec.get('title') or rec.get('id')
    pid = str(rec.get('id') or '')
    url = rec.get('url') or ''
    try:
        cur.execute("INSERT INTO PUBLISHED_GAMES (title, id, published, url) VALUES (?, ?, ?, ?)", (title, pid, now, url))
        conn.commit()
    except Exception as e:
        print('Failed to mark published:', e)

def prepare_items(pdga_entries):
    items = []
    for g in pdga_entries:
        it = {}
        it['id'] = g.get('id')
        it['name'] = g.get('name') or g.get('title') or g.get('id')
        it['title'] = it['name']
        it['url'] = g.get('url') or g.get('link')
        it['date'] = g.get('date')
        # optional flags used by embed builder
        it['registration_open'] = g.get('registration_open', False)
        it['opening_soon'] = g.get('opening_soon', False)
        items.append(it)
    return items

def main(dry_run=True):
    if not os.path.exists(DB):
        print('DB missing at', DB)
        return
    conn = sqlite3.connect(DB)
    try:
        pdga = load_pdga_from_db(conn)
        if not pdga:
            print('No PDGA entries in json_store; fetching live')
            pdga = pdga_mod.fetch_competitions(pdga_mod.DEFAULT_URL)
            pdga = [c for c in pdga if pdga_mod.is_pdga_entry(c)]
            pdga_mod.save_pdga_list(pdga, None)
        cur = conn.cursor()
        cur.execute('SELECT id FROM PUBLISHED_GAMES')
        published = set(r[0] for r in cur.fetchall())
        # Filter out small 'kierros' round entries (e.g. "1. Kierros")
        import re
        def is_kierros(name):
            if not name:
                return False
            n = str(name).strip()
            # match patterns like '1. Kierros', '2. Kierros' (case-insensitive)
            if re.match(r"^\s*\d+\.\s*kierros\b", n, flags=re.IGNORECASE):
                return True
            # also skip single-word 'kierros'
            if n.lower() == 'kierros':
                return True
            return False

        new_games = [g for g in pdga if str(g.get('id')) not in published and not is_kierros(g.get('name') or g.get('title'))]
        print('Detected new PDGA games:', len(new_games))
        if not new_games:
            return
        items = prepare_items(new_games)
        # Use embed builder from existing module
        embeds = ppr.build_embeds_with_title(items, f"Uudet kilpailut ({len(items)})", 3447003)
        # Dry-run: print preview
        if dry_run:
            print('Dry-run: would post the following embeds (first embed shown):')
            try:
                print(json.dumps(embeds[0], ensure_ascii=False, indent=2)[:4000])
            except Exception:
                print(embeds[0])
            return
        # Real post
        ok = ppr.post_embeds(ppr.PDGA_THREAD, embeds)
        if ok:
            for g in new_games:
                mark_published(conn, g)
            print('Posted and marked', len(new_games), 'games as published')
        else:
            print('Failed to post embeds')
    finally:
        conn.close()

if __name__ == '__main__':
    dry = True
    if '--live' in sys.argv or '--no-dry-run' in sys.argv:
        dry = False
    main(dry_run=dry)
