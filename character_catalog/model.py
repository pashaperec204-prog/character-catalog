import re
from dataclasses import dataclass
from urllib.parse import urlsplit


ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def validate_image_url(value: str) -> None:
    if any(character.isspace() for character in value):
        raise ValueError("Посилання на зображення має бути HTTP або HTTPS URL.")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username is not None:
        raise ValueError("Посилання на зображення має бути HTTP або HTTPS URL.")


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

    def __post_init__(self) -> None:
        code = self.id.removeprefix("user:")
        if not ID_PATTERN.fullmatch(code):
            raise ValueError("Код має містити латинські літери, цифри й дефіси між словами.")
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Ім’я та опис мають бути заповнені.")
        validate_image_url(self.image_url)
