#!/usr/bin/env python3
"""
Simplified Metrix fetcher.

- Fetches competitions from DiscGolfMetrix server endpoint for 2026.
- Classifies competitions: clubid=1 (SFL) => PDGA.json; others => VIIKKOKISA.json or DOUBLES.json.
- Only writes these three files: PDGA.json, VIIKKOKISA.json, DOUBLES.json.
- Supports `--once` (run immediately) and `--daemon` (run daily at 04:00 local time).
- If `DISCORD_TOKEN` and `DISCORD_THREAD_ID` are set in env, posts a short summary message to that thread.

Designed to be minimal and easy to run during testing.
"""
import argparse
import json
import os
import re
import time
from datetime import datetime, date, timedelta
from typing import List, Dict

import requests
from bs4 import BeautifulSoup


def _load_dotenv_if_exists(path: str = ".env"):
    """Lightweight .env loader: set env vars only if not already set."""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v and os.environ.get(k) is None:
                    os.environ[k] = v
    except Exception:
        pass

# Load .env automatically if present
_load_dotenv_if_exists()

# Output files (only these will be created/overwritten)
PDGA_FILE = "PDGA.json"
WEEKLY_FILE = "VIIKKOKISA.json"
DOUBLES_FILE = "DOUBLES.json"

# DiscGolfMetrix server endpoint date window (2026)
DATE1 = os.environ.get("METRIX_DATE1", "2026-01-01")
DATE2 = os.environ.get("METRIX_DATE2", "2027-01-01")

# SFL club id (per user's requirement)
SFL_CLUB_ID = os.environ.get("SFL_CLUB_ID", "1")

# Discord posting (optional): provide a Bot token and a thread/channel id
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_THREAD_ID = os.environ.get("DISCORD_THREAD_ID")

USER_AGENT = {"User-Agent": "Mozilla/5.0 (metrix-fetcher)"}

def fetch_server_competitions(clubid: str = None) -> List[Dict]:
    """Fetch competitions via the competitions_server.php endpoint and parse basic info.

    If clubid is provided, we include clubid param to restrict results.
    Returns a list of competitions as dicts: {id, name, url}
    """
    base = (
        "https://discgolfmetrix.com/competitions_server.php?name=&date1={date1}&date2={date2}"
        + "&registration_date1=&registration_date2=&from=1&to=500&page=all"
    )
    url = base.format(date1=DATE1, date2=DATE2)
    if clubid:
        url += f"&clubid={clubid}&clubtype=1"
    try:
        r = requests.get(url, headers=USER_AGENT, timeout=20)
        r.raise_for_status()
        content = r.content
    except Exception as e:
        print(f"Failed to fetch server endpoint: {e}")
        return []

    soup = BeautifulSoup(content, "html.parser")
    container = soup.find(id="competition_list2") or soup

    comps = []
    seen = set()

    # 1) anchors with class gridlist (preferred)
    for a in container.select("a.gridlist"):
        href = a.get("href") or ""
        name = (a.get_text() or "").strip()
        cid = _extract_id_from_href(href)
        url_full = _absolute_url(href)
        if cid and cid not in seen:
            comps.append({"id": cid, "name": name, "url": url_full})
            seen.add(cid)

    # 2) table rows fallback
    for tr in container.select("table.table-list tbody tr"):
        a = tr.find("a")
        if not a:
            continue
        href = a.get("href") or ""
        name = (a.get_text() or "").strip()
        cid = _extract_id_from_href(href)
        url_full = _absolute_url(href)
        if cid and cid not in seen:
            comps.append({"id": cid, "name": name, "url": url_full})
            seen.add(cid)

    # 3) any anchor with competition id in href as last resort
    if not comps:
        for a in container.find_all("a"):
            href = a.get("href") or ""
            cid = _extract_id_from_href(href)
            name = (a.get_text() or "").strip()
            url_full = _absolute_url(href)
            if cid and cid not in seen:
                comps.append({"id": cid, "name": name, "url": url_full})
                seen.add(cid)

    return comps


def _extract_id_from_href(href: str) -> str:
    if not href:
        return ""
    m = re.search(r"(?:id=)(\d+)", href)
    if m:
        return m.group(1)
    # sometimes the URL contains /competition/<id>
    m2 = re.search(r"/competition/(\d+)", href)
    if m2:
        return m2.group(1)
    return ""


def _absolute_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://discgolfmetrix.com{href}"
    return f"https://discgolfmetrix.com/{href}"


def classify_and_split(all_comps: List[Dict], sfl_comps: List[Dict]):
    """Given full competition list and SFL list, split into three lists.

    - Any competition whose id is in sfl_comps -> PDGA
    - Else: if name contains pair/doubles keywords -> DOUBLES
    - Else -> VIIKKOKISA
    """
    sfl_ids = {c["id"] for c in sfl_comps}
    doubles_keywords = ["pari", "parikisa", "pair", "pairs", "double", "doubles", "best shot"]
    pdga = []
    doubles = []
    weeklies = []

    for c in all_comps:
        cid = c.get("id")
        name = (c.get("name") or "").lower()
        if cid in sfl_ids:
            pdga.append(c)
            continue
        if any(k in name for k in doubles_keywords):
            doubles.append(c)
        else:
            weeklies.append(c)

    return pdga, weeklies, doubles


