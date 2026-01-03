from typing import Any, Dict, Optional

try:
    from .data_store import load_category, save_category
except Exception:  # pragma: no cover - optional
    load_category = None  # type: ignore[assignment]
    save_category = None  # type: ignore[assignment]


PLAYERS_CATEGORY = "pelaaja"
LEGACY_PDGA_CATEGORY = "PDGA_USERS"


def _load_players_raw() -> Dict[str, Dict[str, Any]]:
    """Lataa kaikki pelaajamerkinnät pelaaja.json-tiedostosta.

    Rakenne on {"<discord_user_id>": {"pdga": "123", "metrix": "456"}}.
    Palauttaa tyhjän dictin, jos tiedostoa ei ole tai lataus epäonnistuu.

    Jos pelaaja.json on tyhjä, yritetään lukea legacy-PDGA_USERS-tiedostosta
    ja muuntaa merkinnät muotoon {id: {"pdga": number}}.
    """

    players: Dict[str, Dict[str, Any]] = {}

    if load_category is not None:
        data = load_category(PLAYERS_CATEGORY)
        if isinstance(data, dict):
            for user_id, entry in data.items():
                if isinstance(entry, dict):
                    players[str(user_id)] = {
                        str(k): (str(v) if isinstance(v, (int, str)) else v)
                        for k, v in entry.items()
                    }

        # Legacy-tuki: jos pelaaja.json ei sisältänyt mitään, yritetään lukea
        # vanha PDGA_USERS-rakenne ja konvertoida se.
        if not players:
            legacy = load_category(LEGACY_PDGA_CATEGORY)
            if isinstance(legacy, dict):
                for user_id, number in legacy.items():
                    num_str = str(number)
                    if num_str:
                        players[str(user_id)] = {"pdga": num_str}

    return players


def _save_players_raw(players: Dict[str, Dict[str, Any]]) -> None:
    """Tallenna koko pelaajakartta pelaaja.json-tiedostoon."""

    if save_category is None:
        return
    try:
        save_category(PLAYERS_CATEGORY, players)
    except Exception:
        # Tallennusvirheet eivät saa rikkoa komentoa
        pass


def get_player_entry(user_id: str) -> Dict[str, Any]:
    """Palauta yhden käyttäjän merkintä tai tyhjä dict, jos ei ole."""

    players = _load_players_raw()
    return players.get(str(user_id), {})


def get_pdga_for_user(user_id: str) -> Optional[str]:
    """Palauta käyttäjän PDGA-numero, jos tallennettu."""

    entry = get_player_entry(user_id)
    value = entry.get("pdga")
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def get_metrix_for_user(user_id: str) -> Optional[str]:
    """Palauta käyttäjän MetrixID, jos tallennettu."""

    entry = get_player_entry(user_id)
    value = entry.get("metrix")
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def set_pdga_for_user(user_id: str, pdga_number: str) -> None:
    """Aseta/ päivitä käyttäjän PDGA-numero pelaaja.json-tiedostoon."""

    players = _load_players_raw()
    uid = str(user_id)
    entry = players.get(uid, {})
    entry["pdga"] = str(pdga_number).strip()
    players[uid] = entry
    _save_players_raw(players)


def set_metrix_for_user(user_id: str, metrix_id: str) -> None:
    """Aseta/ päivitä käyttäjän MetrixID pelaaja.json-tiedostoon."""

    players = _load_players_raw()
    uid = str(user_id)
    entry = players.get(uid, {})
    entry["metrix"] = str(metrix_id).strip()
    players[uid] = entry
    _save_players_raw(players)
