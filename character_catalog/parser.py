from collections.abc import Mapping

from .model import ID_PATTERN, Character, CharacterFeature


ARTWORK = "https://raw.githubusercontent.com/genshindev/api/mistress/assets/images/characters"


def parse_character_ids(payload: object) -> list[str]:
    """Normalize the character index returned by the HTTP adapter."""
    if not isinstance(payload, list) or not payload or not all(
        isinstance(code, str) and ID_PATTERN.fullmatch(code) for code in payload
    ):
        raise ValueError("Очікується непорожній список кодів персонажів.")
    return sorted(set(payload))


def parse_character(code: str, payload: object) -> Character:
    """Map decoded Genshin JSON to the catalog's typed character model."""
    if not ID_PATTERN.fullmatch(code):
        raise ValueError("Некоректний код віддаленого персонажа.")
    if not isinstance(payload, Mapping):
        raise ValueError("Очікується JSON-об’єкт картки.")
    return Character(
        id=code,
        name=_text(payload, "name"),
        description=_text(payload, "description") or "Опис відсутній.",
        image_url=f"{ARTWORK}/{code}/card",
        element=_text(payload, "vision"),
        nation=_text(payload, "nation"),
        weapon=_text(payload, "weapon"),
        rarity=_positive_int(payload, "rarity"),
        title=_text(payload, "title"),
        affiliation=_text(payload, "affiliation"),
        birthday=_text(payload, "birthday"),
        skills=_features(payload, "skillTalents"),
        passives=_features(payload, "passiveTalents"),
        constellations=_features(payload, "constellations"),
    )


def _text(record: Mapping, field: str) -> str:
    value = record.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Поле {field} має бути рядком.")
    return value.strip()


def _positive_int(record: Mapping, field: str) -> int | None:
    value = record.get(field)
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        value = int(value)
    if type(value) is not int or value < 1:
        raise ValueError(f"Поле {field} має бути додатним цілим числом.")
    return value


def _features(record: Mapping, field: str) -> tuple[CharacterFeature, ...]:
    entries = record.get(field)
    if entries is None:
        return ()
    if not isinstance(entries, list):
        raise ValueError(f"Поле {field} має бути масивом.")
    features = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ValueError(f"Елемент {field}[{index}] має бути об’єктом.")
        try:
            features.append(CharacterFeature(
                name=_text(entry, "name"),
                description=_text(entry, "description"),
                unlock=_text(entry, "unlock"),
                level=_positive_int(entry, "level"),
                kind=_text(entry, "type"),
            ))
        except ValueError as error:
            raise ValueError(f"Елемент {field}[{index}]: {error}") from error
    return tuple(features)