def load_json(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []


def save_json(path: str, data: List[Dict]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def post_to_discord(thread_id: str, message: str):
    """Post a simple text message to a channel/thread using Bot token (if provided).

    This uses the HTTP API directly to avoid discord.py dependency.
    """
    if not DISCORD_TOKEN or not thread_id:
        print("Discord token or thread id not set; skipping post.")
        print(message)
        return
    url = f"https://discord.com/api/v10/channels/{thread_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}", "Content-Type": "application/json"}
    body = {"content": message}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        if r.status_code >= 400:
            print(f"Discord post failed {r.status_code}: {r.text}")
        else:
            print("Posted summary to Discord.")
    except Exception as e:
        print(f"Failed to post to Discord: {e}")


def run_once():
    """One-shot fetch, classification, file writes, and (optional) Discord summary."""
    print("Fetching SFL (clubid={}) competitions...".format(SFL_CLUB_ID))
    sfl = fetch_server_competitions(clubid=SFL_CLUB_ID)
    print(f"SFL fetched: {len(sfl)} competitions")

    print("Fetching all competitions for 2026...")
    allc = fetch_server_competitions(clubid=None)
    print(f"All fetched: {len(allc)} competitions")

    pdga_new, week_new, dbl_new = classify_and_split(allc, sfl)

    # Load existing files and merge (we append only new unique items by id)
    existing_pdga = {c.get("id") for c in load_json(PDGA_FILE)}
    existing_week = {c.get("id") for c in load_json(WEEKLY_FILE)}
    existing_dbl = {c.get("id") for c in load_json(DOUBLES_FILE)}

    # Build final lists (union existing + new), keep simple unique by id
    def union_by_id(existing_path, existing_ids, new_list):
        merged = []
        # add existing items first
        for c in load_json(existing_path):
            if c.get("id"):
                merged.append(c)
        # append new ones that aren't present
        for c in new_list:
            if c.get("id") not in existing_ids:
                merged.append(c)
        return merged

    final_pdga = union_by_id(PDGA_FILE, existing_pdga, pdga_new)
    final_week = union_by_id(WEEKLY_FILE, existing_week, week_new)
    final_dbl = union_by_id(DOUBLES_FILE, existing_dbl, dbl_new)

    # Save only the three files
    save_json(PDGA_FILE, final_pdga)
    save_json(WEEKLY_FILE, final_week)
    save_json(DOUBLES_FILE, final_dbl)

    # Determine which items are newly added this run for notification
    added = {
        "PDGA": [c for c in pdga_new if c.get("id") not in existing_pdga],
        "VIIKKOKISA": [c for c in week_new if c.get("id") not in existing_week],
        "DOUBLES": [c for c in dbl_new if c.get("id") not in existing_dbl],
    }

    total_new = sum(len(v) for v in added.values())
    if total_new == 0:
        print("No new competitions found.")
        return

    # Build a short summary message
    lines = [f"Uusia kilpailuja löydetty: {total_new}"]
    for k in ("PDGA", "VIIKKOKISA", "DOUBLES"):
        cnt = len(added.get(k, []))
        lines.append(f" - {k}: {cnt}")
    lines.append("")
    for k in ("PDGA", "VIIKKOKISA", "DOUBLES"):
        for c in added.get(k, [])[:20]:
            name = c.get("name")
            url = c.get("url")
            lines.append(f"[{k}] {name} — {url}")

    message = "\n".join(lines)

    # Post to Discord thread if configured (otherwise print)
    post_to_discord(DISCORD_THREAD_ID, message)


def _seconds_until_next(hour=4, minute=0):
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


def run_daemon():
    print("Starting daemon: will run daily at 04:00 local time")
    while True:
        secs = _seconds_until_next(4, 0)
        print(f"Sleeping until next run in {int(secs)} seconds...")
        time.sleep(secs)
        try:
            run_once()
        except Exception as e:
            print(f"Run failed: {e}")
        # small sleep to avoid edge-case double-run
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Simplified Metrix fetcher (PDGA/Weekly/Doubles)")
    parser.add_argument("--once", action="store_true", help="Run once and exit (default)")
    parser.add_argument("--daemon", action="store_true", help="Run daily at 04:00")
    args = parser.parse_args()

    # Default behavior: run once
    if args.daemon:
        run_daemon()
    else:
        run_once()


if __name__ == "__main__":
    main()
try:
    import discord
except Exception:
    discord = None
import requests
import asyncio
import os
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import time
from dotenv import load_dotenv
import argparse

# Simple in-memory short-lived cache to deduplicate rapid fetches
_fetch_cache = {
    'ts': 0.0,
    'data': None,
    'ttl': 30  # seconds
}

def _cache_and_return(data):
    _fetch_cache['ts'] = time.time()
    _fetch_cache['data'] = data
    return data


def is_competition_page_pdga(url: str) -> bool:
    """Fetch the competition page and look for PDGA indicators."""
    if not url:
        return False
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return False
        txt = resp.text.lower()
        # simple heuristics: presence of 'pdga' or 'sanction' or 'pdga event' text
        if 'pdga' in txt or 'sanction' in txt or 'pdga event' in txt:
            return True
    except Exception:
        return False
    return False


def parse_metrix_date(s: str) -> str:
    """Parse various date formats returned by Metrix and return DD/MM/YYYY or DD/MM/YYYY HH:MM."""
    if not s:
        return ""
    s = s.strip()
    # Try to extract a date/time substring using regex to handle noisy cells
    # Patterns: mm/dd/yy[yy] optionally with time, dd.mm.yyyy optionally with time, ISO
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})(?:\s+([0-2]?\d:[0-5]\d(?::[0-5]\d)?))?", s)
    if m:
        datepart = m.group(1)
        timepart = m.group(2)
        # handle mm/dd/yy or mm/dd/yyyy
        try:
            mm, dd, yy = datepart.split('/')
            if len(yy) == 2:
                yy = '20' + yy
            fmt = "%m/%d/%Y"
            if timepart:
                # normalize time to HH:MM
                tparts = timepart.split(":")
                tp = ":".join(tparts[:2])
                dt = datetime.strptime(f"{mm}/{dd}/{yy} {tp}", fmt + " %H:%M")
                return dt.strftime("%d/%m/%Y %H:%M")
            dt = datetime.strptime(f"{mm}/{dd}/{yy}", fmt)
            return dt.strftime("%d/%m/%Y")
        except Exception:
            pass

    m2 = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})(?:\s+([0-2]?\d:[0-5]\d))?", s)
    if m2:
        datepart = m2.group(1)
        timepart = m2.group(2)
        try:
            fmt = "%d.%m.%Y"
            if timepart:
                dt = datetime.strptime(f"{datepart} {timepart}", fmt + " %H:%M")
                return dt.strftime("%d/%m/%Y %H:%M")
            dt = datetime.strptime(datepart, fmt)
            return dt.strftime("%d/%m/%Y")
        except Exception:
            pass

    # ISO-like
    m3 = re.search(r"(\d{4}-\d{2}-\d{2})(?:\s+([0-2]?\d:[0-5]\d(?::[0-5]\d)?))?", s)
    if m3:
        datepart = m3.group(1)
        timepart = m3.group(2)
        try:
            fmt = "%Y-%m-%d"
            if timepart:
                dt = datetime.strptime(f"{datepart} {timepart}", fmt + " %H:%M:%S")
                return dt.strftime("%d/%m/%Y %H:%M")
            dt = datetime.strptime(datepart, fmt)
            return dt.strftime("%d/%m/%Y")
        except Exception:
            pass

    # Fallback: try to parse clean tokens
    tokens = re.split(r"[\s\-–—]+", s)
    for tok in reversed(tokens):
        tok = tok.strip()
        if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", tok):
            try:
                mm, dd, yy = tok.split('/')
                if len(yy) == 2:
                    yy = '20' + yy
                dt = datetime.strptime(f"{mm}/{dd}/{yy}", "%m/%d/%Y")
                return dt.strftime("%d/%m/%Y")
            except Exception:
                continue
    # Final best-effort: if string still looks like mm/dd/yy maybe with time, convert
    m_final = re.search(r"^(\d{1,2})/(\d{1,2})/(\d{2})(?:\s+(\d{1,2}:\d{2}))?$", s)
    if m_final:
        mm, dd, yy, timepart = m_final.group(1), m_final.group(2), m_final.group(3), m_final.group(4)
        try:
            yy = '20' + yy
            if timepart:
                dt = datetime.strptime(f"{mm}/{dd}/{yy} {timepart}", "%m/%d/%Y %H:%M")
                return dt.strftime("%d/%m/%Y %H:%M")
            dt = datetime.strptime(f"{mm}/{dd}/{yy}", "%m/%d/%Y")
            return dt.strftime("%d/%m/%Y")
        except Exception:
            pass

    return s

# Lataa .env (valinnainen)
load_dotenv()

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

DISCORD_CHANNEL_ID = 1241453177979797584
# Optional: prefer posting new-competition notifications into a specific thread
DISCORD_THREAD_ID = int(os.environ.get("DISCORD_THREAD_ID", "1241493648080764988"))
# Weekly digest / local weekly alerts (100km default). Set WEEKLY_LOCATION to a city or area name to filter.
DISCORD_WEEKLY_THREAD_ID = int(os.environ.get("DISCORD_WEEKLY_THREAD_ID", "1455647584583417889"))
WEEKLY_JSON = os.environ.get("WEEKLY_JSON", "weekly_pair.json")
WEEKLY_LOCATION = os.environ.get("WEEKLY_LOCATION", "Etelä-Pohjanmaa").strip().lower()
WEEKLY_RADIUS_KM = int(os.environ.get("WEEKLY_RADIUS_KM", "100"))
WEEKLY_SEARCH_URL = os.environ.get("WEEKLY_SEARCH_URL", "https://discgolfmetrix.com/?u=competitions_all&view=1&competition_name=&period=&date1=2026-01-01&date2=2027-01-01&my_country=&registration_open=&registration_date1=&registration_date2=&country_code=FI&my_club=0&club_type=&club_id=&association_id=0&close_to_me=&area=Etelä-Pohjanmaa&city=&course_id=&division=&my=&view=1&sort_name=&sort_order=&my_all=&from=1&to=30")

METRIX_URL = "https://discgolfmetrix.com/?u=competitions_all&view=2&competition_name=&period=&date1=2026-01-01&date2=2027-01-01&my_country=&registration_open=&registration_date1=&registration_date2=&country_code=FI&my_club=&club_type=&club_id=&association_id=0&close_to_me=&area=&city=&course_id=&type=C&division=&my=&view=2&sort_name=&sort_order=&my_all="
AUTO_LIST_INTERVAL = 86400  # Daily automatic posts
CHECK_INTERVAL = 600  # 10 min
CHECK_REGISTRATION_INTERVAL = 3600  # 1 h
CACHE_FILE = "known_pdga_competitions.json"
REG_CHECK_FILE = "pending_registration.json"

if discord:
    intents = discord.Intents.default()
    # Allow reading message content so commands like !testprint work
    intents.message_content = True
    client = discord.Client(intents=intents)
else:
    client = None

