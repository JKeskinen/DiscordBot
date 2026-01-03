import logging
import os
import re
import time
import urllib.parse
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup as BS

from . import data_store

# Alueet: luetaan WEEKLY_AREAS-ympäristömuuttujasta ("A;B;C") tai käytetään oletuslistaa.
AREAS_ENV = os.environ.get("WEEKLY_AREAS", "").strip()
if AREAS_ENV:
    AREAS = [a.strip() for a in AREAS_ENV.split(";") if a.strip()]
else:
    AREAS = [
        "Etelä-Pohjanmaa",
        "Pohjanmaa",
        "Keski-Pohjanmaa",
        "Keski-Suomi",
        "Pirkanmaa",
        "Satakunta",
    ]

# Päiväysikkuna: tänään -> seuraavat 7 päivää.
_today = date.today()
DATE1 = _today.isoformat()
DATE2 = (_today + timedelta(days=7)).isoformat()

COUNTRY = os.environ.get("WEEKLY_COUNTRY", "FI")
TYPE = os.environ.get("WEEKLY_TYPE", "")  # '' = kaikki, 'd' = doubles, 'c' = kilpailut jne.

logger = logging.getLogger(__name__)

weekly_re = re.compile(r"\b(weekly|week|viikko|viikkari|viikotta|viikkokisa|viikkokisat|viikkot|weeklies)\b", re.I)
pair_re = re.compile(r"\b(pari|parikisa|parikilpailu|parigolf|pariviikko|pariviikkokisat|pair|pairs|double|doubles|best shot|max2)\b", re.I)


def _fetch_for_area(area: str) -> list[dict]:
    area_enc = urllib.parse.quote(area)
    type_part = f"&type={TYPE}" if TYPE else ""
    url = (
        "https://discgolfmetrix.com/competitions_server.php?name=&"
        f"date1={DATE1}&date2={DATE2}&"
        "registration_date1=&registration_date2=&"
        f"country_code={COUNTRY}{type_part}&from=1&to=200&page=all&"
        f"area={area_enc}"
    )

    logger.info("[seutu] URL (%s): %s", area, url)
    start = time.perf_counter()
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    elapsed = time.perf_counter() - start
    logger.info("[seutu] HTTP time %.2fs, status %s", elapsed, resp.status_code)
    resp.encoding = resp.apparent_encoding

    soup = BS(resp.text, "html.parser")
    container = soup.find(id="competition_list2")

    results: list[dict] = []

    if not container:
        logger.info("[seutu] Ei kilpailulistaa alueelle %s", area)
        return results

    # gridlist-merkinnät
    for a in container.select("a.gridlist"):
        href = a.get("href", "") or ""
        href_str = str(href)
        comp_id = None
        m = re.search(r"/(\d+)", href_str)
        if m:
            comp_id = m.group(1)
        h2 = a.find("h2")
        if h2 is not None:
            title = h2.get_text(strip=True)
        else:
            title = a.get_text(strip=True) or ""
        tspan = a.select_one(".competition-type")
        tier = tspan.get_text(strip=True) if tspan is not None else ""
        meta = a.select(".metadata-list li") or []
        date_txt = meta[0].get_text(strip=True) if len(meta) > 0 and getattr(meta[0], "get_text", None) else ""
        location = meta[1].get_text(strip=True) if len(meta) > 1 and getattr(meta[1], "get_text", None) else ""

        kind = None
        title_l = (title or "").lower()
        loc_l = (location or "").lower()
        tier_l = (tier or "").lower()
        pair_keywords = [
            "pari",
            "parikisa",
            "parikilpailu",
            "parigolf",
            "pariviikko",
            "pariviikkokisat",
            "pair",
            "pairs",
            "double",
            "doubles",
            "best shot",
            "max2",
        ]
        weekly_keywords = [
            "weekly",
            "week",
            "viikko",
            "viikkari",
            "viikotta",
            "viikkokisa",
            "viikkokisat",
            "viikkot",
            "weeklies",
        ]
        is_pair = bool(
            pair_re.search(title_l)
            or pair_re.search(loc_l)
            or pair_re.search(tier_l)
            or any(k in title_l or k in loc_l or k in tier_l for k in pair_keywords)
        )
        is_weekly = bool(
            weekly_re.search(title_l)
            or weekly_re.search(loc_l)
            or weekly_re.search(tier_l)
            or any(k in title_l or k in loc_l or k in tier_l for k in weekly_keywords)
        )
        is_liiga = "liiga" in title_l or "liiga" in tier_l
        if is_pair:
            kind = "PARIKISA"
        elif is_weekly and not is_liiga:
            kind = "VIIKKOKISA"

        url_full = ""
        if href_str:
            try:
                url_full = urllib.parse.urljoin("https://discgolfmetrix.com", href_str)
            except Exception:
                url_full = href_str

        results.append(
            {
                "id": comp_id,
                "title": title,
                "tier": tier,
                "date": date_txt,
                "location": location,
                "kind": kind,
                "url": url_full,
                "area": area,
            }
        )

    # taulukko-fallback
    for tr in container.select("table.table-list tbody tr"):
        cols = tr.find_all("td")
        if not cols:
            continue
        link = cols[0].find("a")
        href = link.get("href", "") if link else ""
        href_str = str(href)
        comp_id = None
        m = re.search(r"/(\d+)", href_str)
        if m:
            comp_id = m.group(1)
        name = link.get_text(strip=True) if link is not None else cols[0].get_text(strip=True) or ""
        date_txt = cols[1].get_text(strip=True) if len(cols) > 1 and getattr(cols[1], "get_text", None) else ""
        tier = cols[2].get_text(strip=True) if len(cols) > 2 and getattr(cols[2], "get_text", None) else ""
        location = cols[3].get_text(strip=True) if len(cols) > 3 and getattr(cols[3], "get_text", None) else ""

        kind = None
        name_l = (name or "").lower()
        loc_l = (location or "").lower()
        tier_l = (tier or "").lower()
        if pair_re.search(name_l) or pair_re.search(loc_l) or pair_re.search(tier_l):
            kind = "PARIKISA"
        elif weekly_re.search(name_l) or weekly_re.search(loc_l) or weekly_re.search(tier_l):
            kind = "VIIKKOKISA"

        url_full = ""
        if href_str:
            try:
                url_full = urllib.parse.urljoin("https://discgolfmetrix.com", href_str)
            except Exception:
                url_full = href_str

        results.append(
            {
                "id": comp_id,
                "title": name,
                "tier": tier,
                "date": date_txt,
                "location": location,
                "kind": kind,
                "url": url_full,
                "area": area,
            }
        )

    return results


