import json
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class CatalogError(ValueError):
    pass


class GenshinApi:
    API_URL = "https://genshin.jmp.blue"
    GITHUB_CATALOG = "https://api.github.com/repos/genshindev/api/contents/assets/data"
    GITHUB_DATA = "https://raw.githubusercontent.com/genshindev/api/mistress/assets/data"
    CATEGORIES = {"char": "characters", "weapon": "weapons"}

    def __init__(self, timeout=8):
        self.timeout = timeout
        self._use_github = False

    @property
    def source(self):
        if self._use_github:
            return "GitHub (genshindev/api)"
        return self.API_URL

    def list_ids(self, category):
        group = self.CATEGORIES[category]
        data = self._fetch(f"/{group}", f"{self.GITHUB_CATALOG}/{group}?ref=mistress")
        if not isinstance(data, list):
            raise CatalogError("Каталог повернув список у невідомому форматі.")
        if self._use_github:
            data = [
                entry.get("name") for entry in data
                if isinstance(entry, dict) and entry.get("type") == "dir"
            ]
        if not all(isinstance(entry, str) for entry in data):
            raise CatalogError("Каталог повернув некоректні ID.")
        return sorted(data)

    def get_details(self, category, entry_id):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", entry_id):
            raise CatalogError("Некоректний ID. Використайте значення зі списку catalog.")
        group = self.CATEGORIES[category]
        route = f"/{group}/{entry_id}"
        data = self._fetch(route, f"{self.GITHUB_DATA}{route}/en.json")
        if not isinstance(data, dict):
            raise CatalogError("Каталог повернув опис у невідомому форматі.")
        return data

    def _fetch(self, route, github_url):
        if not self._use_github:
            try:
                return self._read(f"{self.API_URL}{route}")
            except HTTPError as error:
                if error.code == 404:
                    raise CatalogError("Запис у каталозі не знайдено.") from error
                if error.code < 500 and error.code != 429:
                    raise CatalogError(f"Помилка Genshin API (HTTP {error.code}).") from error
            except (OSError, ValueError):
                pass
            self._use_github = True

        try:
            return self._read(github_url)
        except HTTPError as error:
            if error.code == 404:
                raise CatalogError("Запис у каталозі не знайдено.") from error
            raise CatalogError(f"Помилка резервного каталогу (HTTP {error.code}).") from error
        except (OSError, ValueError) as error:
            raise CatalogError("Не вдалося отримати дані з віддаленого каталогу.") from error

    def _read(self, url):
        request = Request(url, headers={
            "User-Agent": "Genshin-Character-CLI",
            "Accept": "application/json",
        })
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)
