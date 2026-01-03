import os
import re
import asyncio
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup as BS

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover
    discord = None  # type: ignore[assignment]

try:
    from . import data_store
except Exception:  # pragma: no cover
    data_store = None  # type: ignore[assignment]

try:
    from . import metrix_stats
except Exception:  # pragma: no cover
    metrix_stats = None  # type: ignore[assignment]


BASE_ROOT_URL = "https://discgolfmetrix.com"


_RATING_CACHE: Dict[str, Optional[float]] = {}

# Set to True during local debugging to enable console debug prints for this module.
DEBUG_TULOKSET = False


def _get_player_rating_from_metrix(metrix_id: str) -> Optional[float]:
    """Hae pelaajan Metrix-rating (viimeisin oranssi piste) ID:n perusteella.

    Käyttää metrix_stats.fetch_player_stats-funktiota ja välimuistia, jotta
    samaa ID:tä ei haeta useita kertoja yhden komennon aikana.
    """

    mid = (metrix_id or "").strip()
    if not mid or metrix_stats is None:
        return None

    if mid in _RATING_CACHE:
        return _RATING_CACHE[mid]

    rating_val: Optional[float] = None
    try:
        stats = metrix_stats.fetch_player_stats(mid)
    except Exception:
        stats = None

    if stats is not None and getattr(stats, "rating", None) is not None:
        try:
            rating_val = float(stats.rating)  # type: ignore[arg-type]
        except Exception:
            rating_val = None

    _RATING_CACHE[mid] = rating_val
    return rating_val


def _extract_competition_id(raw: str) -> Optional[str]:
    """Poimi Metrix-kilpailun ID annetusta tekstistä.

    Hyväksyy suoran numeron ("3523248") tai Metrix-linkin, josta
    poimitaan ensimmäinen vähintään 5-numeroa pitkä numerosarja.
    """

    txt = (raw or "").strip()
    if not txt:
        return None

    # Jos annettu on pelkkä numero, käytetään sitä sellaisenaan.
    if txt.isdigit() and len(txt) >= 4:
        return txt

    m = re.search(r"(\d{4,})", txt)
    if not m:
        return None
    return m.group(1)


def _build_competition_url(raw: str) -> Optional[str]:
    """Muodosta kilpailun URL annetusta ID:stä tai linkistä."""

    txt = (raw or "").strip()
    if not txt:
        return None

    # Jos annettu on jo URL, palautetaan se sellaisenaan.
    if "http://" in txt or "https://" in txt:
        return txt

    cid = _extract_competition_id(txt)
    if not cid:
        return None

    return f"{BASE_ROOT_URL}/{cid}"


def _ensure_results_url(url: str) -> str:
    """Lisää tai korvaa Metrix-linkkiin view=result-parametrin.

    Esim.:
      https://discgolfmetrix.com/3523248           -> https://discgolfmetrix.com/3523248&view=result
      https://discgolfmetrix.com/3523248?view=...  -> ...?view=result
    """

    txt = (url or "").strip()
    if not txt:
        return url

    # Jos URL:ssa on jo view-parametri, korvataan se.
    if "view=" in txt:
        return re.sub(r"view=[^&]*", "view=result", txt)

    # Muussa tapauksessa lisätään &view=result (käyttäjän antaman esimerkin mukaisesti).
    return txt + "&view=result"


def _guess_event_name(soup: BS) -> str:
    """Yritä päätellä kilpailun nimi sivun otsikoista."""

    try:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(strip=True)
    except Exception:
        pass

    try:
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            return title_tag.get_text(strip=True)
    except Exception:
        pass

    return "Metrix-kilpailu"


