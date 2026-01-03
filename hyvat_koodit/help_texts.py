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
        "• !spots\n"
        "• !paikat\n"
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
        "!spots / !paikat — Näytä kilpailut, joissa on vähän paikkoja jäljellä.\n\n"
        "Komennot:\n!rek\n!etsi\n!spots\n!paikat\n"
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

    if normalized in {"kisa", "kisat", "kilpailu", "kilpailut", "rek", "spots", "paikat", "etsi"}:
        return {"title": BASE_TITLE, "description": _kilpailut_help_description()}

    return {"title": BASE_TITLE, "description": _general_help_description()}
