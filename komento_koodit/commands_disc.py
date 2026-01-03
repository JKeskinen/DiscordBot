import asyncio
import re
import csv
import logging
from typing import Any, Dict, List, Tuple

import requests  # type: ignore[import]

try:
    from bs4 import BeautifulSoup  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None  # type: ignore[assignment]

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    discord = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


PDGA_DISC_URL = "https://www.pdga.com/technical-standards/equipment-certification/all"
PDGA_DISCS_CSV_URL = "https://www.pdga.com/technical-standards/equipment-certification/discs/export"
PDGA_DISCS_DETAIL_BASE = "https://www.pdga.com/technical-standards/equipment-certification/discs"


def _search_pdga_disc(name: str) -> List[Dict[str, Any]]:
    """Search PDGA lists for a disc name.

    Prefers the discs CSV export (with technical specs). Falls back to the
    older HTML equipment list if CSV fetch fails. Returns a list of dicts with
    keys like: manufacturer, product/model, cert_type/class, date, and various
    spec fields (max_weight_g, diameter_cm, height_cm, rim_depth_cm,
    rim_thickness_cm, inside_rim_diameter_cm, rim_depth_diameter_ratio_pct,
    flexibility_kg, disc_class, cert_number, approved_date, etc.).
    """
    name = (name or "").strip()
    if not name:
        return []

    q = name.lower()

    # First try the CSV export which contains all technical specifications.
    try:
        resp_csv = requests.get(PDGA_DISCS_CSV_URL, timeout=20)
        if getattr(resp_csv, "status_code", 0) == 200 and resp_csv.text:
            text = resp_csv.text
            rows = list(csv.DictReader(text.splitlines()))

            # Buckets for better ranking: exact > normalised-exact > prefix > substring
            exact: List[Dict[str, Any]] = []
            exact_norm: List[Dict[str, Any]] = []
            prefix: List[Dict[str, Any]] = []
            partial: List[Dict[str, Any]] = []

            # Normalise query by removing non-alphanumerics (so "fd" matches "FD (New)")
            q_norm = re.sub(r"[^a-z0-9]+", "", q)

            for row in rows:
                model = (row.get("Disc Model") or "").strip()
                manu = (row.get("Manufacturer / Distributor") or "").strip()
                if not model:
                    continue
                rec: Dict[str, Any] = {
                    "manufacturer": manu,
                    "product": model,
                    "model": model,
                    "cert_type": (row.get("Class") or "").strip(),
                    "disc_class": (row.get("Class") or "").strip(),
                    "date": (row.get("Approved Date") or "").strip(),
                    "approved_date": (row.get("Approved Date") or "").strip(),
                    "max_weight_g": (row.get("Max Weight (gr)") or "").strip(),
                    "diameter_cm": (row.get("Diameter (cm)") or "").strip(),
                    "height_cm": (row.get("Height (cm)") or "").strip(),
                    "rim_depth_cm": (row.get("Rim Depth (cm)") or "").strip(),
                    "inside_rim_diameter_cm": (row.get("Inside Rim Diameter (cm)") or "").strip(),
                    "rim_thickness_cm": (row.get("Rim Thickness (cm)") or "").strip(),
                    "rim_depth_diameter_ratio_pct": (row.get("Rim Depth / Diameter Ratio (%)") or "").strip(),
                    "rim_configuration": (row.get("Rim Configuration") or "").strip(),
                    "flexibility_kg": (row.get("Flexibility (kg)") or "").strip(),
                    "max_weight_vint_g": (row.get("Max Weight Vint (gr)") or "").strip(),
                    "last_year_production": (row.get("Last Year Production") or "").strip(),
                    "cert_number": (row.get("Certification Number") or "").strip(),
                    # Try to find any flight-number-like column name (robust to CSV variations)
                    "flight_numbers": "",
                }
                # populate flight_numbers by scanning row keys for anything containing 'flight'
                try:
                    for k, v in row.items():
                        if k and "flight" in k.lower() and v:
                            rec["flight_numbers"] = (v or "").strip()
                            break
                except Exception:
                    pass
                lm = model.lower()
                lm_norm = re.sub(r"[^a-z0-9]+", "", lm)

                if lm == q:
                    exact.append(rec)
                elif lm_norm == q_norm and q_norm:
                    exact_norm.append(rec)
                elif lm.startswith(q):
                    prefix.append(rec)
                elif q in lm:
                    partial.append(rec)

            ordered = exact or exact_norm or prefix or partial
            if ordered:
                return ordered
    except Exception:
        # If CSV fetch fails, fall back to HTML scraping below.
        logger.exception("Error while fetching PDGA discs CSV")

    # Legacy fallback: HTML equipment list search
    try:
        resp = requests.get(PDGA_DISC_URL, params={"title": name}, timeout=10)
    except Exception:
        return []

    if getattr(resp, "status_code", 0) != 200:
        return []

    html = resp.text or ""

    # Prefer BeautifulSoup when available for robust parsing
    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table", class_="views-table") or soup.find("table")
            if not table:
                return []
            results: List[Dict[str, Any]] = []
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 4:
                    continue
                manufacturer = tds[0].get_text(strip=True)
                product = tds[1].get_text(strip=True)
                cert_type = tds[2].get_text(strip=True)
                date = tds[3].get_text(strip=True)
                if not manufacturer and not product:
                    continue
                results.append({
                    "manufacturer": manufacturer,
                    "product": product,
                    "cert_type": cert_type,
                    "date": date,
                })
            return results
        except Exception:
            logger.exception("Error while parsing PDGA discs HTML with BeautifulSoup")

    # Fallback: very naive parsing from plain text
    results: List[Dict[str, Any]] = []
    lowered = html.lower()
    if name.lower() not in lowered:
        return []
    for line in html.splitlines():
        if name.lower() in line.lower() and "Disc Certification" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 4:
                manufacturer, product, cert_type, date = parts[0], parts[1], parts[2], parts[3]
                results.append({
                    "manufacturer": manufacturer,
                    "product": product,
                    "cert_type": cert_type,
                    "date": date,
                })
    return results


