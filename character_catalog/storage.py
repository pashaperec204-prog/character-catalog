import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .model import ID_PATTERN, Character


@dataclass
class CatalogData:
    remote_ids: list[str] = field(default_factory=list)
    remote_cards: dict[str, Character] = field(default_factory=dict)
    custom_cards: dict[str, Character] = field(default_factory=dict)
    source: str = ""


class JsonCatalogStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> CatalogData:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return CatalogData()

        try:
            data = json.loads(raw)
            if data["version"] != 1:
                raise ValueError("Невідома версія сховища.")
            remote_ids = data["remote_ids"]
            source = data["source"]
            if not isinstance(source, str) or not isinstance(remote_ids, list) or not all(
                isinstance(code, str) and ID_PATTERN.fullmatch(code) for code in remote_ids
            ):
                raise ValueError("Помилковий список ID.")
            return CatalogData(
                remote_ids=remote_ids,
                source=source,
                remote_cards=self._load_cards(data["remote_cards"], custom=False),
                custom_cards=self._load_cards(data["custom_cards"], custom=True),
            )
        except (KeyError, TypeError, AttributeError, ValueError) as error:
            raise ValueError(f"Не вдалося прочитати сховище {self.path}: {error}") from error

    @staticmethod
    def _load_cards(records, *, custom: bool) -> dict[str, Character]:
        cards = {code: Character(**record) for code, record in records.items()}
        if any(code != card.id or code.startswith("user:") != custom
               for code, card in cards.items()):
            raise ValueError("Помилковий ID картки.")
        return cards

    def save(self, data: CatalogData) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            # The previous snapshot stays intact if writing the new one fails.
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent, mode="w", encoding="utf-8", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump({"version": 1, **asdict(data)}, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
