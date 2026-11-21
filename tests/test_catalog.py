import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from character_catalog.cli import CatalogCLI
from character_catalog.genshin_api import CatalogError, GenshinApi
from character_catalog.service import CharacterCatalog
from character_catalog.storage import JsonCatalogStore


class CatalogTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "catalog.json"
        self.store = JsonCatalogStore(self.path)
        self.api = Mock(spec=GenshinApi)
        self.api.source = "Тестове джерело"
        self.api.list_ids.return_value = ["lisa", "amber", "amber"]
        self.api.get_details.return_value = {
            "name": "Amber", "description": "Розвідниця", "vision": "Pyro", "rarity": 4,
        }
        self.catalog = CharacterCatalog(self.api, self.store)

    def run_cli(self, entries):
        answers = iter(entries)
        output = []
        CatalogCLI(self.catalog, input_func=lambda _: next(answers), output=output.append).run()
        return "\n".join(output)

    def test_refresh_lists_all_ids_and_show_outputs_card_and_graphics(self):
        output = self.run_cli(["refresh", "show amber", "exit"])
        self.api.list_ids.assert_called_once_with("char")
        self.api.get_details.assert_called_once_with("char", "amber")
        self.assertIn("Віддалених персонажів: 2", output)
        self.assertIn("\namber\nlisa\n", output)
        self.assertIn("Опис: Розвідниця\nСтихія: Pyro", output)
        self.assertIn("Графіка: https://raw.githubusercontent.com/", output)
        self.assertEqual(self.store.load().remote_ids, ["amber", "lisa"])

    def test_failed_refresh_keeps_previous_data_and_show_uses_cached_card(self):
        self.catalog.refresh()
        self.catalog.show("amber")
        before = self.path.read_bytes()
        self.api.list_ids.side_effect = CatalogError("Мережа недоступна.")
        self.api.get_details.side_effect = CatalogError("Мережа недоступна.")
        self.catalog = CharacterCatalog(self.api, self.store)
        output = self.run_cli(["refresh", "list", "show amber", "exit"])
        self.assertIn("Помилка: Мережа недоступна.", output)
        self.assertIn("\namber\nlisa\n", output)
        self.assertIn("Показано збережену локальну копію картки.", output)
        self.assertEqual(self.path.read_bytes(), before)

    def test_cancel_invalid_url_and_duplicate_do_not_overwrite(self):
        self.catalog.create("original", "Оригінал", "Перший запис", "https://example.com/a.png")
        before = self.path.read_bytes()
        output = self.run_cli([
            "create", "draft", "/cancel",
            "create", "draft", "Чернетка", "Опис", "file:///draft.png",
            "create", "original", "Інше ім’я", "Опис", "https://example.com/b.png",
            "exit",
        ])
        self.assertIn("Створення скасовано.", output)
        self.assertIn("має бути HTTP або HTTPS URL", output)
        self.assertIn("user:original уже існує.", output)
        self.assertEqual(self.path.read_bytes(), before)

    def test_custom_and_remote_ids_can_share_a_slug(self):
        self.catalog.refresh()
        self.catalog.create("amber", "Моя Amber", "Мій опис", "https://example.com/my.png")
        self.assertEqual(self.catalog.show("amber")[0].name, "Amber")
        self.assertEqual(self.catalog.show("user:amber")[0].name, "Моя Amber")

    def test_creation_survives_a_new_process(self):
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, "-X", "utf8", "-m", "character_catalog", "--data-file", str(self.path)]

        def run(entries):
            return subprocess.run(
                command, input="\n".join(entries) + "\n", encoding="utf-8", capture_output=True,
                cwd=root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=10, check=True,
            ).stdout

        self.assertIn("створено й збережено", run([
            "create", "star-keeper", "Провідник", "Шукає зорі", "https://example.com/star.png", "exit",
        ]))
        self.assertIn("user:star-keeper  Провідник", run(["list", "exit"]))
        self.assertIn("Графіка: https://example.com/star.png", run(["show user:star-keeper", "exit"]))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["custom_cards"]["user:star-keeper"]["description"], "Шукає зорі")