def _guess_class_name_for_table(table, fallback_index: int) -> str:
    """Yritä löytää sarjan / luokan nimi taulukolle.

    Parempi heuristiikka:
      - Jos <thead> sisältää <th> jossa on jotain muotoa "Name (N)", käytä sitä.
      - Muussa tapauksessa etsi ensimmäinen <th>, joka ei ole selvästi sarakkeen otsikko.
      - Jos ei löydy, käytä captionia tai lähintä h2/h3 -otsikkoa.
      - Lopuksi fallback "Sarja N".
    """

    name: Optional[str] = None

    try:
        thead = table if getattr(table, 'name', None) == 'thead' else table.find("thead")
        if thead:
            ths = thead.find_all("th")
            candidate = None
            for th in ths:
                txt = th.get_text(" ", strip=True)
                if not txt:
                    continue
                # Etsi muotoa "Something (3)"
                if re.search(r"\(\d+\)", txt) and not txt.lower().startswith("sija"):
                    name = txt
                    break
                low = txt.lower()
                if low in ("sija", "sij", "nimi", "pelaaja", "+/-", "kortti", "tot"):
                    continue
                # Prefer multi-word labels (todennäköisemmin luokkien nimiä)
                if len(txt.split()) >= 2:
                    name = txt
                    break
                if candidate is None:
                    candidate = txt
            if not name and candidate:
                name = candidate
    except Exception:
        name = None

    if not name:
        try:
            # caption
            cap = table.find("caption")
            if cap and cap.get_text(strip=True):
                name = cap.get_text(strip=True)
        except Exception:
            pass

    if not name:
        try:
            heading = table.find_previous(["h3", "h4", "h2"])
            if heading:
                txt = heading.get_text(" ", strip=True)
                if txt:
                    name = txt
        except Exception:
            pass

    if not name:
        name = f"Sarja {fallback_index + 1}"

    if len(name) > 80:
        name = name[:77] + "..."

    return name


