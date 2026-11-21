import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from character_catalog.genshin_api import GenshinApi
from character_catalog.gui_data import load_preview
from character_catalog.model import Character
from character_catalog.service import CharacterCatalog
from character_catalog.storage import JsonCatalogStore


try:
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError:
    QApplication = None


class CardDataTests(unittest.TestCase):
    def test_metadata_survives_a_portrait_error(self):
        catalog = Mock(spec=CharacterCatalog)
        card = Character("amber", "Amber", "Outrider", "https://example.com/amber.png")
        catalog.get_card.return_value = card
        catalog.portrait.side_effect = OSError("offline")
        preview = load_preview(catalog, {"id": "amber", "label": "amber"})

        self.assertEqual(preview.label, "Amber")
        self.assertIs(preview.character, card)
        self.assertIsNone(preview.portrait)
        self.assertEqual(preview.message, "Портрет недоступний.")

    def test_cached_cards_load_without_requesting_metadata_again(self):
        with TemporaryDirectory() as directory:
            store = JsonCatalogStore(Path(directory) / "catalog.json")
            api = Mock(spec=GenshinApi)
            api.get_details.return_value = {"name": "Amber", "description": "Outrider"}
            CharacterCatalog(api, store).show("amber")
            api.reset_mock()

            cached = CharacterCatalog(api, store).get_card("amber")
            self.assertEqual(cached.name, "Amber")
            api.get_details.assert_not_called()


@unittest.skipIf(QApplication is None, "Встановіть requirements-gui.txt для тесту вікна.")
class QtWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def wait_until(self, condition):
        for _ in range(100):
            if condition():
                return
            QTest.qWait(15)
        self.fail("Операція вікна не завершилась.")

    def test_window_loads_scrollable_cards_paginates_and_filters(self):
        from character_catalog.gui import CatalogWindow, PAGE_SIZE

        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "portrait.png"
            image = QImage(12, 18, QImage.Format.Format_RGB32)
            image.fill(QColor("#a6754f"))
            self.assertTrue(image.save(str(image_path)))

            api = Mock(spec=GenshinApi)
            api.source = "test"
            api.list_ids.return_value = [f"hero-{number}" for number in range(PAGE_SIZE + 1)]
            api.get_details.side_effect = lambda _, code: {
                "name": f"Hero {code[-1]}", "description": "Short profile", "vision": "Pyro",
            }
            portraits = Mock()
            portraits.get.return_value = (image_path, True)
            catalog = CharacterCatalog(api, JsonCatalogStore(Path(directory) / "catalog.json"), portraits)
            window = CatalogWindow(catalog)
            window.resize(900, 560)
            window.show()
            try:
                self.wait_until(lambda: window.more.isEnabled() and window.shown == PAGE_SIZE)
                api.list_ids.assert_called_once_with("char")
                self.assertGreater(window.scroll.verticalScrollBar().maximum(), 0)
                first = window.cards[0]
                self.assertEqual(first.findChild(QLabel, "name").text(), "Hero 0")
                self.assertIn("Pyro", first.findChild(QLabel, "meta").text())
                self.assertFalse(first.findChild(QLabel, "portrait").pixmap().isNull())

                window.more.click()
                self.wait_until(lambda: window.shown == PAGE_SIZE + 1 and window.refresh_button.isEnabled())
                self.assertFalse(window.more.isVisible())
                api.get_details.reset_mock()

                window.search.setText("Hero 2")
                self.wait_until(lambda: window.shown == 1 and window.refresh_button.isEnabled())
                self.assertEqual(window.cards[0].findChild(QLabel, "name").text(), "Hero 2")
                api.get_details.assert_not_called()

                window.search.setText("missing")
                self.wait_until(lambda: window.shown == 0)
                self.assertIn("нічого не знайдено", window.status.text())
            finally:
                window.close()
                window.pool.waitForDone(3000)
                self.app.processEvents()