def _fetch_pdga_disc_image_url(model: str) -> str | None:
    """Best-effort fetch of a disc image URL from the PDGA product page.

    Uses the model name to build a slug and hits the detail page, then looks
    for an og:image meta tag or a reasonable <img> src. Returns None on any
    error or if nothing suitable is found.
    """
    model = (model or "").strip()
    if not model:
        return None

    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    if not slug:
        return None

    url = f"{PDGA_DISCS_DETAIL_BASE}/{slug}"
    try:
        resp = requests.get(url, timeout=10)
    except Exception:
        return None

    if getattr(resp, "status_code", 0) != 200 or not resp.text:
        return None

    html = resp.text

    # Prefer BeautifulSoup if available
    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html, "html.parser")

            # 1) Try OpenGraph image
            og = soup.find("meta", attrs={"property": "og:image"})
            if og and og.get("content") is not None:
                src = str(og.get("content") or "").strip()
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = "https://www.pdga.com" + src
                    return src

            # 2) Fallback to first <img> with a plausible src
            for img in soup.find_all("img"):
                src = str(img.get("src") or "").strip()
                if not src:
                    continue
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = "https://www.pdga.com" + src
                if src.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    return src
        except Exception:
            return None

    # Simple regex-based fallback if BeautifulSoup is not available
    try:
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if m:
            src = str(m.group(1) or "").strip()
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = "https://www.pdga.com" + src
            return src
    except Exception:
        pass

    try:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if m:
            src = str(m.group(1) or "").strip()
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = "https://www.pdga.com" + src
            return src
    except Exception:
        pass

    return None


