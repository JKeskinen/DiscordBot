"""Help message builder for LakeusBotti.

Tarjoaa aihekohtaiset ohjeet komennolle ``!ohje``.
Pääohje näyttää vain ne kategoriat ja komennot, jotka ovat oikeasti käytössä:
Kiekot, Kilpailut ja Ratingit.
"""

from typing import Dict, Optional


BASE_TITLE = "Käyttöohje"


def _general_help_description() -> str:
    """Yleinen käyttöohje ilman tarkennusta ("!ohje")."""

    return (
        "LakeusBotti 1.0 \n\n"
  
        "🥏 Kiekot ja lentonumerot\n"
        "Hae PDGA:n hyväksymiä kiekkoja nimellä. Haku käyttää PDGA:n virallista listaa"
        "ja näyttää perustiedot yhdestä parhaasta osumasta.\n"
        "Komennot:\n"
        "• !kiekko\n\n"

        "Ratingit\n"
        "📊 Ratingit ja pelaajatiedot (PDGA & Metrix)\n"
        "Hae PDGA- ja Metrix-pelaajien rating- ja perustietoja numerolla.\n"
        "Komennot:\n"
        "• !pdga\n"
        "• !metrix\n\n"

        
        "🏆 Kilpailut\n"
        "Seuraa ja etsi kilpailuja sekä tarkista, missä paikkoja on vähän.\n"
        "Komennot:\n"
        "• !rek\n"
        "• !etsi\n"
        "• !paikat\n"
        "• !viikkarit ep | pohj | kp | ks | pirk | sata | mk | suomi\n\n"

        "📊 Tulospalvelu\n"
        "Näytä viikkarikisojen ja Metrix-kilpailujen tuloksia Top3-koosteina.\n"
        "Komennot:\n"
        "• !tulokset [ep|pohj|kp|ks|pirk|sata|mk|suomi]\n"
        "• !tulokset kisa <Metrix-linkki tai ID>\n"

        "\n"
        "🏅 SeuraRanking\n"
        "Seuraa seuran pelaajien menestystä: botin keräämät podium-sijoitukset ja top-tilastot.\n"
        "Komennot:\n"
        "• !seura ranking  — Näytä nykyinen top-lista (oletus top 10)\n"
        "• !seura <n>  — Näytä top n pelaajaa (esim. !seura 5)\n"

    )


def _bagit_help_description() -> str:
    return (
        "Bägit\n"
        "🎒 Bägit ja tilastot\n\n"
        "Rakenna ja hallitse omaa kiekkobägiäsi uusilla tilasto- ja visualisointitoiminnoilla!\n"
        "Näe bägisi koostumus, keskispeed, valmistajat ja kategoriajako.\n\n"
        "📊 Uudet tilastot: Keskispeed, kategoriajako, valmistajat\n"
        "🎨 Paremmat kuvat: Uudistettu bägikuva selkeämmällä esityksellä\n"
        "⚡ Automaattiset numerot: Lentonumerot haetaan tietokannasta\n"
        "🏷️ Kategoriointi: Automaattinen jako tyypin mukaan\n\n"
        "💡 Komennot: !bägi ja !bägikuva\n"
    )


def _kiekot_help_description() -> str:
    return (
        "Kiekot\n"
        "🥏 Kiekot ja lentonumerot\n\n"
        "Hae PDGA:n hyväksymiä kiekkoja nimellä. Haku käyttää PDGA:n virallista listaa\n"
        "ja näyttää perustiedot yhdestä parhaasta osumasta.\n\n"
        "🔍 Haku: tarkka, alku- ja osuma hakusanaan\n"
        "🖼️ Kiekon kuva: yritetään hakea PDGA-sivulta, jos saatavilla\n"
        "📊 Lentonumerot: yritetään hakea automaattisesti PDGA-tiedoista\n\n"
        "💡 Komento: !kiekko\n\n"
        "Komennot:\n!kiekko\n!paivita_lentonumerot\n"
    )


def _ratingit_help_description() -> str:
    return (
        "!pdga\n\n"
        "Linkitä PDGA-tilisi ja näe kattavat pelaajatiedot: rating-kehitys, "
        "kilpailutulokset, ansiot, sijainti ja profiilikuva.\n\n"
        "Käyttö:\n"
        "🏆 PDGA-komennot:\n\n"
        "Tietojen katselu:\n"
        "• !pdga - näytä omat PDGA-tiedot\n"
        "• !pdga @käyttäjä - näytä toisen käyttäjän tiedot\n\n"
        "Tilin linkitys:\n"
        "• !pdga [PDGA-numero] - linkitä oma PDGA-tili\n"
        "• !pdga poista - poista linkitys\n\n"
        "Näytettävät tiedot (tavoite):\n"
        "• Rating ja rating-kehitys (trendi)\n"
        "• Luokka ja jäsenyys\n"
        "• Kilpailut ja voitot\n"
        "• Sijainti ja ansiot\n"
        "• Toimitsijakoe-status\n"
        "• Global Masters Rank\n"
        "• Profiilikuva ja suora linkki\n\n"
        "💡 Vinkki: PDGA-numerosi löydät PDGA.com-profiilistasi\n"
    )