def build_metrix_url(association_id=1, type_code=None, country_code='FI', date1='2026-01-01', date2='2027-01-01', area=WEEKLY_LOCATION, view=2):
    params = {
        'u': 'competitions_all',
        'view': str(view),
        'competition_name': '',
        'period': '',
        'date1': date1,
        'date2': date2,
        'my_country': '',
        'registration_open': '',
        'registration_date1': '',
        'registration_date2': '',
        'country_code': country_code,
        'my_club': '',
        'club_type': '',
        'club_id': '',
        'association_id': str(association_id),
        'close_to_me': '',
        'area': area,
        'city': '',
        'course_id': '',
        
        'division': '',
        'my': '',
        'sort_name': '',
        'sort_order': '',
        'my_all': ''
    }
    # Only include 'type' param when filtering by a specific tier
    if type_code:
        params['type'] = type_code
    from urllib.parse import urlencode
    return f"https://discgolfmetrix.com/?{urlencode(params)}"


def tier_sort_key(tier: str):
    """Return a sort key so tiers order as A,B,C,L,X then others alphabetically."""
    order = {'a': 0, 'b': 1, 'c': 2, 'l': 3, 'x': 4}
    t = (tier or '').strip().lower()
    if not t:
        return (99, '')
    # Prefer explicit first-letter mapping
    first = t[0]
    if first in order:
        return (order[first], t)
    # handle 'liiga' appearance
    if 'liiga' in t:
        return (order['l'], t)
    return (50, t)


def is_allowed_pdga_group(key: str) -> bool:
    """Return True if this group key represents an allowed PDGA tier (A,B,C,L,X)."""
    if not key:
        return False
    k = key.strip().lower()
    # If the key is an explicit kind (weekly/pair), it's not PDGA
    if k in ('parikisa', 'parikilpailu', 'viikkokisa', 'viikkokisat', 'viikkokisa', 'viikkari', 'viikkot'):
        return False
    # Allow if the first character is one of the allowed PDGA tier letters
    first = k[0]
    return first in ('a', 'b', 'c', 'l', 'x')


def detect_weekly_kind(comps):
    """Mark competitions with 'kind' = 'VIIKKOKISA' or 'PARIKISA' when name/location match heuristics."""
    try:
        # 'liiga' is a tier label (L-tier), not a weekly indicator — exclude it here
        # broaden Finnish weekly synonyms and pair indicators; exclude 'liiga' (handled elsewhere)
        weekly_re = re.compile(r"\b(weekly|week|viikko|viikkari|viikotta|viikkokisa|viikkokisat|viikkot|weeklies)\b", re.I)
        pair_re = re.compile(r"\b(pari|parikisa|parikilpailu|parigolf|pariviikko|pariviikkokisat|pair|pairs|double|doubles|best shot|max2)\b", re.I)
        for comp in comps:
            try:
                name_low = (comp.get('name','') or '').lower()
                loc_low = (comp.get('location','') or '').lower()
                tier_low = (comp.get('tier','') or '').lower()
                # consider explicit competition-type / tier label (e.g. 'Weekly', 'double')
                # robust detection: regex OR simple substring checks to handle odd whitespace/characters
                pair_check = pair_re.search(name_low) or pair_re.search(loc_low) or pair_re.search(tier_low)
                pair_keywords = ['pari','parikisa','parikilpailu','parigolf','pariviikko','pariviikkokisat','pair','pairs','double','doubles','best shot','max2']
                pair_sub = any(k in name_low or k in loc_low or k in tier_low for k in pair_keywords)
                is_pair = bool(pair_check or pair_sub)
                # detect PDGA-tier / Liiga to avoid misclassifying league events as weeklies
                is_pdga_tier = 'pdga' in tier_low or tier_low.strip().startswith(('a','b','c','l','x'))
                is_liiga = 'liiga' in name_low or 'liiga' in tier_low
                # weekly if weekly term appears and not a PDGA-liiga event
                weekly_check = weekly_re.search(name_low) or weekly_re.search(loc_low) or weekly_re.search(tier_low)
                weekly_keywords = ['weekly','week','viikko','viikkari','viikotta','viikkokisa','viikkokisat','viikkot','weeklies','viikkari','viikkari']
                weekly_sub = any(k in name_low or k in loc_low or k in tier_low for k in weekly_keywords)
                is_weekly = bool((weekly_check or weekly_sub) and not (is_pdga_tier and is_liiga))
                if is_pair:
                    comp['kind'] = 'PARIKISA'
                elif is_weekly:
                    comp['kind'] = 'VIIKKOKISA'
            except Exception:
                continue
    except Exception:
        return


def date_display(date_str: str) -> str:
    """Return only the date part in DD/MM/YYYY (drop time) for nicer display."""
    if not date_str:
        return ""
    # take first token (before any whitespace) and normalize dots to slashes
    part = str(date_str).split()[0]
    return part.replace('.', '/')



