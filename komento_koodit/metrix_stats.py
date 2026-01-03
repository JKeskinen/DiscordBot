import os
import re
import html
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Tuple

import requests


BASE_ROOT_URL = "https://discgolfmetrix.com"
BASE_PLAYER_URL = f"{BASE_ROOT_URL}/player/"


@dataclass
class RatingEntry:
    date: Optional[str]
    round_rating: Optional[float]
    course_rating: Optional[float] = None
    calc_rating: Optional[float] = None
    competition: Optional[str] = None


@dataclass
class RatingPoint:
    """Yksittäinen piste Metrix rating -käyrältä (oranssi viiva)."""

    date: Optional[str]
    rating: Optional[float]
    label: Optional[str] = None


@dataclass
class PlayerStats:
    """Yksinkertainen tietorakenne Metrix-pelaajan statseille.

    Huom: Kaikkia kenttiä ei välttämättä saada parsittua; tällöin ne ovat None.
    """

    metrix_id: str
    profile_url: str
    name: Optional[str] = None
    rating: Optional[float] = None
    rating_change: Optional[float] = None
    competitions_count: Optional[int] = None
    last_competition_date: Optional[str] = None
    best_round_rating: Optional[float] = None
    best_round_date: Optional[str] = None
    rating_history: List[RatingEntry] = field(default_factory=list)
    # Arvio kaikkien Metrix-kierrosten määrästä (aktiivisuusgraafin perusteella).
    total_rounds: Optional[int] = None
    # Paras peli course based rating -käyrän (vihreä jana) perusteella.
    best_course_rating: Optional[float] = None
    best_course_date: Optional[str] = None
    # Metrix rating -käyrän (oranssi viiva) pisteet aikajärjestyksessä.
    rating_curve: List[RatingPoint] = field(default_factory=list)


def _create_session() -> Optional[requests.Session]:
    """Luo sisäänkirjautuneen session Metrixiin.

    Vaihtoehdot:
    - METRIX_COOKIE: koko selaimen Cookie-header Metrixistä (varmin tapa)
    - METRIX_EMAIL + METRIX_PASSWORD: yritetään kirjautua lomakkeen kautta

    Palauttaa None, jos kirjautuminen ei onnistu.
    """

    session = requests.Session()
    session.headers.update({
        "User-Agent": os.environ.get(
            "METRIX_USER_AGENT",
            "Mozilla/5.0 (compatible; MetrixDiscordBot/1.0)",
        )
    })

    cookie = os.environ.get("METRIX_COOKIE", "").strip()
    if cookie:
        # Käytä annettua cookiea sellaisenaan.
        session.headers["Cookie"] = cookie
        return session

    email = os.environ.get("METRIX_EMAIL") or os.environ.get("METRIX_USER")
    password = os.environ.get("METRIX_PASSWORD")
    if not email or not password:
        # Ei kirjautumistietoja
        return None

    login_url = os.environ.get("METRIX_LOGIN_URL", "https://discgolfmetrix.com/?u=login")

    # Lomakekenttien nimet voivat muuttua; tämä on paras arvaus.
    payload = {
        "email": email,
        "password": password,
    }

    try:
        resp = session.post(login_url, data=payload, timeout=20)
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    # Tässä ei ole varmaa tapaa tunnistaa kirjautumisen onnistumista
    # ilman tarkkaa HTML:ää. Luotetaan siihen, että cookie tallentui,
    # ja mahdollinen epäonnistuminen näkyy myöhemmin stats-haussa.
    return session


def _strip_tags(value: str) -> str:
    """Poista HTML-tagit ja dekoodaa entiteetit yksinkertaisesti."""

    # Poistetaan kaikki tagit
    text = re.sub(r"<[^>]+>", "", value)
    return html.unescape(text).strip()