def _dedupe(results: list[dict]) -> list[dict]:
    seen = set()
    unique: list[dict] = []
    for r in results:
        cid = r.get("id") or r.get("title")
        if cid in seen:
            continue
        seen.add(cid)
        unique.append(r)
    return unique


def main() -> None:
    all_results: list[dict] = []
    for area in AREAS:
        try:
            area_results = _fetch_for_area(area)
            all_results.extend(area_results)
        except Exception as e:  # pragma: no cover
            logger.exception("[seutu] Virhe haettaessa aluetta %s: %s", area, e)

    if not all_results:
        logger.info("[seutu] Ei tuloksia yhdeltäkään alueelta: %s", ", ".join(AREAS))
        return

    # Deduplikointi ID:n/tittelin perusteella.
    unique = _dedupe(all_results)

    # Jos haetaan nimenomaan usealle alueelle, kaikki oletetaan viikkokisoiksi, jos kind puuttuu.
    for r in unique:
        if not r.get("kind"):
            r["kind"] = "VIIKKOKISA"

    from collections import Counter

    kcounts = Counter([r.get("kind") or "OTHER" for r in unique])
    logger.info("[seutu] Tuloksia yhteensä %d, jakauma: %s", len(unique), dict(kcounts))

    entries = [r for r in unique if r.get("kind") == "VIIKKOKISA"]
    try:
        data_store.save_category("VIIKKARIT_SEUTU", entries)
    except Exception as e:  # pragma: no cover
        logger.exception("[seutu] VIIKKARIT_SEUTU tallennus epäonnistui: %s", e)


if __name__ == "__main__":  # pragma: no cover
    main()