async def fetch_competitions(url=None):
    # Use explicit built URL when none provided to avoid stale global defaults
    if url:
        target_url = url
    else:
        target_url = build_metrix_url(association_id=1, type_code=None, country_code='FI', date1='2026-01-01', date2='2027-01-01')
    headers = {"User-Agent": "Mozilla/5.0"}
    rows = []
    print(f"fetch_competitions: fetching {target_url}")
    # Return cached result if recent to avoid duplicate quick server requests
    now_ts = time.time()
    if _fetch_cache['data'] is not None and (now_ts - _fetch_cache['ts'] < _fetch_cache['ttl']):
        cached = _fetch_cache['data']
        print(f"fetch_competitions: returning cached {len(cached)} competitions (cached)")
        return _cache_and_return(cached)
    # Fast-path: if the query includes area/type/country filters, prefer the server endpoint immediately
    try:
        from urllib.parse import urlparse, parse_qs, quote
        parsed_quick = urlparse(target_url)
        qs_quick = parse_qs(parsed_quick.query)
        area_q = qs_quick.get('area', [''])[0] if qs_quick else ''
        type_q = qs_quick.get('type', [''])[0] if qs_quick else ''
        country_q = qs_quick.get('country_code', [''])[0] if qs_quick else ''
        date1_q = qs_quick.get('date1', ['2026-01-01'])[0]
        date2_q = qs_quick.get('date2', ['2027-01-01'])[0]
        try:
            if date1_q > date2_q:
                date1_q, date2_q = date2_q, date1_q
        except Exception:
            pass
        if area_q or type_q or country_q:
            try:
                area_part = f"&area={quote(area_q)}" if area_q else ""
                type_part = f"&type={type_q}" if type_q else ""
                country_part = f"&country_code={country_q}" if country_q else ""
                server_url_quick = f"https://discgolfmetrix.com/competitions_server.php?name=&date1={date1_q}&date2={date2_q}&registration_date1=&registration_date2={country_part}{area_part}{type_part}&from=1&to=200&page=all"
                resp_quick = await asyncio.to_thread(requests.get, server_url_quick, headers=headers, timeout=20)
                if hasattr(resp_quick, 'content'):
                    soup_q = BeautifulSoup(resp_quick.content, 'html.parser')
                    cont_q = soup_q.find(id='competition_list2')
                    if cont_q:
                        comps_q = []
                        # gridlist
                        for a in cont_q.select('a.gridlist'):
                            try:
                                href = a.get('href')
                                h2 = a.find('h2')
                                name = h2.get_text(strip=True) if h2 else a.get_text(strip=True)
                                span = a.select_one('.competition-type')
                                tier = span.get_text(strip=True) if span else ''
                                meta_items = a.select('.metadata-list li')
                                date_raw = meta_items[0].get_text(strip=True) if len(meta_items) > 0 else ''
                                location_raw = meta_items[1].get_text(strip=True) if len(meta_items) > 1 else ''
                                date_str = parse_metrix_date(date_raw)
                                comp_id = href.strip('/').split('/')[-1] if href else name
                                comps_q.append({
                                    'id': comp_id,
                                    'name': name,
                                    'tier': tier,
                                    'url': f"https://discgolfmetrix.com{href}",
                                    'date': date_str,
                                    'location': location_raw
                                })
                            except Exception:
                                continue
                        # table rows
                        for tr in cont_q.select('table.table-list tbody tr'):
                            try:
                                cols = tr.find_all('td')
                                if not cols:
                                    continue
                                link = cols[0].find('a')
                                url = link['href'] if link else ''
                                name = link.get_text(strip=True) if link else cols[0].get_text(strip=True)
                                tier = cols[2].get_text(strip=True) if len(cols) > 2 else ''
                                date_raw = cols[1].get_text(strip=True) if len(cols) > 1 else ''
                                location_raw = cols[3].get_text(strip=True) if len(cols) > 3 else ''
                                date_str = parse_metrix_date(date_raw)
                                comp_id = url.strip('/').split('/')[-1] if url else name
                                comps_q.append({
                                    'id': comp_id,
                                    'name': name,
                                    'tier': tier,
                                    'url': f"https://discgolfmetrix.com{url}",
                                    'date': date_str,
                                    'location': location_raw
                                })
                            except Exception:
                                continue
                        if comps_q:
                            print(f"fetch_competitions: quick server endpoint returned {len(comps_q)} competitions")
                            return _cache_and_return(comps_q)
            except Exception:
                pass
    except Exception:
        pass
    # Quick path: if the URL contains a club/association id, call the server endpoint directly
    competitions = []
    try:
        from urllib.parse import urlparse, parse_qs
        parsed_qu = urlparse(target_url)
        qs_qu = parse_qs(parsed_qu.query)
        # prefer explicit club_id (client-facing param), fall back to association_id
        assoc = None
        if 'club_id' in qs_qu:
            assoc = qs_qu.get('club_id', [None])[0]
        if not assoc:
            assoc = qs_qu.get('clubid', [None])[0]
        if not assoc:
            assoc = qs_qu.get('association_id', [None])[0]
        clubtype = qs_qu.get('club_type', ['1'])[0]
        date1_q = qs_qu.get('date1', ['2026-01-01'])[0]
        date2_q = qs_qu.get('date2', ['2027-01-01'])[0]
        country_q = qs_qu.get('country_code', ['FI'])[0]
        type_q = qs_qu.get('type', [''])[0] or ''
        # ensure date ordering
        try:
            if date1_q > date2_q:
                date1_q, date2_q = date2_q, date1_q
        except Exception:
            pass
        if assoc and assoc != '0':
            type_param = f"&type={type_q}" if type_q else ""
            server_url = f"https://discgolfmetrix.com/competitions_server.php?name=&date1={date1_q}&date2={date2_q}&registration_date1=&registration_date2=&country_code={country_q}&clubid={assoc}&clubtype={clubtype}{type_param}&from=1&to=200&page=all"
            try:
                resp_srv = await asyncio.to_thread(requests.get, server_url, headers=headers, timeout=20)
                if hasattr(resp_srv, 'content'):
                    soup_srv = BeautifulSoup(resp_srv.content, 'html.parser')
                    cont = soup_srv.find(id='competition_list2')
                    if cont:
                        for a in cont.select('a.gridlist'):
                            try:
                                href = a.get('href')
                                h2 = a.find('h2')
                                name = h2.get_text(strip=True) if h2 else a.get_text(strip=True)
                                span = a.select_one('.competition-type')
                                tier = span.get_text(strip=True) if span else ''
                                meta_items = a.select('.metadata-list li')
                                date_raw = meta_items[0].get_text(strip=True) if len(meta_items) > 0 else ''
                                location_raw = meta_items[1].get_text(strip=True) if len(meta_items) > 1 else ''
                                date_str = parse_metrix_date(date_raw)
                                comp_id = href.strip('/').split('/')[-1] if href else name
                                competitions.append({
                                    'id': comp_id,
                                    'name': name,
                                    'tier': tier,
                                    'url': f"https://discgolfmetrix.com{href}",
                                    'date': date_str,
                                    'location': location_raw
                                })
                            except Exception:
                                continue
            except Exception:
                pass
            # Fast server endpoint fallback for area/type/country queries (do this early to speed up weekly searches)
            try:
                area_q_fast = qs_qu.get('area', [''])[0] if qs_qu else ''
                # If user requested a specific area or type or country, prefer server endpoint (very fast)
                if (area_q_fast or type_q or country_q) and not competitions:
                    from urllib.parse import quote
                    area_part = f"&area={quote(area_q_fast)}" if area_q_fast else ""
                    type_part = f"&type={type_q}" if type_q else ""
                    server_url_fast = f"https://discgolfmetrix.com/competitions_server.php?name=&date1={date1_q}&date2={date2_q}&registration_date1=&registration_date2=&country_code={country_q}{area_part}{type_part}&from=1&to=200&page=all"
                    try:
                        resp_fast = await asyncio.to_thread(requests.get, server_url_fast, headers=headers, timeout=20)
                        if hasattr(resp_fast, 'content'):
                            soup_fast = BeautifulSoup(resp_fast.content, 'html.parser')
                            cont = soup_fast.find(id='competition_list2')
                            if cont:
                                # parse gridlist
                                for a in cont.select('a.gridlist'):
                                    try:
                                        href = a.get('href')
                                        h2 = a.find('h2')
                                        name = h2.get_text(strip=True) if h2 else a.get_text(strip=True)
                                        span = a.select_one('.competition-type')
                                        tier = span.get_text(strip=True) if span else ''
                                        meta_items = a.select('.metadata-list li')
                                        date_raw = meta_items[0].get_text(strip=True) if len(meta_items) > 0 else ''
                                        location_raw = meta_items[1].get_text(strip=True) if len(meta_items) > 1 else ''
                                        date_str = parse_metrix_date(date_raw)
                                        comp_id = href.strip('/').split('/')[-1] if href else name
                                        competitions.append({
                                            'id': comp_id,
                                            'name': name,
                                            'tier': tier,
                                            'url': f"https://discgolfmetrix.com{href}",
                                            'date': date_str,
                                            'location': location_raw
                                        })
                                    except Exception:
                                        continue
                                # parse table rows if present
                                for tr in cont.select('table.table-list tbody tr'):
                                    try:
                                        cols = tr.find_all('td')
                                        if not cols:
                                            continue
                                        link = cols[0].find('a')
                                        url = link['href'] if link else ''
                                        name = link.get_text(strip=True) if link else cols[0].get_text(strip=True)
                                        tier = cols[2].get_text(strip=True) if len(cols) > 2 else ''
                                        date_raw = cols[1].get_text(strip=True) if len(cols) > 1 else ''
                                        location_raw = cols[3].get_text(strip=True) if len(cols) > 3 else ''
                                        date_str = parse_metrix_date(date_raw)
                                        comp_id = url.strip('/').split('/')[-1] if url else name
                                        competitions.append({
                                            'id': comp_id,
                                            'name': name,
                                            'tier': tier,
                                            'url': f"https://discgolfmetrix.com{url}",
                                            'date': date_str,
                                            'location': location_raw
                                        })
                                    except Exception:
                                        continue
                    except Exception:
                        pass
                    if competitions:
                        print(f"fetch_competitions: fast server endpoint returned {len(competitions)} competitions")
                        return _cache_and_return(competitions)
            except Exception:
                pass
        if competitions:
            print(f"fetch_competitions: server endpoint returned {len(competitions)} competitions")
            return _cache_and_return(competitions)
    except Exception:
        pass
    try:
        resp = await asyncio.to_thread(requests.get, target_url, headers=headers, timeout=15)
        if hasattr(resp, 'content'):
            soup = BeautifulSoup(resp.content, "html.parser")
            rows = soup.select("table.competitions-list tbody tr")
            print(f"fetch_competitions: initial request found {len(rows)} rows")
    except Exception:
        rows = []
    # second lightweight attempt (use same target_url) in case of intermittent failures
    rows = rows or []
    try:
        resp = await asyncio.to_thread(requests.get, target_url, headers=headers, timeout=10)
        if hasattr(resp, 'content'):
            soup = BeautifulSoup(resp.content, "html.parser")
            rows = soup.select("table.competitions-list tbody tr")
            print(f"fetch_competitions: second request found {len(rows)} rows")
    except Exception:
        rows = rows or []

    competitions = []
    if not rows:
        # Try an async Playwright fallback to render JS-heavy content
        try:
            from playwright.async_api import async_playwright
            # XPath to container provided by user
            XPATH_CONTAINER = '/html/body/div[2]/div/div[4]/div[1]/div/div[2]'
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()
                # capture JSON/XHR responses for debugging and API discovery
                captured = []
                async def _on_response(response):
                    try:
                        urlr = response.url
                        hdr = response.headers.get('content-type','')
                        if 'application/json' in hdr or urlr.find('ajax')!=-1 or urlr.find('json')!=-1 or urlr.find('competit')!=-1:
                            try:
                                txt = await response.text()
                                snippet = txt[:2000]
                                print(f"[network] {urlr} -> {snippet[:500]!s}")
                                captured.append((urlr, snippet))
                            except Exception:
                                pass
                    except Exception:
                        pass
                page.on('response', _on_response)
                await page.goto(target_url, timeout=30000)
                await page.wait_for_timeout(2000)
                # Try to select the club/association dropdown value for SFL
                try:
                    CLUB_NAME = "Suomen Frisbeegolfliitto"
                    # click the club dropdown if present
                    if await page.query_selector('#id_filter_club'):
                        try:
                            await page.click('#id_filter_club')
                            # wait for dropdown options to render and click the matching text
                            await page.wait_for_timeout(500)
                            locator = page.locator(f"text={CLUB_NAME}")
                            if await locator.count() > 0:
                                await locator.first.click()
                                await page.wait_for_timeout(1000)
                        except Exception:
                            pass
                except Exception:
                    pass
                html = await page.content()
                soup2 = BeautifulSoup(html, "html.parser")
                rows = soup2.select("table.competitions-list tbody tr")
                print(f"fetch_competitions: playwright snapshot found {len(rows)} rows")
                # If table rows still empty, try container XPath and interact with filter links
                if not rows:
                    try:
                        container = page.locator(f"xpath={XPATH_CONTAINER}")
                        container_html = await container.inner_html()
                        if container_html:
                            sect = BeautifulSoup(container_html, "html.parser")
                            links = sect.find_all('a', href=True)
                            # collect candidate filter hrefs (those with 'filter=' or competitions_all)
                            candidate_hrefs = []
                            for a in links:
                                href = a.get('href')
                                if not href:
                                    continue
                                if 'filter=' in href or 'competitions_all' in href:
                                    candidate_hrefs.append(href)
                            # try each filter link until we find competition rows
                            seen_ids = set()
                            for href in candidate_hrefs:
                                try:
                                    full = href if href.startswith('http') else f"https://discgolfmetrix.com{href}"
                                    await page.goto(full, timeout=30000)
                                    try:
                                        await page.wait_for_selector('table.competitions-list tbody tr', timeout=7000)
                                    except Exception:
                                        pass
                                    html3 = await page.content()
                                    soup3 = BeautifulSoup(html3, "html.parser")
                                    rows2 = soup3.select('table.competitions-list tbody tr')
                                    for row in rows2:
                                        cols = row.find_all('td')
                                        if len(cols) >= 3:
                                            link = cols[0].find('a')
                                            url = link['href'] if link else ''
                                            name = link.text.strip() if link else ''
                                            tier = cols[1].text.strip()
                                            date_str_raw = cols[2].text.strip()
                                            date_str = parse_metrix_date(date_str_raw)
                                            comp_id = url.split('=')[-1] if url else name
                                            if comp_id in seen_ids:
                                                continue
                                            seen_ids.add(comp_id)
                                            competitions.append({
                                                'id': comp_id,
                                                'name': name,
                                                'tier': tier,
                                                'url': f"https://discgolfmetrix.com{url}",
                                                'date': date_str
                                            })
                                    if competitions:
                                        break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                await browser.close()
        except Exception as e:
            print(f"Playwright fallback failed: {e}")
            rows = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 3:
            link = cols[0].find("a")
            url = link["href"] if link else ""
            name = link.text.strip() if link else ""
            tier = cols[1].text.strip()
            date_str_raw = cols[2].text.strip()
            date_str = parse_metrix_date(date_str_raw)
            comp_id = url.split('=')[-1] if url else name
            competitions.append({
                "id": comp_id,
                "name": name,
                "tier": tier,
                "url": f"https://discgolfmetrix.com{url}",
                "date": date_str
            })
    # If no competitions found yet, try direct competitions_server.php endpoint (faster)
    if not competitions:
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(target_url)
            qs = parse_qs(parsed.query)
            date1 = qs.get('date1', ['2026-01-01'])[0]
            date2 = qs.get('date2', ['2027-01-01'])[0]
            # ensure date ordering: server expects date1 <= date2
            try:
                if date1 > date2:
                    date1, date2 = date2, date1
            except Exception:
                pass
            assoc = qs.get('association_id', [None])[0]
            # determine optional type param (allow empty -> all competitions)
            type_q = qs.get('type', [''])[0] or ''
            type_param = f"&type={type_q}" if type_q else ""
            # If association provided, prefer club-based server endpoint
            if assoc and assoc != '0':
                server_url = f"https://discgolfmetrix.com/competitions_server.php?name=&date1={date1}&date2={date2}&registration_date1=&registration_date2=&country_code=FI&clubid={assoc}&clubtype=1{type_param}&from=1&to=200&page=all"
            else:
                # Fallback: use area/country/type filters if no specific club/association
                area_q = qs.get('area', [''])[0] if qs else ''
                country_q2 = qs.get('country_code', ['FI'])[0] if qs else 'FI'
                area_part = f"&area={area_q}" if area_q else ""
                type_part = f"&type={type_q}" if type_q else ""
                server_url = f"https://discgolfmetrix.com/competitions_server.php?name=&date1={date1}&date2={date2}&registration_date1=&registration_date2=&country_code={country_q2}{area_part}{type_part}&from=1&to=200&page=all"
            try:
                resp = await asyncio.to_thread(requests.get, server_url, headers=headers, timeout=20)
                if hasattr(resp, 'content'):
                    soup_srv = BeautifulSoup(resp.content, 'html.parser')
                    cont = soup_srv.find(id='competition_list2')
                    if cont:
                        for a in cont.select('a.gridlist'):
                            try:
                                href = a.get('href')
                                h2 = a.find('h2')
                                name = h2.get_text(strip=True) if h2 else a.get_text(strip=True)
                                span = a.select_one('.competition-type')
                                tier = span.get_text(strip=True) if span else ''
                                # date and location in metadata-list li
                                meta_items = a.select('.metadata-list li')
                                date_raw = meta_items[0].get_text(strip=True) if len(meta_items) > 0 else ''
                                location_raw = meta_items[1].get_text(strip=True) if len(meta_items) > 1 else ''
                                date_str = parse_metrix_date(date_raw)
                                comp_id = href.strip('/').split('/')[-1] if href else name
                                competitions.append({
                                    'id': comp_id,
                                    'name': name,
                                    'tier': tier,
                                    'url': f"https://discgolfmetrix.com{href}",
                                    'date': date_str,
                                    'location': location_raw
                                })
                            except Exception:
                                continue
            except Exception:
                pass
        except Exception:
            pass

    # Deduplicate competitions by id while preserving order
    try:
        seen_ids = set()
        unique = []
        for c in competitions:
            cid = c.get('id')
            if not cid:
                # keep entries without id as they are
                unique.append(c)
                continue
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            unique.append(c)
        competitions = unique
        # Best-effort sort by date string (format varies), stable if parsing fails
        try:
            competitions.sort(key=lambda x: x.get('date', ''))
        except Exception:
            pass
    except Exception:
        pass

    print(f"fetch_competitions: returning {len(competitions)} competitions")
    # Single-rule classification by `type` / `pdga`:
    # - If PDGA is present (query hint or tier contains 'pdga') => mark as PDGA (goes to PDGA.json)
    # - Else if query `type=C` => mark as VIIKKOKISA
    # - Else if query `type=D` => mark as PARIKISA
    # - Otherwise, fallback to weekly/pair heuristics
    try:
        from urllib.parse import urlparse, parse_qs
        parsed_hint = urlparse(target_url)
        qs_hint = parse_qs(parsed_hint.query)
        type_hint = (qs_hint.get('type', [''])[0] or '').strip().upper()
        pdga_hint = (qs_hint.get('pdga', [''])[0] or '').strip().lower()
    except Exception:
        type_hint = ''
        pdga_hint = ''

    for c in competitions:
        try:
            tier_low = (c.get('tier','') or '').lower()
            # Rule: PDGA wins — if query indicates PDGA or tier contains 'pdga', mark PDGA
            if pdga_hint in ('1', 'true', 'yes') or 'pdga' in tier_low:
                c['pdga'] = True
                # ensure non-weekly kind doesn't override PDGA
                continue

            # If the query explicitly requested PDGA competitions via type=pdga, mark as PDGA
            if type_hint == 'PDGA':
                c['pdga'] = True
                continue

            # Apply explicit type hints
            if type_hint == 'C':
                c['kind'] = 'VIIKKOKISA'
                c['pdga'] = False
                continue
            if type_hint == 'D':
                c['kind'] = 'PARIKISA'
                c['pdga'] = False
                continue

            # Fallback: run heuristics to detect weekly/pair if no explicit type/pdga
            try:
                detect_weekly_kind([c])
                if c.get('kind') in ('PARIKISA', 'VIIKKOKISA'):
                    c['pdga'] = False
            except Exception:
                pass
        except Exception:
            continue

    # Final override: if a competition page explicitly mentions PDGA, mark it PDGA (overrides type hints)
    for c in competitions:
        try:
            if not c.get('pdga') and c.get('url'):
                if is_competition_page_pdga(c.get('url')):
                    c['pdga'] = True
        except Exception:
            continue

    return _cache_and_return(competitions)