def _fetch_pdga_flight_numbers(model: str) -> str | None:
    """Best-effort fetch of flight numbers from the PDGA product page.

    Tries to scrape the detail page for text like "Flight numbers: 12, 5, -1, 3".
    Returns a short string or None.
    """
    model = (model or "").strip()
    if not model:
        return None

    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    if not slug:
        return None

    url = f"{PDGA_DISCS_DETAIL_BASE}/{slug}"
    try:
        resp = requests.get(url, timeout=10)
    except Exception:
        return None

    if getattr(resp, "status_code", 0) != 200 or not resp.text:
        return None

    html = resp.text
    # Prefer BeautifulSoup
    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Look for any label/text containing "Flight" and grab nearby text
            text = soup.get_text(separator="\n")
            m = re.search(r"Flight\s*numbers?\s*[:\-]?\s*([0-9\-,.\s]+)", text, re.I)
            if m:
                return m.group(1).strip()
        except Exception:
            pass

    # Fallback regex on raw HTML
    try:
        m = re.search(r"Flight\s*numbers?\s*[:\-]?\s*([0-9\-,.\s]+)", html, re.I)
        if m:
            return m.group(1).strip()
    except Exception:
        pass

    return None


async def send_disc_card(channel: Any, best: Dict[str, Any], query_fallback: str = "") -> None:
    """Build and send a detailed disc card embed (or text fallback)."""
    model = (best.get("model") or best.get("product") or "").strip() or query_fallback
    manu = (best.get("manufacturer") or "").strip()
    approved = (best.get("approved_date") or best.get("date") or "").strip()

    max_weight = (best.get("max_weight_g") or "").strip()
    diameter = (best.get("diameter_cm") or "").strip()
    height = (best.get("height_cm") or "").strip()
    rim_depth = (best.get("rim_depth_cm") or "").strip()
    rim_thickness = (best.get("rim_thickness_cm") or "").strip()
    inside_rim = (best.get("inside_rim_diameter_cm") or "").strip()
    ratio = (best.get("rim_depth_diameter_ratio_pct") or "").strip()
    disc_class = (best.get("disc_class") or best.get("cert_type") or "").strip()
    flex = (best.get("flexibility_kg") or "").strip()
    cert_no = (best.get("cert_number") or "").strip()
    last_year = (best.get("last_year_production") or "").strip()

    # Build a nicely formatted description with bold labels (Finnish) similar to the example
    desc_lines: List[str] = []
    desc_lines.append(f"**{model}**")
    if manu:
        desc_lines.append(f"**Valmistaja:** {manu}")
    if approved:
        desc_lines.append(f"**Hyväksytty:** {approved}")
    if max_weight:
        desc_lines.append(f"**Paino:** {max_weight} g")
    if diameter:
        desc_lines.append(f"**Halkaisija:** {diameter} cm")
    if height:
        desc_lines.append(f"**Korkeus:** {height} cm")
    if rim_depth:
        desc_lines.append(f"**Rimmin syvyys:** {rim_depth} cm")
    if rim_thickness:
        desc_lines.append(f"**Rimmin leveys:** {rim_thickness} cm")
    if inside_rim:
        desc_lines.append(f"**Rimmin sisähalkaisija:** {inside_rim} cm")
    if ratio:
        desc_lines.append(f"**Rimmin syvyys/halkaisija:** {ratio} %")
    if disc_class:
        desc_lines.append(f"**Luokka:** {disc_class}")
    if flex:
        desc_lines.append(f"**Joustavuus:** {flex} kg")
    if cert_no:
        desc_lines.append(f"**Sertifikaatti:** {cert_no}")
    if last_year:
        desc_lines.append(f"**Viimeinen tuotantovuosi:** {last_year}")

    # Flight numbers: try from result first, otherwise fetch from PDGA detail page
    flight_nums = (best.get("flight_numbers") or "").strip()
    if not flight_nums:
        try:
            loop = asyncio.get_running_loop()
            fetched = await loop.run_in_executor(None, lambda: _fetch_pdga_flight_numbers(model))
            if fetched:
                flight_nums = fetched
        except Exception:
            flight_nums = flight_nums

    if flight_nums:
        desc_lines.append(f"**Lentonumerot:** {flight_nums}")

    # Add PDGA link
    desc_lines.append("\n[PDGA](https://www.pdga.com/technical-standards/equipment-certification/discs)")

    desc = "\n".join(desc_lines)

    # Try to fetch image URL too
    image_url: str | None = None
    try:
        loop = asyncio.get_running_loop()
        image_url = await loop.run_in_executor(None, lambda: _fetch_pdga_disc_image_url(model))
    except Exception:
        image_url = None

    try:
        Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
        if Embed_cls:
            title = "Löytyi kiekkoja:"
            embed = Embed_cls(title=title, description=desc)
            try:
                if image_url:
                    # Use thumbnail so it appears on the right like the example
                    embed.set_thumbnail(url=image_url)
            except Exception:
                pass
            await channel.send(embed=embed)
        else:
            await channel.send(f"Löytyi kiekkoja:\n{desc}")
    except Exception:
        try:
            await channel.send(f"Löytyi kiekkoja:\n{desc}")
        except Exception:
            pass


