from dataclasses import replace

from .genshin_api import CatalogError, GenshinApi
from .model import ID_PATTERN, Character
from .storage import JsonCatalogStore


class CharacterCatalog:
    ARTWORK = "https://raw.githubusercontent.com/genshindev/api/mistress/assets/images/characters"

    def __init__(self, api: GenshinApi, store: JsonCatalogStore):
        self.api = api
        self.store = store
        self.data = store.load()

    def refresh(self) -> int:
        ids = sorted(set(self.api.list_ids("char")))
        if not ids or not all(ID_PATTERN.fullmatch(code) for code in ids):
            raise CatalogError("Джерело повернуло порожній або некоректний каталог.")
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
            raw = self.api.get_details("char", code)
        except CatalogError:
            cached = self.data.remote_cards.get(code)
            if cached is None:
                raise
            return cached, True

        try:
            card = Character(
                id=code, name=raw["name"], description=raw.get("description") or "Опис відсутній.",
                element=raw.get("vision") or "", nation=raw.get("nation") or "",
                weapon=raw.get("weapon") or "", rarity=raw.get("rarity"),
                image_url=f"{self.ARTWORK}/{code}/card",
            )
        except (KeyError, TypeError, AttributeError, ValueError) as error:
            raise CatalogError("Джерело повернуло некоректну картку персонажа.") from error

        self._commit(replace(self.data, remote_cards={**self.data.remote_cards, code: card}))
        return card, False

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
