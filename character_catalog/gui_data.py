from dataclasses import dataclass
from pathlib import Path

from .model import Character
from .service import CharacterCatalog


@dataclass(frozen=True)
class CardPreview:
    code: str
    label: str
    character: Character | None = None
    portrait: Path | None = None
    message: str = ""


def load_preview(catalog: CharacterCatalog, entry: dict[str, str]) -> CardPreview:
    code, label = entry["id"], entry["label"]
    try:
        character = catalog.get_card(code)
    except (OSError, ValueError):
        return CardPreview(code, label, message="Картка зараз недоступна.")

    try:
        portrait, _ = catalog.portrait(code)
    except (OSError, ValueError):
        return CardPreview(code, character.name, character, message="Портрет недоступний.")
    return CardPreview(code, character.name, character, portrait)
