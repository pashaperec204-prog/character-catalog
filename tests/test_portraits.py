import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from character_catalog.cli import CatalogCLI
from character_catalog.genshin_api import GenshinApi
from character_catalog.parser import ARTWORK
from character_catalog.portraits import PortraitCache, PortraitError
from character_catalog.service import CharacterCatalog
from character_catalog.storage import JsonCatalogStore


PORTRAIT = f"{ARTWORK}/amber/portrait"
CARD = f"{ARTWORK}/amber/card"
PNG = b"\x89PNG\r\n\x1a\n" + b"test image"
JPEG = b"\xff\xd8\xff" + b"test image"


def response(data, headers=None):
    stream = io.BytesIO(data)
    stream.headers = headers or {}
    return stream


class PortraitTests(unittest.TestCase):
    def setUp(self):
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        self.directory = self.root / "portraits"
        self.cache = PortraitCache(self.directory)

    @patch("character_catalog.portraits.urlopen")
    def test_download_and_reuse_cached_file_after_restart(self, open_url):
        open_url.return_value = response(PNG, {"Content-Type": "application/octet-stream"})
        path, cached = self.cache.get((PORTRAIT,))
        self.assertFalse(cached)
        self.assertEqual(path.parent, self.directory)
        self.assertEqual(path.suffix, ".png")
        self.assertEqual(path.read_bytes(), PNG)
        self.assertEqual(open_url.call_args.args[0].full_url, PORTRAIT)

        restarted = PortraitCache(self.directory)
        self.assertEqual(restarted.get((PORTRAIT,)), (path, True))
        open_url.assert_called_once()

    @patch("character_catalog.portraits.urlopen")
    def test_fallback_image_remains_available_without_retrying_the_missing_portrait(self, open_url):
        open_url.side_effect = [HTTPError(PORTRAIT, 404, "Not found", {}, None), response(JPEG)]
        path, cached = self.cache.get((PORTRAIT, CARD))
        self.assertFalse(cached)
        self.assertEqual(path.suffix, ".jpg")
        self.assertEqual(path.read_bytes(), JPEG)
        self.assertEqual(self.cache.get((PORTRAIT, CARD)), (path, True))
        self.assertEqual([call.args[0].full_url for call in open_url.call_args_list], [PORTRAIT, CARD])

    @patch("character_catalog.portraits.urlopen")
    def test_invalid_or_incomplete_payloads_do_not_create_files(self, open_url):
        for data, headers, message in (
            (b"<html>not an image</html>", {"Content-Type": "image/png"}, "Очікується зображення"),
            (PNG, {"Content-Length": str(len(PNG) + 8)}, "неповне"),
            (PNG, {"Content-Length": str(PortraitCache.MAX_BYTES + 1)}, "10 МіБ"),
        ):
            with self.subTest(message=message):
                open_url.return_value = response(data, headers)
                with self.assertRaisesRegex(PortraitError, message):
                    self.cache.get((PORTRAIT,))
                self.assertFalse(self.directory.exists())

    @patch("character_catalog.portraits.urlopen")
    def test_damaged_cache_file_is_reloaded(self, open_url):
        open_url.side_effect = [response(PNG), response(PNG)]
        path, _ = self.cache.get((PORTRAIT,))
        path.write_bytes(b"")
        self.assertEqual(self.cache.get((PORTRAIT,)), (path, False))
        self.assertEqual(path.read_bytes(), PNG)
        self.assertEqual(open_url.call_count, 2)

    @patch("character_catalog.portraits.urlopen")
    def test_http_error_does_not_leave_a_partial_file(self, open_url):
        open_url.side_effect = URLError("offline")
        with self.assertRaisesRegex(PortraitError, "відповідь сервера"):
            self.cache.get((PORTRAIT,))
        self.assertFalse(self.directory.exists())

    @patch("character_catalog.portraits.urlopen")
    def test_cli_across_catalog_sessions_uses_cache_without_metadata_download(self, open_url):
        api = Mock(spec=GenshinApi)
        api.source = "test"
        api.list_ids.return_value = ["amber"]
        store = JsonCatalogStore(self.root / "catalog.json")
        initial = CharacterCatalog(api, store)
        initial.refresh()
        open_url.return_value = response(JPEG)

        output = []
        for _ in range(2):
            catalog = CharacterCatalog(api, store)
            commands = iter(["portrait amber", "exit"])
            CatalogCLI(catalog, input_func=lambda _: next(commands), output=output.append).run()

        self.assertTrue(any(line.startswith("Портрет завантажено:") for line in output))
        self.assertTrue(any(line.startswith("Портрет із кешу:") for line in output))
        self.assertEqual(len(list(self.directory.iterdir())), 1)
        api.get_details.assert_not_called()
        open_url.assert_called_once()

    @patch("character_catalog.portraits.urlopen")
    def test_custom_art_uses_the_url_saved_for_the_character(self, open_url):
        api = Mock(spec=GenshinApi)
        catalog = CharacterCatalog(api, JsonCatalogStore(self.root / "catalog.json"))
        url = "https://example.com/my-character"
        catalog.create("mine", "Мій герой", "Опис", url)
        open_url.return_value = response(PNG)

        path, cached = catalog.portrait("user:mine")
        self.assertFalse(cached)
        self.assertEqual(path.read_bytes(), PNG)
        self.assertEqual(open_url.call_args.args[0].full_url, url)
        api.get_details.assert_not_called()
