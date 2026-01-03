#!/usr/bin/env python3
"""Fetch and print Top3 + HC for event 3523691 for quick local check."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__) or "", ".."))
sys.path.insert(0, ROOT)

from komento_koodit import commands_tulokset as ct


def main():
    url = "https://discgolfmetrix.com/3523691&view=result"
    print("Fetching:", url)
    result = ct._fetch_competition_results(url)
    if not result:
        print("Failed to fetch/parse result")
        return
    print("Parsed event:", result.get("event_name"))
    hc_rows = ct._fetch_handicap_table(url)
    lines = ct._format_top3_lines_for_result(result, hc_present=bool(hc_rows))
    hc_lines = ct._format_hc_top3_lines(hc_rows) if hc_rows else []

    if lines:
        print("\n".join(lines))
    if hc_lines:
        print("\n".join(hc_lines))


if __name__ == "__main__":
    main()
