import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit


ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def validate_image_url(value: str) -> None:
    if any(character.isspace() for character in value):
        raise ValueError("Посилання на зображення має бути HTTP або HTTPS URL.")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username is not None:
        raise ValueError("Посилання на зображення має бути HTTP або HTTPS URL.")


@dataclass(frozen=True)
class CharacterFeature:
    name: str
    description: str = ""
    unlock: str = ""
    level: int | None = None
    kind: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Назва здібності або сузір’я має бути заповнена.")


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    description: str
    image_url: str
    element: str = ""
    nation: str = ""
    weapon: str = ""
    rarity: int | None = None
    title: str = ""
    affiliation: str = ""
    birthday: str = ""
    skills: tuple[CharacterFeature, ...] = ()
    passives: tuple[CharacterFeature, ...] = ()
    constellations: tuple[CharacterFeature, ...] = ()

    def __post_init__(self) -> None:
        code = self.id.removeprefix("user:")
        if not ID_PATTERN.fullmatch(code):
            raise ValueError("Код має містити латинські літери, цифри й дефіси між словами.")
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Ім’я та опис мають бути заповнені.")
        validate_image_url(self.image_url)

    def to_view_data(self) -> dict:
        """Return a detached, JSON-ready card for a presentation component."""
        data = asdict(self)
        for field in ("skills", "passives", "constellations"):
            data[field] = list(data[field])
        return data