async def periodic_post_list():
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    while True:
        try:
            url = build_metrix_url(association_id=1, type_code=None, country_code='FI', date1='2026-01-01', date2='2027-01-01')
            comps = await fetch_competitions(url=url)
            if comps:
                # Tag weeklies/pairs then group competitions by kind (if present) or tier
                detect_weekly_kind(comps)
                from collections import defaultdict
                grouped = defaultdict(list)
                for c in comps:
                    key = (c.get('kind') or c.get('tier','')).strip()
                    grouped[key].append(c)
                title = "PDGA kisat (SFL, 2026)"
                # Send one embed per tier (do not mix tiers across messages)
                # If a single tier is too large, split that tier across multiple embeds
                tiers_sorted = sorted(grouped.keys(), key=tier_sort_key)
                for tier in tiers_sorted:
                    # Only post PDGA-thread groups for allowed PDGA tiers
                    if not is_allowed_pdga_group(tier):
                        continue
                    items = grouped[tier]
                    if tier and 'liiga' in tier.lower():
                        heading = f"LIIGA — {tier}"
                    else:
                        heading = tier if tier else 'Muut'
                    tier_lines = [f"**{heading}**"]
                    for c in items[:200]:
                        name = c.get('name','')
                        date = c.get('date','')
                        urlc = c.get('url','')
                        tier_lines.append(f"• [{name}]({urlc})")
                    # send this tier in one or more embeds
                    chunk = []
                    cur_len = 0
                    for line in tier_lines:
                        if cur_len + len(line) + 1 > 1900:
                            embed = discord.Embed(title=title, description="\n".join(chunk), color=0xFFA500)
                            if channel:
                                await channel.send(embed=embed)
                            chunk = [line]
                            cur_len = len(line) + 1
                        else:
                            chunk.append(line)
                            cur_len += len(line) + 1
                    if chunk:
                        embed = discord.Embed(title=title, description="\n".join(chunk), color=0xFFA500)
                        if channel:
                            await channel.send(embed=embed)
        except Exception as e:
            print(f"periodic_post_list error: {e}")
        await asyncio.sleep(AUTO_LIST_INTERVAL)

