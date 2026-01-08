#!/usr/bin/env python3
"""Fetch Metrix URL 3523711, save HTML and print table/thead/tbody/tr counts and first table header."""
import os
import sys
import requests
from bs4 import BeautifulSoup as BS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__) or "", ".."))
OUT_DIR = os.path.join(ROOT, "scripts", "html_debug")
os.makedirs(OUT_DIR, exist_ok=True)
URL = "https://discgolfmetrix.com/3523711&view=result"

def main():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MetrixDebug/1.0)"}
    print("Fetching:", URL)
    r = requests.get(URL, headers=headers, timeout=25)
    print("Status:", r.status_code)
    if r.status_code != 200:
        print("Failed to fetch page")
        return
    html = r.text
    path = os.path.join(OUT_DIR, "3523711.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved HTML to:", path)

    soup = BS(html, "html.parser")
    tables = soup.find_all("table")
    print("Tables found:", len(tables))
    for i, t in enumerate(tables[:5], start=1):
        theads = t.find_all("thead")
        tbodys = t.find_all("tbody")
        trs = t.find_all("tr")
        print(f" Table {i}: theads={len(theads)} tbodys={len(tbodys)} trs={len(trs)}")
        # print first thead text if present
        if theads:
            th_texts = [th.get_text(" ", strip=True) for th in theads[0].find_all("th")]
            print("  first thead ths:", th_texts[:5])
        # print first 3 tr texts
        for j, tr in enumerate(trs[:3], start=1):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th","td"])][:8]
            print(f"  tr{j}:", cells)

if __name__ == '__main__':
    main()