def _parse_metrix_date(value: str) -> Optional[date]:
    """Yritä tulkita Metrixin VIIKKOKISA.jsonissa oleva päivämäärä.

    Sama logiikka kuin commands_viikkarit._parse_metrix_date: palauttaa pelkän
    päivämäärän (ei kellonaikaa).
    """

    if not value:
        return None

    txt = value.strip()
    if not txt:
        return None

    if " - " in txt:
        txt = txt.split(" - ", 1)[0].strip()

    for fmt in ("%m/%d/%y %H:%M", "%m/%d/%y", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(txt, fmt)
            return dt.date()
        except Exception:
            continue

    return None


def _parse_results_html(html_text: str) -> Dict[str, Any]:
    """Parsii Metrix-kilpailun tulossivun HTML:n.

    Palauttaa rakenteen:
    {
      "event_name": str,
      "classes": [
        {
          "class_name": str,
          "rows": [
            {"position": int, "name": str, "to_par": str, "total": str},
            ...
          ],
        },
        ...
      ],
    }
    """

    soup = BS(html_text, "html.parser")
    event_name = _guess_event_name(soup)

    class_results: List[Dict[str, Any]] = []

    tables = soup.find_all("table")
    idx = 0
    for table in tables:
        # Joissakin Metrix-sivuissa yksi <table> voi sisältää useita
        # <thead>/<tbody>-pareja, jotka vastaavat eri luokkia. Käsitellään
        # kukin thead/tbody -pariksi erikseen.
        theads = table.find_all("thead")
        if theads:
            for thead in theads:
                # Etsi mahdollinen rating-index theadin sisältä
                rating_index = None
                header_cells = thead.find_all("th")
                for i, th in enumerate(header_cells):
                    txt = th.get_text(strip=True).lower()
                    if "rating" in txt or "rtg" in txt:
                        rating_index = i
                        break

                # Etsi vastaava tbody (seuraa theadia). Joissain sivuissa
                # pelaajarivit ovat suoraan thead:in jälkeen <tr>-elementeinä
                # (ei erillistä <tbody>). Käsitellään molemmat tapaukset.
                tbody = thead.find_next_sibling("tbody")
                rows_iterable = None
                if tbody:
                    rows_iterable = tbody.find_all("tr")
                else:
                    # Kerää tr-elementit, jotka seuraavat theadia, kunnes
                    # törmätään uuteen theadiin tai tbody:hin.
                    rows_tags: List[Any] = []
                    s = thead.find_next_sibling()
                    while s:
                        if getattr(s, 'name', None) == 'tr':
                            rows_tags.append(s)
                            s = s.find_next_sibling()
                            continue
                        if getattr(s, 'name', None) == 'thead':
                            break
                        if getattr(s, 'name', None) == 'tbody':
                            # jos löytyi tbody myöhemmin, lisää sen tr:t ja lopeta
                            rows_tags.extend(s.find_all('tr'))
                            break
                        s = s.find_next_sibling()
                    if rows_tags:
                        rows_iterable = rows_tags

                if not rows_iterable:
                    # Jos ei löydy rivejä, etsitään seuraava tbody taulukosta
                    tbodys = table.find_all("tbody")
                    rows_iterable = tbodys[0].find_all("tr") if tbodys else None

                if not rows_iterable:
                    continue

                rows_data: List[Dict[str, Any]] = []
                for tr in rows_iterable:
                    player_td = tr.find("td", class_="player-cell")
                    if not player_td:
                        continue
                    tds = tr.find_all("td")
                    if len(tds) < 3:
                        continue

                    pos_text = tds[0].get_text(strip=True)
                    try:
                        m_pos = re.match(r"(\d+)", pos_text)
                        pos_html = int(m_pos.group(1)) if m_pos else None
                    except Exception:
                        pos_html = None

                    name_parts = list(player_td.stripped_strings)
                    name = name_parts[0] if name_parts else player_td.get_text(strip=True)

                    metrix_id = ""
                    try:
                        link = player_td.find("a", href=True)
                        if link is not None:
                            href = str(link.get("href") or "")
                            m_id = re.search(r"/player/(\d+)", href)
                            if not m_id:
                                m_id = re.search(r"user_id=(\d+)", href)
                            if m_id:
                                metrix_id = m_id.group(1)
                    except Exception:
                        metrix_id = ""

                    to_par = tds[2].get_text(strip=True)
                    total = tds[-1].get_text(strip=True)

                    rating = ""
                    if rating_index is not None and rating_index < len(tds):
                        rating = tds[rating_index].get_text(strip=True)

                    rows_data.append({
                        "position": pos_html,
                        "name": name,
                        "to_par": to_par,
                        "total": total,
                        "rating": rating,
                        "metrix_id": metrix_id,
                    })

                if rows_data:
                    # Poista rivit, joissa total==0 (DNS / did not start)
                    filtered_rows: List[Dict[str, Any]] = []
                    for r in rows_data:
                        total_txt = str(r.get("total") or "").strip()
                        m = re.match(r"-?\d+", total_txt)
                        total_num = int(m.group(0)) if m else None
                        if total_num == 0:
                            if DEBUG_TULOKSET:
                                print(f"[DEBUG] Skipping DNS row: {r}")
                            continue
                        filtered_rows.append(r)
                    rows_data = filtered_rows
                    # Laske sijat kuten aiemmin
                    def _score_key_inline(r: Dict[str, Any]) -> Any:
                        total_txt = str(r.get("total") or "").strip()
                        to_par_txt = str(r.get("to_par") or "").strip()

                        def _parse_int(s: str) -> Optional[int]:
                            m = re.match(r"-?\d+", s)
                            if not m:
                                return None
                            try:
                                return int(m.group(0))
                            except Exception:
                                return None

                        total_val = _parse_int(total_txt)
                        to_par_val = _parse_int(to_par_txt)

                        primary = total_val if total_val is not None else 9999
                        secondary = to_par_val if to_par_val is not None else 0
                        return (primary, secondary)

                    last_score: Optional[Any] = None
                    current_place = 0
                    same_count = 0
                    for row in rows_data:
                        score = _score_key_inline(row)
                        if last_score is None:
                            # first row
                            current_place = 1
                            same_count = 1
                        elif score == last_score:
                            # tie: same place as previous
                            same_count += 1
                        else:
                            # new score: advance place by number of tied players
                            current_place = current_place + same_count
                            same_count = 1
                        row["position"] = current_place
                        last_score = score

                    # Täydennetään ratingit top3:lle
                    if metrix_stats is not None:
                        top_rows = [
                            r for r in rows_data
                            if isinstance(r.get("position"), int) and 1 <= r["position"] <= 3
                        ]
                        if top_rows:
                            unique_ids = {
                                str(r.get("metrix_id") or "").strip()
                                for r in top_rows
                                if str(r.get("metrix_id") or "").strip()
                            }
                            for mid in unique_ids:
                                _get_player_rating_from_metrix(mid)

                            for r in top_rows:
                                if not str(r.get("rating") or "").strip():
                                    mid = str(r.get("metrix_id") or "").strip()
                                    if not mid:
                                        continue
                                    val = _get_player_rating_from_metrix(mid)
                                    if val is not None:
                                        try:
                                            r["rating"] = str(int(round(val)))
                                        except Exception:
                                            r["rating"] = str(val)

                    class_name = _guess_class_name_for_table(thead, idx)
                    class_results.append({
                        "class_name": class_name,
                        "rows": rows_data,
                    })
                    idx += 1
            continue
        # Fallback: jos ei theadeja, käsittele kuten aiemmin koko table rivinä
        rows_data: List[Dict[str, Any]] = []
        rating_index: Optional[int] = None
        for tr in table.find_all("tr"):
            header_cells = tr.find_all("th")
            if header_cells:
                if rating_index is None:
                    for i, th in enumerate(header_cells):
                        txt = th.get_text(strip=True).lower()
                        if "rating" in txt or "rtg" in txt:
                            rating_index = i
                            break
                continue

            player_td = tr.find("td", class_="player-cell")
            if not player_td:
                continue

            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            pos_text = tds[0].get_text(strip=True)
            try:
                m_pos = re.match(r"(\d+)", pos_text)
                pos_html = int(m_pos.group(1)) if m_pos else None
            except Exception:
                pos_html = None

            name_parts = list(player_td.stripped_strings)
            name = name_parts[0] if name_parts else player_td.get_text(strip=True)

            metrix_id = ""
            try:
                link = player_td.find("a", href=True)
                if link is not None:
                    href = str(link.get("href") or "")
                    m_id = re.search(r"/player/(\d+)", href)
                    if not m_id:
                        m_id = re.search(r"user_id=(\d+)", href)
                    if m_id:
                        metrix_id = m_id.group(1)
            except Exception:
                metrix_id = ""

            to_par = tds[2].get_text(strip=True)
            total = tds[-1].get_text(strip=True)

            rating = ""
            if rating_index is not None and rating_index < len(tds):
                rating = tds[rating_index].get_text(strip=True)

            rows_data.append({
                "position": pos_html,
                "name": name,
                "to_par": to_par,
                "total": total,
                "rating": rating,
                "metrix_id": metrix_id,
            })

        if rows_data:
            # Poista rivit, joissa total==0 (DNS / did not start)
            filtered_rows: List[Dict[str, Any]] = []
            for r in rows_data:
                total_txt = str(r.get("total") or "").strip()
                m = re.match(r"-?\d+", total_txt)
                total_num = int(m.group(0)) if m else None
                if total_num == 0:
                    if DEBUG_TULOKSET:
                        print(f"[DEBUG] Skipping DNS row: {r}")
                    continue
                filtered_rows.append(r)
            rows_data = filtered_rows
            # Sama laskenta kuin aiemmin
            def _score_key_inline(r: Dict[str, Any]) -> Any:
                total_txt = str(r.get("total") or "").strip()
                to_par_txt = str(r.get("to_par") or "").strip()

                def _parse_int(s: str) -> Optional[int]:
                    m = re.match(r"-?\d+", s)
                    if not m:
                        return None
                    try:
                        return int(m.group(0))
                    except Exception:
                        return None

                total_val = _parse_int(total_txt)
                to_par_val = _parse_int(to_par_txt)

                primary = total_val if total_val is not None else 9999
                secondary = to_par_val if to_par_val is not None else 0
                return (primary, secondary)

            last_score: Optional[Any] = None
            current_place = 0
            for row in rows_data:
                score = _score_key_inline(row)
                if last_score is None:
                    current_place = 1
                elif score != last_score:
                    current_place += 1
                row["position"] = current_place
                last_score = score

            class_name = _guess_class_name_for_table(table, idx)
            class_results.append({
                "class_name": class_name,
                "rows": rows_data,
            })
            idx += 1

    return {
        "event_name": event_name,
        "classes": class_results,
    }


def _fetch_competition_results(url: str) -> Optional[Dict[str, Any]]:
    """Hae Metrix-kilpailun tulossivu ja parsittu rakenne.

    Palauttaa None, jos haku tai parsiminen epäonnistuu.
    """

    headers = {
        "User-Agent": os.environ.get(
            "METRIX_USER_AGENT",
            "Mozilla/5.0 (compatible; MetrixDiscordBot/1.0)",
        )
    }

    try:
        resp = requests.get(url, headers=headers, timeout=25)
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    try:
        return _parse_results_html(resp.text)
    except Exception:
        return None


def _format_top3_lines_for_result(result: Dict[str, Any]) -> List[str]:
    """Muodosta tekstirivit yksittäisen kilpailun Top3-sijoituksista luokittain."""

    classes: List[Dict[str, Any]] = result.get("classes", [])  # type: ignore[assignment]
    lines: List[str] = []

    for cls in classes:
        cname = str(cls.get("class_name") or "Sarja")
        m_count = re.search(r"^(.*)\((\d+)\)$", cname)
        if m_count:
            base_name = m_count.group(1).strip()
            count = m_count.group(2)
            cname_fmt = f"{base_name} ({count} pelaajaa)"
        else:
            cname_fmt = cname

        rows: List[Dict[str, Any]] = cls.get("rows", [])

        # Näytetään vain top3: kaikki, joiden sijoitus on 1, 2 tai 3 (myös tasatilanteet)
        # Eli jos sijoitukset ovat 1,2,2,4 → näytetään 1,2,2. Jos 1,2,3,3 → näytetään 1,2,3,3.
        # Etsi kaikki, joiden sijoitus on 1 tai 2, ja kaikki, joilla sijoitus on 3 (kaikki 3:t mukaan)
        top_rows = []
        count_3 = 0
        for r in rows:
            pos = r.get("position")
            total = str(r.get("total") or "")
            try:
                total_num = int(total)
            except Exception:
                total_num = None
            if not isinstance(pos, int) or total_num == 0:
                continue
            if pos == 1 or pos == 2:
                top_rows.append(r)
            elif pos == 3:
                count_3 += 1
        # Jos on yhtään sijoitus 3, lisätään kaikki, joilla pos==3
        if count_3 > 0:
            for r in rows:
                pos = r.get("position")
                total = str(r.get("total") or "")
                try:
                    total_num = int(total)
                except Exception:
                    total_num = None
                if isinstance(pos, int) and pos == 3 and total_num != 0 and r not in top_rows:
                    top_rows.append(r)
        # Tulosta luokan otsikko aina, vaikka top_rows olisi tyhjä
        lines.append(f"**{cname_fmt}**")
        if top_rows:
            for r in top_rows:
                pos = r.get("position")
                name = str(r.get("name") or "")
                to_par = str(r.get("to_par") or "")
                total = str(r.get("total") or "")
                rating = str(r.get("rating") or "").strip()

                tail = ""
                if to_par:
                    tail += f" {to_par}"

                inner_parts: List[str] = []
                if total:
                    inner_parts.append(total)
                if rating:
                    inner_parts.append(f"rtg {rating}")

                if inner_parts:
                    tail += f" ({', '.join(inner_parts)})"

                line = f"{pos}) {name}{tail}"
                lines.append(line.strip())
        lines.append("")

    return [l for l in lines if l.strip()]


async def _handle_single_viikkari_results(message: Any, raw: str) -> None:
    """Hae yhden Metrix-viikkarin tulokset linkin tai ID:n perusteella."""

    url_base = _build_competition_url(raw)
    if not url_base:
        try:
            await message.channel.send(
                "Anna Metrix-kilpailun ID tai linkki. Esim: 3523248 tai https://discgolfmetrix.com/3523248"
            )
        except Exception:
            pass
        return

    url = _ensure_results_url(url_base)

    try:
        if hasattr(message.channel, "trigger_typing"):
            await message.channel.trigger_typing()
    except Exception:
        pass

    loop = asyncio.get_running_loop()

    def _do_fetch() -> Optional[Dict[str, Any]]:
        return _fetch_competition_results(url)

    result = await loop.run_in_executor(None, _do_fetch)

    if not result or not result.get("classes"):
        try:
            await message.channel.send(
                "Tulosten hakeminen epäonnistui tältä Metrix-sivulta. "
                "Varmista, että kilpailun tulokset ovat julkisia."
            )
        except Exception:
            pass
        return

    event_name = str(result.get("event_name") or "Metrix-viikkari")
    # Erotellaan HC- ja raakatulokset, jos molemmat löytyvät
    hc_lines = []
    raw_lines = []
    classes = result.get("classes", [])
    for cls in classes:
        cname = str(cls.get("class_name") or "")
        if "HC" in cname.upper() or "handicap" in cname.lower():
            hc_lines.extend(_format_top3_lines_for_result({"classes": [cls]}))
        else:
            raw_lines.extend(_format_top3_lines_for_result({"classes": [cls]}))
    lines = []
    if hc_lines:
        lines.append("__Handicap (HC) tulokset__")
        lines.extend(hc_lines)
    if raw_lines:
        lines.append("__Raakatulokset__")
        lines.extend(raw_lines)
    desc = "\n".join(lines) if lines else "Tulokset löytyivät, mutta Top3-sijoituksia ei voitu tulkita."

    try:
        Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
        if Embed_cls:
            title = f"Viikkaritulokset: {event_name}"
            # Lisätään linkki suoraan kisaan embedin URL-kenttään.
            embed = Embed_cls(title=title, description=desc, url=url)
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(f"Viikkaritulokset: {event_name}\n{url}\n\n{desc}")
    except Exception:
        try:
            await message.channel.send(desc)
        except Exception:
            pass


async def _handle_weekly_viikkari_results(message: Any, area_mode: str) -> None:
    """Hae tämän viikon viikkarikisojen Top3-tulokset annetulla alueella.

    area_mode vastaa !viikkarit-komennon lyhenteitä:
      - "ep" (oletus) → VIIKKOKISA.json (Etelä-Pohjanmaa)
      - "mk" → VIIKKARIT_SEUTU.json (lähimaakunnat)
      - muut koodit kuten "pohj", "kp" jne. samaan tapaan kuin !viikkarit
    """

    mode = "ep"
    sub = (area_mode or "").strip().lower()
    if sub in ("suomi", "fi", "koko", "koko-suomi"):
        mode = "suomi"
    elif sub in ("mk",):
        mode = "seutu"
    elif sub in ("ep", "etelä-pohjanmaa", "etelapohjanmaa", "etela-pohjanmaa"):
        mode = "ep"
    elif sub in ("pohj", "pohjanmaa"):
        mode = "pohj"
    elif sub in ("kp", "keski-pohjanmaa", "keskipohjanmaa"):
        mode = "kp"
    elif sub in ("ks", "keski-suomi", "keskisuomi"):
        mode = "ks"
    elif sub in ("pirk", "pirkanmaa"):
        mode = "pirk"
    elif sub in ("sata", "satakunta"):
        mode = "sata"

    area_filter: Optional[str] = None

    if mode == "suomi":
        category_name = "VIIKKARIT_SUOMI"
        filename = "viikkarit_suomi.json"
    elif mode == "seutu":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
    elif mode == "pohj":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        area_filter = "Pohjanmaa"
    elif mode == "kp":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        area_filter = "Keski-Pohjanmaa"
    elif mode == "ks":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        area_filter = "Keski-Suomi"
    elif mode == "pirk":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        area_filter = "Pirkanmaa"
    elif mode == "sata":
        category_name = "VIIKKARIT_SEUTU"
        filename = "VIIKKARIT_SEUTU.json"
        area_filter = "Satakunta"
    else:
        category_name = "VIIKKOKISA"
        filename = "VIIKKOKISA.json"

    entries: List[Dict[str, Any]]
    if data_store is not None and hasattr(data_store, "load_category"):
        try:
            entries = data_store.load_category(category_name)  # type: ignore[assignment]
        except Exception:
            entries = []
    else:
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__) or "", ".."))
            path = os.path.join(base_dir, filename)
            import json

            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            entries = []

    if not entries:
        try:
            await message.channel.send(f"VIIKKOKISA-dataa ei löytynyt ({filename}).")
        except Exception:
            pass
        return

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)

    week_entries: List[Dict[str, Any]] = []

    for e in entries:
        kind = (e.get("kind") or "").upper()
        if "VIIKKOKISA" not in kind:
            continue

        if area_filter:
            entry_area = str(e.get("area") or "").strip()
            if not entry_area:
                continue
            if entry_area.lower() != area_filter.lower():
                continue

        d_raw = str(e.get("date") or "")
        loc_raw = str(e.get("location") or "")

        is_root = False
        txt = d_raw.strip()
        if " - " in txt:
            start_s, end_s = [p.strip() for p in txt.split(" - ", 1)]
            for fmts in (("%m/%d/%y", "%m/%d/%y"), ("%m/%d/%Y", "%m/%d/%Y")):
                try:
                    d1 = datetime.strptime(start_s, fmts[0]).date()
                    d2 = datetime.strptime(end_s, fmts[1]).date()
                    if (d2 - d1).days > 1:
                        is_root = True
                        break
                except Exception:
                    continue

        loc_l = loc_raw.lower()
        if "players:" in loc_l or "registration open" in loc_l:
            is_root = True

        if is_root:
            continue

        d_parsed = _parse_metrix_date(d_raw)
        if d_parsed is None:
            continue

        if week_start <= d_parsed < week_end:
            week_entries.append(e)

    if not week_entries:
        try:
            await message.channel.send("Tälle viikolle ei löytynyt viikkokisoja tuloksia varten.")
        except Exception:
            pass
        return

    # DEBUG: Näytetään perustiedot ennen hakusilmukkaa
    try:
        if DEBUG_TULOKSET:
            print(f"[DEBUG] _handle_weekly_viikkari_results mode={mode} area_filter={area_filter} filename={filename} entries_total={len(entries)} week_entries={len(week_entries)}")
            for i, we in enumerate(week_entries):
                try:
                    print(f"[DEBUG]  week_entry[{i}]: title={we.get('title')} url={we.get('url')}")
                except Exception:
                    continue
    except Exception:
        pass

    try:
        if hasattr(message.channel, "trigger_typing"):
            await message.channel.trigger_typing()
    except Exception:
        pass

    loop = asyncio.get_running_loop()

    lines: List[str] = []
    first_event = True

    # Do not send debug messages to Discord; keep console debug behind DEBUG_TULOKSET
    for e in sorted(week_entries, key=lambda x: str(x.get("date") or "")):
        title = str(e.get("title") or "")
        url_raw = str(e.get("url") or "")
        if not url_raw:
            continue

        url = _ensure_results_url(url_raw)

        def _do_fetch_one(u: str = url) -> Optional[Dict[str, Any]]:
            return _fetch_competition_results(u)

        result = await loop.run_in_executor(None, _do_fetch_one)
        if not result or not result.get("classes"):
            continue

        # DEBUG: Tulosta kilpailun ja luokkien nimet sekä rivit konsoliin (vain kun DEBUG_TULOKSET)
        if DEBUG_TULOKSET:
            print(f"[DEBUG] KILPAILU: {title} ({url})")
        # Tulostetaan luokkien tiedot vain konsoliin, jos DEBUG_TULOKSET on päällä
        for cls in result.get("classes", []):
            cname = str(cls.get("class_name") or "?")
            if DEBUG_TULOKSET:
                print(f"  [DEBUG]  LUOKKA: {cname}")
            rows = cls.get("rows", []) or []
            for r in rows:
                if DEBUG_TULOKSET:
                    print(f"    [DEBUG]   RIVI: {r}")

        event_lines = _format_top3_lines_for_result(result)
        if not event_lines:
            continue

        event_name = title or str(result.get("event_name") or "") or "(nimetön viikkari)"

        if not first_event:
            lines.append("")
        first_event = False
        lines.append(f"[{event_name}]({url})")
        lines.extend(event_lines)

    desc = "\n".join(lines) if lines else "Tälle viikolle ei löytynyt tulostettavia viikkarikisoja."

    try:
        Embed_cls = getattr(discord, "Embed", None) if discord is not None else None
        if Embed_cls:
            area_label = "Etelä-Pohjanmaa" if mode == "ep" else ("lähimaakunnat" if mode == "seutu" else "maakunnat")
            title = f"Tämän viikon viikkaritulokset – {area_label}"
            embed = Embed_cls(title=title, description=desc)
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(desc)
    except Exception:
        try:
            await message.channel.send(desc)
        except Exception:
            pass