def load_json(filepath):
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            # handle empty files or invalid JSON by returning empty list
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    except Exception:
        return []

def save_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_registration_time(comp_url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(comp_url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.content, "html.parser")
        reg_info = soup.find("div", class_="competition-registration")
        if reg_info:
            for strong in reg_info.find_all("strong"):
                if "Ilmoittautuminen alkaa" in strong.text or "Registration opens" in strong.text:
                    next_sib = strong.next_sibling
                    if next_sib:
                        reg_text = next_sib.strip()
                        try:
                            dt = datetime.strptime(reg_text, "%d.%m.%Y %H:%M:%S")
                            return dt
                        except ValueError:
                            pass
    except Exception as e:
        print(f"Registration scraping failed: {e}")
    return None

async def check_new_competitions():
    await client.wait_until_ready()
    # Prefer the designated thread for new-competition notifications
    channel = client.get_channel(DISCORD_THREAD_ID) or client.get_channel(DISCORD_CHANNEL_ID)
    known = load_json(CACHE_FILE)
    pending_registrations = load_json(REG_CHECK_FILE)
    weekly_known = load_json(WEEKLY_JSON)
    while True:
        competitions = await fetch_competitions()
        known_ids = {c["id"] for c in known}
        new_comps = [c for c in competitions if c["id"] not in known_ids]
        # If there are new competitions, group them by tier and send one markdown list per tier
        if new_comps:
            # Each embed will carry the top-level announcement title instead of a separate plain message

            # Tag weeklies/pairs so new-competition posting will include them as their own group
            detect_weekly_kind(competitions)
            from collections import defaultdict
            grouped = defaultdict(list)
            # track existing pending ids to avoid duplicates
            existing_pending_ids = {p.get('id') for p in pending_registrations}
            now = datetime.now()
            for comp in new_comps:
                key = (comp.get('kind') or comp.get('tier','')).strip()
                grouped[key].append(comp)
                reg_dt = fetch_registration_time(comp["url"])
                if reg_dt and reg_dt > now:
                    # add to pending registrations if not already present
                    if comp["id"] not in existing_pending_ids:
                        pending_registrations.append({
                            "id": comp["id"],
                            "name": comp["name"],
                            "url": comp["url"],
                            "reg_time": reg_dt.isoformat()
                        })
                        existing_pending_ids.add(comp["id"])
                    # if registration opens within 7 days, notify immediately
                    days_until = (reg_dt - now).days
                    if 0 < days_until <= 7:
                        # short tier label (C-PDGA / L-PDGA)
                        t = (comp.get('tier','') or '').strip()
                        if t.lower().startswith('c'):
                            tier_short = 'C-PDGA'
                        elif t.lower().startswith('l') or 'liiga' in t.lower():
                            tier_short = 'L-PDGA'
                        else:
                            tier_short = t or 'Kisa'
                        when = reg_dt.strftime("%d.%m.%Y")
                        if channel:
                            await channel.send(f"{tier_short}: Rekisteröityminen alkamassa {when}")

                # Weekly / Pair detection: heuristic on competition name; filter by WEEKLY_LOCATION if configured
                try:
                    name_low = (comp.get('name','') or '').lower()
                    loc_low = (comp.get('location','') or '').lower()
                    weekly_re = re.compile(r"\b(weekly|week|viikko|viikotta|viikkokisa|viikkokisat|weeklies)\b", re.I)
                    pair_re = re.compile(r"\b(pari|parikisa|parikilpailu|pair|pairs)\b", re.I)
                    is_weekly = bool(weekly_re.search(name_low))
                    is_pair = bool(pair_re.search(name_low))
                    kind = None
                    if is_pair:
                        kind = 'PARIKISA'
                    elif is_weekly:
                        kind = 'VIIKKOKISA'
                    if kind:
                        # check area filter: if WEEKLY_LOCATION set, require it to appear in location or name
                        in_area = True
                        if WEEKLY_LOCATION:
                            in_area = (WEEKLY_LOCATION in loc_low) or (WEEKLY_LOCATION in name_low)
                        if in_area:
                            existing_weekly_ids = {p.get('id') for p in weekly_known}
                            if comp['id'] not in existing_weekly_ids:
                                weekly_known.append({
                                    'id': comp['id'],
                                    'name': comp['name'],
                                    'url': comp['url'],
                                    'location': comp.get('location',''),
                                    'kind': kind
                                })
                                save_json(weekly_known, WEEKLY_JSON)
                                # collect for batch notify later
                                if 'to_notify_weekly' not in locals():
                                    to_notify_weekly = []
                                to_notify_weekly.append(comp)
                except Exception:
                    pass
                # end for new comps loop
            # send batch weekly notifications (embed list) if any
            try:
                weekly_thread = client.get_channel(DISCORD_WEEKLY_THREAD_ID)
                if 'to_notify_weekly' in locals() and to_notify_weekly and weekly_thread:
                    # build lines
                    lines = []
                    for c in to_notify_weekly:
                        loc = c.get('location','')
                        lines.append(f"- [{c.get('name')}]({c.get('url')}) {loc}")
                    # chunk into embeds of ~1800 chars
                    chunk = []
                    cur = 0
                    for line in lines:
                        if cur + len(line) + 1 > 1800:
                            embed = discord.Embed(title="Uusia VIIKKOKISA kisoja lisätty", description="\n".join(chunk), color=0x00BFFF)
                            await weekly_thread.send(embed=embed)
                            chunk = [line]
                            cur = len(line) + 1
                        else:
                            chunk.append(line)
                            cur += len(line) + 1
                    if chunk:
                        embed = discord.Embed(title="Uusia VIIKKOKISA kisoja lisätty", description="\n".join(chunk), color=0x00BFFF)
                        await weekly_thread.send(embed=embed)
            except Exception:
                pass

            # Send one embed per tier (title = tier heading) in preferred order
            tiers_sorted = sorted(grouped.keys(), key=tier_sort_key)
            for tier in tiers_sorted:
                # Only post PDGA-thread groups for allowed PDGA tiers
                if not is_allowed_pdga_group(tier):
                    continue
                comps = grouped[tier]
                title_tier = (tier or '').strip()
                if title_tier.lower().startswith('c'):
                    heading = "C - PDGA"
                elif title_tier.lower().startswith('l') or 'l-pdga' in title_tier.lower():
                    heading = f"LIIGA — {title_tier}"
                else:
                    heading = title_tier if title_tier else "Muut"

                # build lines for this tier
                body_lines = []
                for c in comps:
                    name = c.get('name','')
                    url = c.get('url','')
                    date = c.get('date','')
                    body_lines.append(f"- [{name}]({url})")

                if channel:
                    # Determine short tier label for title
                    tt = (title_tier or '').strip()
                    if tt.lower().startswith('c'):
                        tier_short = 'C-PDGA'
                    elif tt.lower().startswith('l') or 'liiga' in tt.lower():
                        tier_short = 'L-PDGA'
                    else:
                        tier_short = tt or 'Kisa'
                    embed_title = f"Uusia {tier_short} kisoja lisätty"
                    embed = discord.Embed(title=embed_title, description="\n".join(body_lines), color=0xFFD700)
                    await channel.send(embed=embed)
        if new_comps:
            known.extend(new_comps)
            save_json(known, CACHE_FILE)
            save_json(pending_registrations, REG_CHECK_FILE)
        await asyncio.sleep(CHECK_INTERVAL)


async def weekly_area_check():
    """Fetch competitions using WEEKLY_SEARCH_URL and notify weekly thread of new items."""
    await client.wait_until_ready()
    weekly_thread = client.get_channel(DISCORD_WEEKLY_THREAD_ID) or client.get_channel(DISCORD_CHANNEL_ID)
    weekly_known = load_json(WEEKLY_JSON)
    while True:
        try:
            if not WEEKLY_SEARCH_URL:
                await asyncio.sleep(24*3600)
                continue
            comps = await fetch_competitions(url=WEEKLY_SEARCH_URL)
            if not comps:
                await asyncio.sleep(6*3600)
                continue
            known_ids = {c.get('id') for c in weekly_known}
            new_weeklies = [c for c in comps if c.get('id') not in known_ids]
            # append all new weeklies and prepare a single embed list message
            to_notify = []
            for comp in new_weeklies:
                weekly_known.append({'id': comp.get('id'), 'name': comp.get('name'), 'url': comp.get('url'), 'location': comp.get('location','')})
                to_notify.append(comp)
            if new_weeklies:
                save_json(weekly_known, WEEKLY_JSON)
                if weekly_thread and to_notify:
                    try:
                        lines = [f"- [{c.get('name')}]({c.get('url')}) {c.get('location','')}" for c in to_notify]
                        # chunk into embeds
                        chunk = []
                        cur = 0
                        for line in lines:
                            if cur + len(line) + 1 > 1800:
                                embed = discord.Embed(title="Uusia viikkokisoja alueella", description="\n".join(chunk), color=0x00BFFF)
                                await weekly_thread.send(embed=embed)
                                chunk = [line]
                                cur = len(line) + 1
                            else:
                                chunk.append(line)
                                cur += len(line) + 1
                        if chunk:
                            embed = discord.Embed(title="Uusia viikkokisoja alueella", description="\n".join(chunk), color=0x00BFFF)
                            await weekly_thread.send(embed=embed)
                    except Exception:
                        pass
        except Exception as e:
            print(f"weekly_area_check error: {e}")
        await asyncio.sleep(24*3600)

async def check_registration_open():
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    while True:
        pending = load_json(REG_CHECK_FILE)
        now = datetime.now()
        notify = []
        still_pending = []
        for reg in pending:
            reg_dt = datetime.fromisoformat(reg["reg_time"])
            if now >= reg_dt:
                notify.append(reg)
            else:
                still_pending.append(reg)
        for reg in notify:
            if channel:
                await channel.send(f"**{reg['name']}** kilpailun ilmoittautuminen on avautunut! {reg['url']}")
        if len(still_pending) != len(pending):
            save_json(still_pending, REG_CHECK_FILE)
        await asyncio.sleep(CHECK_REGISTRATION_INTERVAL)

@client.event
async def on_ready():
    print(f"Bot kirjautui sisään {client.user}")
    print(f"Starting background tasks: check_new_competitions, check_registration_open, periodic_post_list")
    client.loop.create_task(check_new_competitions())
    client.loop.create_task(check_registration_open())
    client.loop.create_task(periodic_post_list())
    client.loop.create_task(weekly_area_check())

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content == "!ping":
        await message.channel.send("Pong!")
    # Listen for !testi in the designated thread/channel and print there
    if message.content.strip().lower() == "!testi":
        try:
            THREAD_ID = 1241493648080764988
            if message.channel.id == THREAD_ID:
                await message.channel.send("Haetaan kilpailut, hetki...")
                url = build_metrix_url(association_id=1, type_code=None, country_code='FI', date1='2026-01-01', date2='2027-01-01', view=1)
                try:
                    comps = await fetch_competitions(url=url)
                except Exception as e:
                    await message.channel.send(f"Haku epäonnistui: {e}")
                    return
                if not comps:
                    await message.channel.send("Ei löytynyt kilpailuja annetulla haulla.")
                    return
                # Tag weeklies/pairs then group competitions by kind (if present) or tier
                detect_weekly_kind(comps)
                from collections import defaultdict
                grouped = defaultdict(list)
                for c in comps:
                    key = (c.get('kind') or c.get('tier','')).strip()
                    grouped[key].append(c)
                title = "PDGA kisat (SFL, 2026)"
                # Build sections
                sections = []
                tiers_sorted = sorted(grouped.keys(), key=tier_sort_key)
                for tier in tiers_sorted:
                    # Only post PDGA-thread groups for allowed PDGA tiers
                    if not is_allowed_pdga_group(tier):
                        continue
                    items = grouped[tier]
                    if tier and 'liiga' in tier.lower():
                        heading = f"LIIGA — {tier}"
                    else:
                        heading = tier if tier else 'Muut'
                    sections.append(f"**{heading}**")
                    for c in items:
                        name = c.get('name','')
                        urlc = c.get('url','')
                        sections.append(f"- [{name}]({urlc})")
                    sections.append("")

                # Send a single top-level title message once (announce new competitions)
                title_msg = discord.Embed(title="UUSIA KILPAILUJA LISÄTTY", color=0xFFA500)
                await message.channel.send(embed=title_msg)
                # Then send each tier as its own message (title = tier heading)
                for tier in tiers_sorted:
                    # Only post PDGA-thread groups for allowed PDGA tiers
                    if not is_allowed_pdga_group(tier):
                        continue
                    items = grouped[tier]
                    if tier and 'liiga' in tier.lower():
                        heading = f"LIIGA — {tier}"
                    else:
                        heading = tier if tier else 'Muut'
                    # build list lines for this tier; prefix with the tier heading
                    tier_lines = []
                    for c in items:
                        name = c.get('name','')
                        date = c.get('date','')
                        urlc = c.get('url','')
                        tier_lines.append(f"- [{name}]({urlc})")
                    tier_lines.insert(0, f"**{heading}**")

                    # send this tier in one or more embeds; each embed uses the announcement title
                    chunk = []
                    cur_len = 0
                    for line in tier_lines:
                        if cur_len + len(line) + 1 > 1900:
                            embed = discord.Embed(title="UUSIA KILPAILUJA LISÄTTY", description="\n".join(chunk), color=0xFFA500)
                            await message.channel.send(embed=embed)
                            chunk = [line]
                            cur_len = len(line) + 1
                        else:
                            chunk.append(line)
                            cur_len += len(line) + 1
                    if chunk:
                        embed = discord.Embed(title="UUSIA KILPAILUJA LISÄTTY", description="\n".join(chunk), color=0xFFA500)
                        await message.channel.send(embed=embed)
                # Also run weekly/pair detection for these fetched competitions and notify weekly thread
                try:
                    weekly_known = load_json(WEEKLY_JSON)
                    existing_weekly_ids = {p.get('id') for p in weekly_known}
                    weekly_thread = client.get_channel(DISCORD_WEEKLY_THREAD_ID)
                    for comp in comps:
                        try:
                            name_low = (comp.get('name','') or '').lower()
                            loc_low = (comp.get('location','') or '').lower()
                            weekly_re = re.compile(r"\b(weekly|week|viikko|viikkari|viikotta|viikkokisa|viikkokisat|viikkot|weeklies)\b", re.I)
                            pair_re = re.compile(r"\b(pari|parikisa|parikilpailu|parigolf|pair|pairs|double|doubles)\b", re.I)
                            is_weekly = bool(weekly_re.search(name_low) or weekly_re.search(loc_low))
                            is_pair = bool(pair_re.search(name_low) or pair_re.search(loc_low))
                            kind = None
                            if is_pair:
                                kind = 'PARIKISA'
                            elif is_weekly:
                                kind = 'VIIKKOKISA'
                            if not kind:
                                continue
                            in_area = True
                            if WEEKLY_LOCATION:
                                in_area = (WEEKLY_LOCATION in loc_low) or (WEEKLY_LOCATION in name_low)
                            if not in_area:
                                continue
                            if comp.get('id') in existing_weekly_ids:
                                continue
                            weekly_known.append({'id': comp.get('id'), 'name': comp.get('name'), 'url': comp.get('url'), 'location': comp.get('location',''), 'kind': kind})
                            save_json(weekly_known, WEEKLY_JSON)
                            # collect to batch notify
                            if 'testi_weekly_notify' not in locals():
                                testi_weekly_notify = []
                            testi_weekly_notify.append(comp)
                        except Exception:
                            continue
                    # send batched weekly notifications for !testi handler
                    try:
                        if 'testi_weekly_notify' in locals() and testi_weekly_notify:
                            weekly_thread = client.get_channel(DISCORD_WEEKLY_THREAD_ID)
                            if weekly_thread:
                                lines = [f"- [{c.get('name')}]({c.get('url')}) {c.get('location','')}" for c in testi_weekly_notify]
                                chunk = []
                                cur = 0
                                for line in lines:
                                    if cur + len(line) + 1 > 1800:
                                        embed = discord.Embed(title="Uusia VIIKKOKISA kisoja lisätty", description="\n".join(chunk), color=0x00BFFF)
                                        await weekly_thread.send(embed=embed)
                                        chunk = [line]
                                        cur = len(line) + 1
                                    else:
                                        chunk.append(line)
                                        cur += len(line) + 1
                                if chunk:
                                    embed = discord.Embed(title="Uusia VIIKKOKISA kisoja lisätty", description="\n".join(chunk), color=0x00BFFF)
                                    await weekly_thread.send(embed=embed)
                    except Exception:
                        pass
                except Exception:
                    pass
                return
        except Exception as e:
            print(f"!testi handler error: {e}")
    if message.content == "!clistaus":
        comps = await fetch_competitions()
        c_tiers = [c for c in comps if "C-Tier" in c.get("tier", "") or "C-tier" in c.get("tier", "")]
        if not c_tiers:
            await message.channel.send("Ei löytynyt yhtään C-tier PDGA-kisaa tällä hetkellä.")
        else:
            response = "**PDGA C-tier kisat:**\n"
            for c in c_tiers[:10]:
                tier = c.get('tier','')
                tier_part = f" ({tier})" if tier else ""
                response += f"[{c['name']}]({c['url']}){tier_part}\n"
            await message.channel.send(response)
    if message.content.startswith("!testprint"):
        parts = message.content.split()
        target_id = None
        if len(parts) > 1:
            try:
                target_id = int(parts[1])
            except ValueError:
                target_id = None
        if not target_id:
            target_id = 1241493648080764988
        target = client.get_channel(target_id)
        if target:
            await target.send("Test print from bot — tämä on testi.")
            await message.channel.send(f"Lähetetty testiviesti kanavalle <#{target_id}>")
        else:
            await message.channel.send(f"Kanavaa {target_id} ei löytynyt tai bottilla ei ole oikeuksia.")

async def run_dry_run():
    """Fetch competitions (SFL FI 2026), classify them and write output JSONs without posting to Discord."""
    print("Running dry-run: fetching competitions and saving JSON outputs...")
    url = build_metrix_url(association_id=1, type_code=None, country_code='FI', date1='2026-01-01', date2='2027-01-01', area='')
    comps = await fetch_competitions(url=url)
    if not comps:
        print("No competitions fetched.")
        return
    # detect weeklies/pairs
    try:
        detect_weekly_kind(comps)
    except Exception:
        pass

    pdga_list = []
    week_list = []
    doubles_list = []
    others = []
    for c in comps:
        if c.get('pdga'):
            pdga_list.append(c)
        elif c.get('kind') == 'PARIKISA':
            doubles_list.append(c)
        elif c.get('kind') == 'VIIKKOKISA':
            week_list.append(c)
        else:
            others.append(c)

    save_json(pdga_list, 'PDGA.json')
    save_json(week_list, 'VIIKKOKISA.json')
    save_json(doubles_list, 'DOUBLES.json')
    save_json(others, 'OTHER_COMPETITIONS.json')

    print(f"Dry-run complete: PDGA={len(pdga_list)}, VIIKKOKISA={len(week_list)}, PARIKISA={len(doubles_list)}, OTHER={len(others)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='metrixDiscordBot runner')
    parser.add_argument('--dry-run', action='store_true', help='Fetch and save JSONs without posting to Discord')
    args = parser.parse_args()
    # startup: nothing to export — run normal bot loop
    if args.dry_run:
        asyncio.run(run_dry_run())
    elif getattr(args, 'once', False):
        asyncio.run(run_once())
    else:
        # Normal bot run requires discord and token
        if not discord:
            raise RuntimeError('discord package not available; install discord.py or run with --dry-run')
        if not DISCORD_TOKEN:
            raise RuntimeError('DISCORD_TOKEN not set in environment')
        client.run(DISCORD_TOKEN)


async def run_once():
    """Fetch competitions once, detect new ones, update cache and pending registration file, then exit.
    Does not start background tasks or post to Discord.
    """
    print("Running one-shot fetch...")
    known = load_json(CACHE_FILE)
    pending_registrations = load_json(REG_CHECK_FILE)
    weekly_known = load_json(WEEKLY_JSON)

    url = build_metrix_url(association_id=1, type_code=None, country_code='FI', date1='2026-01-01', date2='2027-01-01')
    comps = await fetch_competitions(url=url)
    if not comps:
        print("No competitions fetched.")
        return

    detect_weekly_kind(comps)
    known_ids = {c.get('id') for c in known}
    new_comps = [c for c in comps if c.get('id') not in known_ids]
    if not new_comps:
        print("No new competitions.")
    else:
        print(f"Found {len(new_comps)} new competitions:")
        for c in new_comps:
            print(f" - {c.get('name')} ({c.get('url')})")
        # update caches
        known.extend(new_comps)
        save_json(known, CACHE_FILE)
        # check registration times and append pending registrations
        now = datetime.now()
        existing_pending_ids = {p.get('id') for p in pending_registrations}
        for comp in new_comps:
            try:
                reg_dt = fetch_registration_time(comp.get('url'))
                if reg_dt and reg_dt > now and comp.get('id') not in existing_pending_ids:
                    pending_registrations.append({
                        'id': comp.get('id'), 'name': comp.get('name'), 'url': comp.get('url'), 'reg_time': reg_dt.isoformat()
                    })
                    existing_pending_ids.add(comp.get('id'))
            except Exception:
                continue
        save_json(pending_registrations, REG_CHECK_FILE)
        # update weekly_known with new weeklies
        wk_ids = {p.get('id') for p in weekly_known}
        for comp in comps:
            if comp.get('kind') in ('PARIKISA', 'VIIKKOKISA') and comp.get('id') not in wk_ids:
                weekly_known.append({'id': comp.get('id'), 'name': comp.get('name'), 'url': comp.get('url'), 'location': comp.get('location',''), 'kind': comp.get('kind')})
        save_json(weekly_known, WEEKLY_JSON)
    print("One-shot fetch complete.")