def _metrix_help_description() -> str:
    return (
        "!metrix\n\n"
        "Linkitä Metrix-tilisi ja seuraa omaa rating-kehitystä, "
        "kilpailumääriä ja parhaita kierroksia.\n\n"
        "Käyttö:\n"
        "📊 Metrix-komennot:\n\n"
        "Tietojen katselu:\n"
        "• !metrix - näytä omat Metrix-tiedot (käyttää tallennettua MetrixID:tä)\n"
        "• !metrix 12345 - näytä annetun MetrixID:n tiedot\n"
        "• !metrix https://discgolfmetrix.com/player/12345 - poimii ID:n linkistä\n\n"
        "Tilin linkitys:\n"
        "• !metrix lisää 12345 - tallenna oma MetrixID\n"
        "• !metrix poista - poista linkitys\n\n"
        "MetrixID löydät:\n"
        "• Metrix-profiilin URL:stä: discgolfmetrix.com/player/[ID]\n"
        "• Metrix-asetuksista: Asetukset → Integraatio → MetrixID\n\n"
        "Näytettävät tiedot:\n"
        "• Nykyinen rating ja muutos\n"
        "• Kilpailujen määrä ja viimeisin kilpailu\n"
        "• Paras kierros ja päivämäärä (course based rating)\n"
        "• Rating-historia värillisessä codeblockissa\n"
        "• Suora linkki Metrix-profiiliin\n"
    )


def _kilpailut_help_description() -> str:
    return (
        "Kilpailut\n"
        "🏆 Kilpailut ja muistutukset\n\n"
        "Seuraa ja etsi kilpailuja sekä tarkista, missä paikkoja on vähän.\n\n"
        "!rek — Näytä avoimet rekisteröinnit (PDGA / viikkokisat).\n"
        "!etsi <hakusana> — Etsi kilpailuja nimen, alueen tai radan mukaan.\n"
        "!paikat — Näytä kilpailut, joissa on vähän paikkoja jäljellä.\n"
        "!viikkarit [ep|pohj|kp|ks|pirk|sata|mk|suomi] — Tämän viikon viikkokisat (maakunnittain, lähimaakunnissa tai koko Suomi).\n\n"
        "Tulospalvelu-komennot on kuvattu erikseen: !ohje tulospalvelu.\n\n"
        "Lyhenteet: ep = Etelä-Pohjanmaa, pohj = Pohjanmaa, kp = Keski-Pohjanmaa, ks = Keski-Suomi, pirk = Pirkanmaa, sata = Satakunta, mk = lähimaakunnat (EP + naapurit).\n\n"
        "Komennot:\n!rek\n!etsi\n!paikat\n!viikkarit\n"
    )


def _pelit_help_description() -> str:
    return (
        "Pelit\n"
        "🎮 Pelit ja kilpailut\n\n"
        "Osallistu friba-aiheisiin peleihin ja ansaitse XP:tä!\n"
        "Pelijärjestelmä tarjoaa erilaisia kilpailuja ja haasteita käyttäen oikeita kiekko-, bägi- ja ratatietoja.\n\n"
        "🏆 Palkinnat: Ansaitse XP:tä osallistumisesta ja voitoista\n"
        "📊 Tilastot: Leaderboard ja parhaat tulokset\n\n"
        "💡 Komennot: Katso !ohje pelit lisätiedoille\n\n"
        "Komennot:\n!peli\n!top20\n!top10\n!kiekkovisa\n!admin\n"
    )


def _tulospalvelu_help_description() -> str:
    return (
        "Tulospalvelu\n"
        "📊 Viikkareiden tulokset\n\n"
        "Näytä viikkareiden koontitulokset ja yksittäisten Metrix-kisojen Top3-tulokset luokittain.\n\n"
        "Viikkarikisojen tulokset (viikon kooste):\n"
        "!tulokset [ep|pohj|kp|ks|pirk|sata|mk|suomi] — Tämän viikon viikkarikisojen Top3-tulokset alueittain.\n\n"
        "Lyhenteet: ep = Etelä-Pohjanmaa, pohj = Pohjanmaa, kp = Keski-Pohjanmaa, ks = Keski-Suomi, pirk = Pirkanmaa, sata = Satakunta, mk = lähimaakunnat (EP + naapurit), suomi = koko Suomi.\n"
    )