async def handle_tulokset(message: Any, parts: Any) -> None:
    """Pääkomento "!tulokset".

        Alakomennot / muodot:
            !tulokset                         – tämän viikon viikkarikisojen Top3 Etelä-Pohjanmaalla
            !tulokset ep|mk|pohj|...          – viikon viikkarikisojen Top3 annetulla alueella
            !tulokset viikkari [ep|mk|...]    – alias yllä oleville (sama logiikka kuin !viikkarit)

            !tulokset kisa <Metrix-linkki tai ID>
            !tulokset viikkari <Metrix-linkki tai ID>
                                              – yksittäisen Metrix-kisan Top3 tulokset luokittain
    """

    # Ei lisäparametreja: tämän viikon viikkarit EP-alueella.
    if not parts or len(parts) < 2:
        await _handle_weekly_viikkari_results(message, "ep")
        return

    sub = str(parts[1] or "").strip().lower()

    # !tulokset kisa <linkki/ID> → yksittäisen kilpailun tulokset
    if sub in {"kisa", "k"}:
        if len(parts) < 3:
            try:
                await message.channel.send(
                    "Käyttö: !tulokset kisa <Metrix-linkki tai ID>\n"
                    "Esim: !tulokset kisa https://discgolfmetrix.com/3523248"
                )
            except Exception:
                pass
            return

        await _handle_single_viikkari_results(message, parts[2])
        return

    # !tulokset viikkari ... → viikkarikomennon alakentät
    if sub in {"viikkari", "viikkarit"}:
        # Jos ei jatkoargumentteja → tämän viikon viikkarit EP:llä.
        if len(parts) < 3:
            await _handle_weekly_viikkari_results(message, "ep")
            return

        # Seuraava sana on joko aluekoodi (mk, ep, ...) tai suora linkki/ID.
        next_arg = str(parts[2] or "").strip().lower()
        if next_arg in {"ep", "mk", "pohj", "kp", "ks", "pirk", "sata", "suomi", "fi", "koko", "koko-suomi"}:
            await _handle_weekly_viikkari_results(message, next_arg)
            return

        # Muussa tapauksessa käsitellään yksittäisen kisan linkkinä/ID:nä.
        await _handle_single_viikkari_results(message, parts[2])
        return

    # !tulokset mk → suoraan mk-alueen viikkaritulokset.
    if sub in {"ep", "mk", "pohj", "kp", "ks", "pirk", "sata", "suomi", "fi", "koko", "koko-suomi"}:
        await _handle_weekly_viikkari_results(message, sub)
        return

    # Viimeinen fallback: yritetään tulkita parametria yksittäisenä kisalinkkinä.
    await _handle_single_viikkari_results(message, parts[1])
