from dataclasses import replace
from pathlib import Path

from .genshin_api import CatalogError, GenshinApi
from .model import ID_PATTERN, Character
from .parser import ARTWORK, parse_character, parse_character_ids
from .portraits import PortraitCache
from .storage import JsonCatalogStore


class CharacterCatalog:
    def __init__(
        self, api: GenshinApi, store: JsonCatalogStore, portraits: PortraitCache | None = None,
    ):
        self.api = api
        self.store = store
        self.data = store.load()
        self.portraits = portraits if portraits is not None else PortraitCache(store.path.parent / "portraits")

    def refresh(self) -> int:
        payload = self.api.list_ids("char")
        try:
            ids = parse_character_ids(payload)
        except ValueError as error:
            raise CatalogError("Джерело повернуло порожній або некоректний каталог.") from error
        cards = {code: self.data.remote_cards[code] for code in ids if code in self.data.remote_cards}
        self._commit(replace(self.data, remote_ids=ids, remote_cards=cards, source=self.api.source))
        return len(ids)

    def show(self, code: str) -> tuple[Character, bool]:
        if code.startswith("user:"):
            try:
                return self.data.custom_cards[code], False
            except KeyError as error:
                raise ValueError(f"Персонажа {code} не знайдено.") from error
        if not ID_PATTERN.fullmatch(code):
            raise ValueError("Некоректний код персонажа.")

        try:
            card = self._fetch_character(code)
        except CatalogError:
            cached = self.data.remote_cards.get(code)
            if cached is None:
                raise
            return cached, True

        self._commit(replace(self.data, remote_cards={**self.data.remote_cards, code: card}))
        return card, False

    def list_entries(self) -> list[dict[str, str]]:
        """Return list items without issuing one request per character."""
        entries = []
        for code in self.data.remote_ids:
            card = self.data.remote_cards.get(code)
            entries.append({"id": code, "label": card.name if card else code, "origin": "remote"})
        for code, card in sorted(self.data.custom_cards.items()):
            entries.append({"id": code, "label": card.name, "origin": "custom"})
        return entries

    def portrait(self, code: str) -> tuple[Path, bool]:
        """Download a portrait on demand or return a cached local image."""
        if code.startswith("user:"):
            card, _ = self.show(code)
            return self.portraits.get((card.image_url,))

        if not ID_PATTERN.fullmatch(code):
            raise ValueError("Некоректний код персонажа.")
        card = self.data.remote_cards.get(code)
        if card is None and code not in self.data.remote_ids:
            card, _ = self.show(code)
        primary = f"{ARTWORK}/{code}/portrait"
        fallback = card.image_url if card is not None else f"{ARTWORK}/{code}/card"
        return self.portraits.get((primary, fallback))

    def _fetch_character(self, code: str) -> Character:
        raw = self.api.get_details("char", code)
        try:
            return parse_character(code, raw)
        except ValueError as error:
            raise CatalogError(f"Некоректна картка персонажа {code}. {error}") from error

    def create(self, code: str, name: str, description: str, image_url: str) -> Character:
        if not ID_PATTERN.fullmatch(code):
            raise ValueError("Код має містити латинські літери, цифри й дефіси між словами.")
        code = f"user:{code}"
        if code in self.data.custom_cards:
            raise ValueError(f"Персонаж {code} уже існує.")
        card = Character(code, name, description, image_url)
        self._commit(replace(self.data, custom_cards={**self.data.custom_cards, code: card}))
        return card

    def _commit(self, data) -> None:
        self.store.save(data)
        self.data = data