async def handle_kiekko(message: Any, parts: Any, pending_disc_choices: Dict[Tuple[str, str], List[Dict[str, Any]]]) -> None:
    """Handle the !kiekko command.

    This encapsulates the PDGA search and selection logic so that the main
    command handler only needs to delegate here.
    """
    if not parts or len(parts) < 1:
        return

    query = " ".join(parts[1:]).strip()
    if not query:
        # Näytä käytön ohje embed-korttina samaan tyyliin kuin muut komennot
        try:
            Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
            title = "Käyttö: !kiekko"
            desc = (
                "Hae PDGA:n hyväksymistä kiekoista nimeä käyttämällä.\n\n"
                "Esimerkki:\n!kiekko destroyer"
            )
            if Embed_cls:
                embed = Embed_cls(title=title, description=desc)
                await message.channel.send(embed=embed)
            else:
                await message.channel.send(f"{title}\n{desc}")
        except Exception:
            pass
        return

    try:
        if hasattr(message.channel, "trigger_typing"):
            await message.channel.trigger_typing()
    except Exception:
        pass

    loop = asyncio.get_running_loop()

    def _do_search() -> List[Dict[str, Any]]:
        return _search_pdga_disc(query)

    res = await loop.run_in_executor(None, _do_search)

    if not res:
        try:
            await message.channel.send(f"Kiekkoa ei löytynyt haulla: {query}")
        except Exception:
            pass
        return

    # If there are many matches for a short query, ask user to pick
    if len(res) > 1 and len(query) <= 4:
        # limit to 9 numbered options
        options = res[:9]
        lines: List[str] = []
        for i, d in enumerate(options, start=1):
            model_opt = (d.get("model") or d.get("product") or "").strip() or "(tuntematon)"
            manu_opt = (d.get("manufacturer") or "").strip()
            date_opt = (d.get("approved_date") or d.get("date") or "").strip()
            parts_opt = [f"{i}) {model_opt}"]
            if manu_opt:
                parts_opt.append(f"— {manu_opt}")
            if date_opt:
                parts_opt.append(f"— {date_opt}")
            lines.append(" ".join(parts_opt))

        # Show the options using an embed so it looks like a
        # "real" answer; selection is done by replying with a number.
        try:
            Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
            footer_line = f"Vastaa numerolla (1–{len(options)}) valitaksesi parhaan vaihtoehdon."
            desc_lines = lines + ["", footer_line]
            if Embed_cls:
                embed = Embed_cls(
                    title=f'Löytyi useita kiekkoja haulla "{query}":',
                    description="\n".join(desc_lines),
                )
                await message.channel.send(embed=embed)
            else:
                header = f'Löytyi useita kiekkoja haulla "{query}":'
                await message.channel.send("\n".join([header] + desc_lines))

            # store pending options for this user/channel
            try:
                key = (str(message.channel.id), str(message.author.id))
                pending_disc_choices[key] = options
            except Exception:
                pass
        except Exception:
            pass
        return

    # Use the best match (first in list) and send a detailed card
    best = res[0]
    await send_disc_card(message.channel, best, query)