def _pelaajaranking_help_description() -> str:
    return (
        "PelaajaRanking\n"
        "🏅 Seuran kovimmat menestyjät\n\n"
        "Botti kirjaa automaattisesti Lakeus Disc Golf -seuran pelaajien Top3-sijoituksia\n"
        "ja säilyttää ne tiedostossa `komento_koodit/club_successes.json`.\n\n"
        "Miten nähdä menestyjät nyt:\n"
        "• Käynnistä `!tulokset` (yksittäinen kilpailu tai viikkari) — botti ilmoittaa löydöistä automaattisesti.\n"
        "  Onnitteluviesti on lyhyt: ensimmäisellä rivillä kilpailun nimi ja linkki,\n"
        "  sen alla sijoitusrivit (esim. '1) Etunimi Sukunimi -3 (53)').\n"
        "  Botti suosii raakatuloksia ennen tasoitettuja (HC)-rivejä,\n"
        "  huomioi tasapelit (kaikki sijalla 3 listataan) ja ohittaa Sum==0 (DNS)-rivit.\n"
        "• Katso kertynyt lista suoraan tiedostosta: `komento_koodit/club_successes.json`.\n"
        "• Dev-työkaluina on myös `scripts/simulate_tulokset_3523248.py` ja `scripts/simulate_force_detect_23665.py`,\n"
        "  jotka voivat näyttää ja päivittää `club_successes.json` testitarkoituksia varten.\n\n"
        "Tulevaisuudessa voidaan lisätä suora komentorakenne (esim. `!seura menestys`),\n"
        "jolla haetaan ja järjestetään top-pelaajat suoraan botin kautta."
    )


    def _seuraranking_help_description() -> str:
        return (
            "SeuraRanking\n"
            "🏆 Seuran menestys ja ranking\n\n"
            "Botti kerää ja ylläpitää seuran pelaajien top-sijoituksia ja muita seurantamittareita\n"
            "tiedostossa `komento_koodit/club_successes.json` ja muissa lokitiedoissa."
            "\n\n"
            "Miten käyttää:\n"
            "• !seura ranking - Näytä nykyinen top-lista seuran menestyjistä (esim. top-pelaajat ja sijoitukset)\n"
            "• !seura menestys - Yhteenveto kauden onnistumisista ja podium-sijoituksista\n"
            "• !seura päivitä - (admin) Päivitä club_successes.json historiasta tai simulaatiolla\n\n"
            "Missä data tulee:\n"
            "• Automaattilöydöt !tulokset-ajosta: botti tunnistaa seurapelaajat ja kirjaa Top3-sijoituksia\n"
            "• Manuaalinen ylläpito: tiedoston muokkaus tai dev-skriptit `scripts/`-hakemistossa\n\n"
            "Tulevaisuuden ideat:\n"
            "• Komentoja suodattamiseen (kausi, luokka, kategoria)\n"
            "• Pysyvä leaderboard Discordiin upotettuna\n"
        )


def get_help_message(topic: Optional[str] = None) -> Dict[str, str]:
    """Palauta otsikko- ja kuvausteksti annetulle ohjeaiheelle.

    ``topic`` tulee komennosta, esim. ``!ohje kiekot`` tai ``!ohje bägit``.
    Jos aihe on tyhjä tai tuntematon, palautetaan yleinen käyttöohje.
    """

    normalized = (topic or "").strip().lower()

    # Sallitaan sekä ääkköset että ilman ääkkösiä kirjoitetut muodot
    if normalized in {"kiekko", "kiekot"}:
        return {"title": BASE_TITLE, "description": _kiekot_help_description()}

    if normalized in {"pdga"}:
        return {"title": "!pdga", "description": _ratingit_help_description()}

    if normalized in {"metrix"}:
        return {"title": "!metrix", "description": _metrix_help_description()}

    if normalized in {"kisa", "kisat", "kilpailu", "kilpailut", "rek", "spots", "paikat", "etsi", "viikkari", "viikkarit"}:
        return {"title": BASE_TITLE, "description": _kilpailut_help_description()}

    if normalized in {"tulokset", "tulospalvelu"}:
        return {"title": BASE_TITLE, "description": _tulospalvelu_help_description()}

    if normalized in {"pelaajaranking", "pelaaja ranking", "ranking", "seuramenestys", "menestys", "menestyjät"}:
        return {"title": "PelaajaRanking", "description": _pelaajaranking_help_description()}

        if normalized in {"seuraranking", "seura ranking", "seura", "seuran", "seura menestys", "seura_ranking"}:
            return {"title": "SeuraRanking", "description": _seuraranking_help_description()}

    return {"title": BASE_TITLE, "description": _general_help_description()}
