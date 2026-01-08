#!/usr/bin/env python3
"""Simuloi !tulokset pohj -komennon tulostus paikallisesti.

Lataa viikkaritiedoston, kutsuu _fetch_competition_results ja _format_top3_lines_for_result
samanlailla kuin botti tekisi, ja tulostaa muodostetun viestin konsoliin.
"""
import asyncio
import json
import os
from komento_koodit import data_store
import sys

# Lisää projektin juurihakemisto polulle
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__) or "", ".."))
sys.path.insert(0, ROOT)

from komento_koodit import commands_tulokset as ct


def load_entries(filename: str):
    # Use sqlite-backed store (fallback to file)
    return data_store.load_category(filename)


async def main():
    # Lataa VIIKKARIT_SEUTU.json ja suodata Pohjanmaa-kisat
    try:
        entries = load_entries("VIIKKARIT_SEUTU.json")
    except Exception as e:
        print("ERROR: failed to load VIIKKARIT_SEUTU.json:", e)
        return

    # Suodata viikkokisat
    week_competitions = []
    for e in entries:
        kind = (e.get("kind") or "").upper()
        if "VIIKKOKISA" not in kind:
            continue
        area = (e.get("area") or "")
        if not area or "pohjanmaa" not in area.lower():
            continue
        week_competitions.append(e)

    if not week_competitions:
        print("No Pohjanmaa weekly competitions found in VIIKKARIT_SEUTU.json")
        return

    # Fetch results for each competition and format
    all_lines = []
    for e in week_competitions:
        raw = e.get("metrix") or e.get("url") or e.get("link") or e.get("id")
        url_base = ct._build_competition_url(raw)
        if not url_base:
            print("Skipped entry with no valid Metrix URL/ID:", raw)
            continue
        url = ct._ensure_results_url(url_base)
        print("Fetching:", url)
        loop = asyncio.get_running_loop()
        def do_fetch():
            return ct._fetch_competition_results(url)
        result = await loop.run_in_executor(None, do_fetch)
        if not result:
            print("Failed to fetch/parse:", url)
            continue
        # Debug print parsed structure
        print("Parsed event:", result.get("event_name"))
        classes = result.get("classes", [])
        print(f"  classes: {len(classes)}")
        for c in classes:
            print("   - class:", c.get("class_name"))
            rows = c.get("rows", [])
            print(f"     rows: {len(rows)}")
            for r in rows[:10]:
                print("      ", r.get("position"), r.get("name"), r.get("total"), r.get("to_par"), r.get("rating"))
        # Format using existing function and also fetch HC (handicap) top3
        hc_rows = ct._fetch_handicap_table(url)
        lines = ct._format_top3_lines_for_result(result, hc_present=bool(hc_rows))
        hc_lines = ct._format_hc_top3_lines(hc_rows) if hc_rows else []
        if lines or hc_lines:
            header = f"== {result.get('event_name') or 'Event'} =="
            all_lines.append(header)
            if lines:
                all_lines.extend(lines)
            if hc_lines:
                all_lines.extend(hc_lines)

    if not all_lines:
        print("No Top3 results found for Pohjanmaa weekly competitions.")
        return

    print("\n\n".join(["\n".join(chunk) for chunk in [all_lines]]))


if __name__ == "__main__":
    asyncio.run(main())