def _parse_player_stats(html_text: str, metrix_id: str) -> PlayerStats:
    """Yritä parsia oleellisimmat kentät pelaajasivun HTML:stä.

        Hyödynnetään Metrix_juho.html -rakennetta:
        - Nimi:   <div class="profile-name"><h1>...</h1>
        - Rating: <div class="metrix-rating"><span>898</span><label>Metrix rating</label></div>
        - Viimeisin rating-analyysi: taulukko otsikolla "Metrix-ratingin analyysi" tai
            vanhemmissa versioissa "Viimeisin Metrix rating analyysi".
    """

    profile_url = f"{BASE_PLAYER_URL}{metrix_id}"
    stats = PlayerStats(metrix_id=metrix_id, profile_url=profile_url)

    # Pelaajan nimi: ensisijaisesti profile-name/h1, varalla <title>
    m_name = re.search(
        r"<div\s+class=\"profile-name\"[^>]*>.*?<h1>(.*?)</h1>",
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m_name:
        stats.name = _strip_tags(m_name.group(1))
    else:
        m_title = re.search(r"<title>([^<]+)</title>", html_text, re.IGNORECASE)
        if m_title:
            title_text = html.unescape(m_title.group(1)).strip()
            stats.name = title_text

    # Metrix rating: haetaan ensisijaisesti metrix-rating -divistä
    m_rating_div = re.search(
        r"<div\s+class=\"metrix-rating\"[^>]*>\s*<span>([0-9]{3,4}(?:\.[0-9]+)?)</span>",
        html_text,
        re.IGNORECASE,
    )
    if m_rating_div:
        try:
            stats.rating = float(m_rating_div.group(1))
        except Exception:
            pass
    else:
        # Fallback: vanha tekstipohjainen heuristiikka (vain rating, EI muutosta)
        m_rating = re.search(
            r"Metrix\s*rating[^0-9]*([0-9]{3,4}(?:\.[0-9]+)?)",
            html_text,
            re.IGNORECASE,
        )
        if m_rating:
            try:
                stats.rating = float(m_rating.group(1))
            except Exception:
                pass

    # Vaihtoehtoinen rating-lähde: mystat-näkymän linkki \"id=rating\"
    if stats.rating is None:
        m_rating_id = re.search(
            r"<a[^>]*id=\"rating\"[^>]*>\s*([0-9]{3,4}(?:\.[0-9]+)?)\s*</a>",
            html_text,
            re.IGNORECASE,
        )
        if m_rating_id:
            try:
                stats.rating = float(m_rating_id.group(1))
            except Exception:
                pass

    # Rating-muutos: AINOASTAAN mystat-/etusivun span id="rating_change" -elementistä.
    # HTML voi olla joko "<span id=...>6<small> pisteet</small>" tai
    # "<span id=...><small> 6 pisteet</small>", joten haetaan numero
    # mistä tahansa spanin sisäisestä tekstistä.
    if stats.rating_change is None:
        m_change_id = re.search(
            r"<span[^>]*id=\"rating_change\"[^>]*>.*?([+\-]?\d+(?:\.\d+)?)[^0-9]*</span>",
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        if m_change_id:
            try:
                stats.rating_change = float(m_change_id.group(1))
            except Exception:
                pass

    # Metrix rating -analyysitaulukko
    # Käytetään tätä kilpailujen määrään, viimeisimpään kisaan ja parhaaseen kierrokseen.
    #
    # Uudemmalla sivupohjalla otsikko on "Metrix-ratingin analyysi";
    # vanhemmissa versioissa "Viimeisin Metrix rating analyysi".
    heading_idx = html_text.find("Metrix-ratingin analyysi")
    if heading_idx == -1:
        heading_idx = html_text.find("Viimeisin Metrix rating analyysi")
    tbody_html: Optional[str] = None

    # Ensisijainen: otsikon "Viimeisin Metrix rating analyysi" jälkeen tuleva taulukko
    if heading_idx != -1:
        sub = html_text[heading_idx:]
        m_tbody = re.search(r"<tbody>(.*?)</tbody>", sub, re.IGNORECASE | re.DOTALL)
        if m_tbody:
            tbody_html = m_tbody.group(1)

    # Varasuunnitelma: etsitään suoraan taulukko, jossa on Metrix-rating -otsikko
    if tbody_html is None:
        m_tbody2 = re.search(
            r"Metrix[-\s]*rating(?:in)?\s+analyysi.*?<tbody>(.*?)</tbody>",
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        if m_tbody2:
            tbody_html = m_tbody2.group(1)

    if tbody_html is not None:
        rows = re.findall(r"<tr>(.*?)</tr>", tbody_html, re.IGNORECASE | re.DOTALL)

        best_rating: Optional[float] = None
        best_date: Optional[str] = None
        history: List[RatingEntry] = []
        competitions = 0

        for row_html in rows:
            # Taulukon viimeinen rivi on yhteenvetorivi, jossa on class="total";
            # sitä ei pidä laskea yksittäiseksi kierrokseksi tai historiariviksi.
            if "class=\"total\"" in row_html or "class='total'" in row_html:
                continue

            cols: List[str] = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.IGNORECASE | re.DOTALL)
            if len(cols) < 3:
                continue

            date_str = _strip_tags(cols[2])

            competitions += 1
            if competitions == 1 and date_str:
                stats.last_competition_date = date_str

            rating_candidates: List[float] = []
            course_rating: Optional[float] = None
            calc_rating: Optional[float] = None

            if len(cols) >= 7:
                cr = _strip_tags(cols[6])
                try:
                    course_rating = float(cr.replace(",", "."))
                    rating_candidates.append(course_rating)
                except Exception:
                    course_rating = None

            if len(cols) >= 9:
                lr = _strip_tags(cols[8])
                try:
                    calc_rating = float(lr.replace(",", "."))
                    rating_candidates.append(calc_rating)
                except Exception:
                    calc_rating = None

            if not rating_candidates:
                continue

            candidate = max(rating_candidates)
            if best_rating is None or candidate > best_rating:
                best_rating = candidate
                best_date = date_str

            competition_name: Optional[str] = None
            if cols:
                competition_name = _strip_tags(cols[0]) or None

            history.append(
                RatingEntry(
                    date=date_str or None,
                    round_rating=candidate,
                    course_rating=course_rating,
                    calc_rating=calc_rating,
                    competition=competition_name,
                )
            )

        if competitions > 0:
            stats.competitions_count = competitions

        # Jos kilpailujen kokonaismäärä ei syystä tai toisesta asettunut,
        # päätellään se historiarivien lukumäärästä.
        if stats.competitions_count is None and history:
            stats.competitions_count = len(history)

        if best_rating is not None:
            stats.best_round_rating = best_rating
            stats.best_round_date = best_date

        stats.rating_history = history

    # Vaihtoehtoinen/parantava lähde parhaalle kierrokselle:
    # "Omat 5 parasta kierrosta" -boksi (data-section="best_rounds").
    # Tästä löytyy taulukko, jossa on kilpailun pvm (span.competition-date)
    # ja rating viimeisessä sarakkeessa.

    best_rating_br: Optional[float] = None
    best_date_br: Optional[str] = None

    best_idx = html_text.find("data-section=\"best_rounds\"")
    if best_idx != -1:
        sub_br = html_text[best_idx:]
        m_tbody_br = re.search(r"<tbody>(.*?)</tbody>", sub_br, re.IGNORECASE | re.DOTALL)
        if m_tbody_br:
            tbody_br = m_tbody_br.group(1)
            rows_br = re.findall(r"<tr>(.*?)</tr>", tbody_br, re.IGNORECASE | re.DOTALL)
            for row_html in rows_br:
                cols_br: List[str] = re.findall(
                    r"<td[^>]*>(.*?)</td>", row_html, re.IGNORECASE | re.DOTALL
                )
                if len(cols_br) < 2:
                    continue

                # Rating on yleensä viimeisessä sarakkeessa
                rating_str = _strip_tags(cols_br[-1])
                try:
                    rating_val = float(rating_str.replace(",", "."))
                except Exception:
                    continue

                # Päivämäärä löytyy span.competition-date -elementistä
                m_date = re.search(
                    r"class=\"competition-date\"[^>]*>(.*?)</span>",
                    row_html,
                    re.IGNORECASE | re.DOTALL,
                )
                date_val: Optional[str] = None
                if m_date:
                    date_val = _strip_tags(m_date.group(1))

                if best_rating_br is None or rating_val > best_rating_br:
                    best_rating_br = rating_val
                    best_date_br = date_val

    if best_rating_br is not None:
        # Käytä "Omat 5 parasta kierrosta" -tietoa, jos se on parempi tai
        # jos aiempaa arvoa ei ole.
        if stats.best_round_rating is None or best_rating_br > stats.best_round_rating:
            stats.best_round_rating = best_rating_br
            stats.best_round_date = best_date_br

    return stats


def _fetch_total_rounds(session: requests.Session, metrix_id: str) -> Optional[int]:
    """Hae arvio kaikkien Metrix-kierrosten määrästä.

    Pelaajasivun "Pelaamisaktiivisuus"-graafi käyttää JSON-endpointtia
    player_stat_activity_server.php?UserID=<id>. Vastauksena tulee suoraan
    Highchartsin "series"-lista, jossa jokaisella sarjalla on nimi ja data.

    Oletus:
      - Sarjan nimi, jossa on "all" tai "kaikki" (esim. "Kaikki data"),
        sisältää koko historian kuukausikohtaiset kierrosmäärät.
      - Sarjan data on lista pisteistä, joissa arvo on joko
        - suoraan numero, tai
        - [x, y] (kuten Highchartsin aikasarjoissa), missä y on määrä.

    Palauttaa summan näistä arvoista tai None, jos dataa ei saada järkevästi
    tulkittua.
    """

    url = f"{BASE_ROOT_URL}/player_stat_activity_server.php?UserID={metrix_id}"
    try:
        resp = session.get(url, timeout=20)
    except Exception:
        return None

    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    if not isinstance(data, list):
        return None

    total_all: Optional[int] = None
    best_series_sum = 0

    for series in data:
        if not isinstance(series, dict):
            continue

        name = str(series.get("name") or "").lower()
        points = series.get("data")
        if not isinstance(points, list):
            continue

        series_sum = 0
        for point in points:
            y_val: Optional[float] = None
            if isinstance(point, (int, float)):
                y_val = float(point)
            elif isinstance(point, (list, tuple)) and len(point) >= 2 and isinstance(point[1], (int, float)):
                y_val = float(point[1])

            if isinstance(y_val, float):
                series_sum += int(round(y_val))

        if series_sum <= 0:
            continue

        # Ensisijaisesti käytetään sarjaa, jonka nimi viittaa kaikkiin datoihin.
        if "all" in name or "kaikki" in name:
            total_all = series_sum

        if series_sum > best_series_sum:
            best_series_sum = series_sum

    if total_all is not None:
        return total_all

    if best_series_sum > 0:
        return best_series_sum

    return None


def _fetch_rating_curve(
    session: requests.Session, metrix_id: str
) -> Tuple[List[RatingPoint], Optional[float], Optional[str], Optional[int]]:
    """Hae Metrix rating -käyrän (oranssi viiva) pisteet.

    Pelaajasivun "Ratingit"-graafi käyttää JSON-endpointtia
    mystat_server_rating.php?user_id=<id>&other=1&course_id=0.

    Paluuarvo on list[str, float, str?] -rakenteita:
      - [0] = aikaleima millisekunteina (Unix epoch)
      - [1] = rating-arvo
      - [2] = tooltip-teksti (esim. "2024-8-7 18:00 ...")

    Highcharts-koodi muodostaa näistä kolme sarjaa:
      - data[0] → Quick rating (sininen)
      - data[2] → Course based rating (vihreä)
      - data[1] → Metrix rating (oranssi)

    Tässä palautetaan vain Metrix rating -sarja (data[1]) muunnettuna
    RatingPoint-olioiksi. Jos JSONia ei saada tai rakenne ei vastaa
    odotuksia, palautetaan tyhjä lista.
    """

    url = f"{BASE_ROOT_URL}/mystat_server_rating.php?user_id={metrix_id}&other=1&course_id=0"
    try:
        resp = session.get(url, timeout=20)
    except Exception:
        return [], None, None, None

    if resp.status_code != 200:
        return [], None, None, None

    try:
        data = resp.json()
    except Exception:
        return [], None, None, None

    if not isinstance(data, list) or len(data) < 2:
        return [], None, None, None

    # Quick rating (sininen viiva) oletetaan olevan data[0]
    quick_len: Optional[int] = None
    try:
        if isinstance(data[0], list):
            quick_len = len(data[0])
    except Exception:
        quick_len = None

    # Metrix rating (oranssi viiva) oletetaan olevan data[1]
    series = data[1]
    if not isinstance(series, list):
        return [], None, None, quick_len

    points: List[RatingPoint] = []

    for item in series:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue

        ts_raw = item[0]
        val_raw = item[1]
        label_raw = item[2] if len(item) >= 3 else None

        try:
            rating_val = float(val_raw)
        except Exception:
            continue

        date_str: Optional[str] = None
        try:
            if isinstance(ts_raw, (int, float)):
                dt = datetime.fromtimestamp(float(ts_raw) / 1000.0)
                date_str = dt.strftime("%d.%m.%Y")
        except Exception:
            date_str = None

        label: Optional[str] = None
        if isinstance(label_raw, str) and label_raw.strip():
            label = label_raw.strip()

        points.append(RatingPoint(date=date_str, rating=rating_val, label=label))

    # Course based rating (vihreä jana) oletetaan olevan data[2]
    best_course_rating: Optional[float] = None
    best_course_date: Optional[str] = None

    if len(data) >= 3 and isinstance(data[2], list):
        for item in data[2]:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue

            ts_raw = item[0]
            val_raw = item[1]
            try:
                rating_val = float(val_raw)
            except Exception:
                continue

            if best_course_rating is None or rating_val > best_course_rating:
                date_str: Optional[str] = None
                try:
                    if isinstance(ts_raw, (int, float)):
                        dt = datetime.fromtimestamp(float(ts_raw) / 1000.0)
                        date_str = dt.strftime("%d.%m.%Y")
                except Exception:
                    date_str = None

                best_course_rating = rating_val
                best_course_date = date_str

    return points, best_course_rating, best_course_date, quick_len


def fetch_player_stats(metrix_id: str) -> Optional[PlayerStats]:
    """Hae Metrix-pelaajan statsit.

    Päälogiikka:
    - Haetaan aina pelaajasivu /player/<id> ja parsitaan sieltä nimi,
      rating, kisat ja paras kierros.
        - Optionaalisesti (vain omalle ID:lle) haetaan lisäksi:
            - etusivu ja sieltä tarkka rating sekä rating-muutos id="rating"/"rating_change" -elementeistä
            - "Omat 5 parasta kierrosta" -lista AJAX-endpointista main_server.php?section=best_rounds
            - Metrix rating -käyrä (oranssi viiva) mystat_server_rating.php-JSONista.

    Palauttaa PlayerStats tai None, jos haku epäonnistuu tai kirjautuminen ei
    onnistu.
    """

    if not metrix_id:
        return None

    session = _create_session()
    if session is None:
        return None

    # 1) Haetaan AINA pelaajasivu tälle MetrixID:lle.
    try:
        player_resp = session.get(f"{BASE_PLAYER_URL}{metrix_id}", timeout=20)
    except Exception:
        return None

    if player_resp.status_code != 200 or not player_resp.text:
        return None

    # Debug HTML voidaan haluttaessa ottaa käyttöön asettamalla
    # METRIX_DEBUG_HTML=1 ympäristömuuttujaan.
    if os.environ.get("METRIX_DEBUG_HTML", "").strip():
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__) or "", ".."))
            debug_path_player = os.path.join(base_dir, f"Metrix_player_{metrix_id}_debug.html")
            with open(debug_path_player, "w", encoding="utf-8") as f_dbg:
                f_dbg.write(player_resp.text)
        except Exception:
            pass

    stats = _parse_player_stats(player_resp.text, metrix_id)

    # 2) Voidaan erotella oma ID ja muiden ID:t lisäparannuksia varten.
    # Omalle ID:lle (METRIX_OWN_ID) täydennetään lisäksi rating ja rating-muutos
    # etusivulta sekä "Omat 5 parasta kierrosta" -lista.
    own_id = os.environ.get("METRIX_OWN_ID", "").strip()

    # 3) Täydennetään OMALLE ID:lle rating ja rating-muutos etusivulta ja
    # sieltä ladattavasta mystat-metrix-rating -osiosta.
    if own_id and own_id == metrix_id:
        try:
            front_resp = session.get(BASE_ROOT_URL, timeout=20)
        except Exception:
            front_resp = None

        if front_resp is not None and front_resp.status_code == 200 and front_resp.text:
            # Debug: tallenna etusivun HTML erilliseen tiedostoon vain, jos
            # METRIX_DEBUG_HTML on asetettu.
            if os.environ.get("METRIX_DEBUG_HTML", "").strip():
                try:
                    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__) or "", ".."))
                    debug_path_front = os.path.join(base_dir, "Metrix_front_debug.html")
                    with open(debug_path_front, "w", encoding="utf-8") as f_dbg:
                        f_dbg.write(front_resp.text)
                except Exception:
                    pass

            front_stats = _parse_player_stats(front_resp.text, metrix_id)

            if front_stats.rating is not None:
                stats.rating = front_stats.rating
            if front_stats.rating_change is not None:
                stats.rating_change = front_stats.rating_change

            # Yritä hakea "Omat 5 parasta kierrosta" -lista erillisellä kutsulla,
            # koska etusivulla se ladataan AJAXilla (data-section="best_rounds").
            try:
                br_resp = session.get(f"{BASE_ROOT_URL}/main_server.php?section=best_rounds", timeout=20)
            except Exception:
                br_resp = None

            if br_resp is not None and br_resp.status_code == 200 and br_resp.text:
                html_br = br_resp.text
                best_rating_br: Optional[float] = None
                best_date_br: Optional[str] = None

                m_tbody_br = re.search(r"<tbody>(.*?)</tbody>", html_br, re.IGNORECASE | re.DOTALL)
                if m_tbody_br:
                    tbody_br = m_tbody_br.group(1)
                    rows_br = re.findall(r"<tr>(.*?)</tr>", tbody_br, re.IGNORECASE | re.DOTALL)
                    for row_html in rows_br:
                        cols_br: List[str] = re.findall(
                            r"<td[^>]*>(.*?)</td>", row_html, re.IGNORECASE | re.DOTALL
                        )
                        if len(cols_br) < 2:
                            continue

                        # Rating on yleensä viimeisessä sarakkeessa
                        rating_str = _strip_tags(cols_br[-1])
                        try:
                            rating_val = float(rating_str.replace(",", "."))
                        except Exception:
                            continue

                        # Päivämäärä löytyy span.competition-date -elementistä, jos sellainen on
                        m_date = re.search(
                            r"class=\"competition-date\"[^>]*>(.*?)</span>",
                            row_html,
                            re.IGNORECASE | re.DOTALL,
                        )
                        date_val: Optional[str] = None
                        if m_date:
                            date_val = _strip_tags(m_date.group(1))

                        if best_rating_br is None or rating_val > best_rating_br:
                            best_rating_br = rating_val
                            best_date_br = date_val

                if best_rating_br is not None:
                    if stats.best_round_rating is None or best_rating_br > stats.best_round_rating:
                        stats.best_round_rating = best_rating_br
                        stats.best_round_date = best_date_br

    # 4) Hae pelaamisaktiivisuudesta arvio kaikkien Metrix-kierrosten määrästä.
    try:
        total_rounds = _fetch_total_rounds(session, metrix_id)
    except Exception:
        total_rounds = None
    if total_rounds is not None:
        stats.total_rounds = total_rounds

    # 5) Hae Metrix rating -käyrä (oranssi viiva), Quick rating -sarjan
    # (sininen viiva) pituus ja paras course based rating -peli (vihreä jana)
    # mystat_server_rating-JSONista.
    try:
        curve, best_course_rating, best_course_date, quick_series_len = _fetch_rating_curve(session, metrix_id)
    except Exception:
        curve = []
        best_course_rating = None
        best_course_date = None
        quick_series_len = None
    if curve:
        stats.rating_curve = curve

    if best_course_rating is not None:
        stats.best_course_rating = best_course_rating
        stats.best_course_date = best_course_date

    # Jos Quick rating -sarjan (sininen viiva) pituus on suurempi kuin
    # aiemmin analyysitaulukosta päätelty competitions_count, käytä sitä
    # kaikkien kisojen määränä.
    if isinstance(locals().get("quick_series_len"), int):
        try:
            qlen = int(quick_series_len)  # type: ignore[arg-type]
            if qlen > 0:
                if not isinstance(stats.competitions_count, int) or stats.competitions_count < qlen:
                    stats.competitions_count = qlen
        except Exception:
            pass

    # 6) Johda rating ja rating-muutos suoraan oranssin Metrix rating -käyrän
    # kahdesta viimeisestä pisteestä, jos mahdollista. Kilpailujen lukumäärä
    # otetaan nyt sinisestä Quick rating -sarjasta (quick_series_len), ei
    # oranssin käyrän pisteiden lukumäärästä.
    if stats.rating_curve:
        curve_all = list(stats.rating_curve)

        last_pt = curve_all[-1]
        if getattr(last_pt, "rating", None) is not None:
            try:
                stats.rating = float(last_pt.rating)  # type: ignore[arg-type]
            except Exception:
                pass

        if len(curve_all) >= 2:
            prev_pt = curve_all[-2]
            if (
                getattr(last_pt, "rating", None) is not None
                and getattr(prev_pt, "rating", None) is not None
            ):
                try:
                    stats.rating_change = float(last_pt.rating) - float(prev_pt.rating)  # type: ignore[arg-type]
                except Exception:
                    pass

    return stats
