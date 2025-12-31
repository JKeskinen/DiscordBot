import requests
from bs4 import BeautifulSoup as BS
import re
import urllib.parse
import os
import time
import json
import argparse

# Default SFL "Kaikki kilpailut" URL (user-provided)
DEFAULT_URL = (
    "https://discgolfmetrix.com/?u=competitions_all&view=1&competition_name=&period="
    "&date1=2026-01-01&date2=2027-01-01&my_country=&registration_open=&registration_date1="
    "&registration_date2=&country_code=FI&my_club=&club_type=1&club_id=1&association_id=0"
    "&close_to_me=&area=&city=&course_id=&type=&division=&my=&view=1&sort_name=date&sort_order=asc&my_all=&from=1&to=200"
)


def fetch_competitions(url: str):
    headers = {"User-Agent": "Mozilla/5.0 (pdga-finder)"}
    try:
        start = time.perf_counter()
        r = requests.get(url, timeout=20, headers=headers)
        r.raise_for_status()
        elapsed = time.perf_counter() - start
        print(f"Fetched {url} in {elapsed:.2f}s, status={r.status_code}")
    except Exception as e:
        print(f"Fetch failed: {e}")
        return []

    r.encoding = r.apparent_encoding
    soup = BS(r.text, "html.parser")
    container = soup.find(id="competition_list2") or soup

    results = []
    # gridlist
    for a in container.select("a.gridlist"):
        href = a.get("href", "")
        comp_id = None
        m = re.search(r"/(\d+)", href)
        if m:
            comp_id = m.group(1)
        title = a.find("h2").get_text(strip=True) if a.find("h2") else a.get_text(strip=True)
        tspan = a.select_one(".competition-type")
        tier = tspan.get_text(strip=True) if tspan else ""
        meta = a.select(".metadata-list li")
        date = meta[0].get_text(strip=True) if len(meta) > 0 else ""
        location = meta[1].get_text(strip=True) if len(meta) > 1 else ""
        results.append({"id": comp_id, "name": title, "tier": tier, "date": date, "location": location, "url": _abs(href)})

    # table rows
    for tr in container.select("table.table-list tbody tr"):
        cols = tr.find_all("td")
        if not cols:
            continue
        link = cols[0].find("a")
        href = link["href"] if link else ""
        comp_id = None
        m = re.search(r"/(\d+)", href)
        if m:
            comp_id = m.group(1)
        name = link.get_text(strip=True) if link else cols[0].get_text(strip=True)
        date = cols[1].get_text(strip=True) if len(cols) > 1 else ""
        tier = cols[2].get_text(strip=True) if len(cols) > 2 else ""
        location = cols[3].get_text(strip=True) if len(cols) > 3 else ""
        results.append({"id": comp_id, "name": name, "tier": tier, "date": date, "location": location, "url": _abs(href)})

    # dedupe by id/title
    seen = set()
    unique = []
    for r in results:
        cid = r.get("id") or r.get("name")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        unique.append(r)
    # If nothing found on the page, try the fast server endpoint as a fallback
    if not unique:
        try:
            print("No entries found on page; trying competitions_server.php fallback...")
            # derive date1/date2 and clubid from provided URL if present
            from urllib.parse import urlparse, parse_qs, urlencode
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            date1 = qs.get('date1', ['2026-01-01'])[0]
            date2 = qs.get('date2', ['2027-01-01'])[0]
            clubid = qs.get('club_id', qs.get('clubid', qs.get('club_id', ['1'])))[0] if qs else '1'
            # build server endpoint URL
            server_url = (
                f"https://discgolfmetrix.com/competitions_server.php?name=&date1={date1}&date2={date2}"
                f"&registration_date1=&registration_date2=&country_code=FI&clubid={clubid}&clubtype=1&from=1&to=500&page=all"
            )
            start = time.perf_counter()
            r2 = requests.get(server_url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (pdga-finder)"})
            r2.raise_for_status()
            elapsed = time.perf_counter() - start
            print(f"Server endpoint fetch time: {elapsed:.2f}s, status={r2.status_code}")
            r2.encoding = r2.apparent_encoding
            soup2 = BS(r2.text, 'html.parser')
            cont2 = soup2.find(id='competition_list2') or soup2
            results2 = []
            for a in cont2.select('a.gridlist'):
                href = a.get('href','')
                m = re.search(r"/(\d+)", href)
                cid = m.group(1) if m else None
                title = a.find('h2').get_text(strip=True) if a.find('h2') else a.get_text(strip=True)
                tspan = a.select_one('.competition-type')
                tier = tspan.get_text(strip=True) if tspan else ''
                meta = a.select('.metadata-list li')
                date = meta[0].get_text(strip=True) if len(meta) > 0 else ''
                location = meta[1].get_text(strip=True) if len(meta) > 1 else ''
                results2.append({"id": cid, "name": title, "tier": tier, "date": date, "location": location, "url": _abs(href)})
            for tr in cont2.select('table.table-list tbody tr'):
                cols = tr.find_all('td')
                if not cols:
                    continue
                link = cols[0].find('a')
                href = link['href'] if link else ''
                m = re.search(r"/(\d+)", href)
                cid = m.group(1) if m else None
                name = link.get_text(strip=True) if link else cols[0].get_text(strip=True)
                date = cols[1].get_text(strip=True) if len(cols) > 1 else ''
                tier = cols[2].get_text(strip=True) if len(cols) > 2 else ''
                location = cols[3].get_text(strip=True) if len(cols) > 3 else ''
                results2.append({"id": cid, "name": name, "tier": tier, "date": date, "location": location, "url": _abs(href)})
            # dedupe
            seen2 = set()
            unique2 = []
            for r in results2:
                cid = r.get('id') or r.get('name')
                if not cid or cid in seen2:
                    continue
                seen2.add(cid)
                unique2.append(r)
            print(f"Server endpoint returned {len(unique2)} entries")
            return unique2
        except Exception as e:
            print(f"Server endpoint fallback failed: {e}")
    return unique


def _abs(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://discgolfmetrix.com{href}"
    return f"https://discgolfmetrix.com/{href}"


def is_pdga_entry(entry: dict) -> bool:
    """Decide if an entry is a PDGA competition.

    Heuristics:
    - tier text contains 'pdga'
    - or tier starts with A/B/C/L/X (case-insensitive)
    - or name contains 'pdga'
    """
    tier = (entry.get("tier") or "").lower()
    name = (entry.get("name") or "").lower()
    if "pdga" in tier or "pdga" in name:
        return True
    if tier.strip():
        first = tier.strip()[0]
        if first in ("a", "b", "c", "l", "x"):
            return True
    return False


def save_pdga_list(entries, out_path):
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(entries)} PDGA entries to {out_path}")
    except Exception as e:
        print(f"Failed to save PDGA JSON: {e}")


def main():
    parser = argparse.ArgumentParser(description="Search SFL (Kaikki kilpailut) and extract PDGA competitions")
    parser.add_argument("--url", default=DEFAULT_URL, help="SFL Kaikki kilpailut URL (default uses 2026 window)")
    parser.add_argument("--out", default=None, help="Output PDGA JSON path (default ../PDGA.json)")
    args = parser.parse_args()

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out = args.out or os.path.join(base_dir, "PDGA.json")

    comps = fetch_competitions(args.url)
    print(f"Parsed {len(comps)} competitions from SFL page")

    pdga = [c for c in comps if is_pdga_entry(c)]
    print(f"Detected {len(pdga)} PDGA competitions (heuristic)")

    save_pdga_list(pdga, out)


if __name__ == "__main__":
    main()
