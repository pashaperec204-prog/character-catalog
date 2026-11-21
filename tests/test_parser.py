import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from character_catalog.genshin_api import CatalogError, GenshinApi
from character_catalog.model import CharacterFeature
from character_catalog.parser import parse_character, parse_character_ids
from character_catalog.service import CharacterCatalog
from character_catalog.storage import JsonCatalogStore


def remote_card():
    return {
        "name": " Amber ",
        "title": "Gliding Champion",
        "vision": "Pyro",
        "weapon": "Bow",
        "nation": "Mondstadt",
        "affiliation": "Knights of Favonius",
        "rarity": "4",
        "birthday": "0000-08-10",
        "description": "Outrider.",
        "skillTalents": [
            {"name": "Sharpshooter", "description": "Fires arrows.", "type": "NORMAL_ATTACK"},
        ],
        "passiveTalents": [
            {"name": "Gliding Champion", "description": "Uses less stamina.", "level": 1},
        ],
        "constellations": [
            {"name": "One Arrow to Rule Them All", "unlock": "Constellation Lv. 1", "level": 1},
        ],
        "unrecognized": ["Ignored"],
    }


class ParserTests(unittest.TestCase):
    def test_index_deduplicates_and_rejects_invalid_json_values(self):
        self.assertEqual(parse_character_ids(["lisa", "amber", "lisa"]), ["amber", "lisa"])
        for value in (None, [], {"characters": []}, [2], ["../lisa"], [{"name": "lisa"}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_character_ids(value)

    def test_card_maps_nested_json_into_a_detached_view_model(self):
        card = parse_character("amber", json.loads(json.dumps(remote_card())))
        self.assertEqual((card.name, card.rarity, card.element), ("Amber", 4, "Pyro"))
        self.assertEqual(card.affiliation, "Knights of Favonius")
        self.assertIsInstance(card.skills[0], CharacterFeature)
        self.assertEqual(card.skills[0].kind, "NORMAL_ATTACK")
        self.assertEqual(card.passives[0].level, 1)
        self.assertEqual(card.constellations[0].unlock, "Constellation Lv. 1")

        view = card.to_view_data()
        self.assertEqual(json.loads(json.dumps(view)), view)
        self.assertTrue(view["image_url"].endswith("/amber/card"))
        self.assertNotIn("unrecognized", view)
        view["skills"][0]["name"] = "Edited"
        self.assertEqual(card.skills[0].name, "Sharpshooter")

    def test_missing_optional_fields_get_consistent_defaults(self):
        card = parse_character("lisa", {"name": "Lisa", "vision": None, "constellations": None})
        self.assertEqual(card.description, "Опис відсутній.")
        self.assertEqual(card.element, "")
        self.assertIsNone(card.rarity)
        self.assertEqual(card.to_view_data()["constellations"], [])

    def test_malformed_nested_data_is_reported_with_the_field(self):
        for payload, field in (
            ({"name": " ", "constellations": []}, "Ім’я"),
            ({"name": "Amber", "rarity": True}, "rarity"),
            ({"name": "Amber", "skillTalents": {}}, "skillTalents"),
            ({"name": "Amber", "passiveTalents": [{"name": 13}]}, r"passiveTalents\[0\]"),
            ({"name": "Amber", "constellations": [{"name": "First", "level": -1}]}, "level"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                parse_character("amber", payload)


class ParserIntegrationTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = JsonCatalogStore(Path(folder.name) / "catalog.json")
        self.api = Mock(spec=GenshinApi)
        self.api.list_ids.return_value = ["amber", "lisa"]
        self.api.get_details.return_value = remote_card()
        self.api.source = "test source"

    def test_view_listing_requires_no_detail_requests(self):
        catalog = CharacterCatalog(self.api, self.store)
        catalog.refresh()
        catalog.create("new", "Власний", "Опис", "https://example.com/new.png")
        self.assertEqual(catalog.list_entries(), [
            {"id": "amber", "label": "amber", "origin": "remote"},
            {"id": "lisa", "label": "lisa", "origin": "remote"},
            {"id": "user:new", "label": "Власний", "origin": "custom"},
        ])
        self.api.get_details.assert_not_called()
        catalog.show("amber")
        self.assertEqual(catalog.list_entries()[0]["label"], "Amber")

    def test_malformed_response_keeps_the_rich_cached_card(self):
        first = CharacterCatalog(self.api, self.store)
        first.refresh()
        saved, _ = first.show("amber")
        self.api.get_details.return_value = {"name": "Amber", "skillTalents": 8}
        second = CharacterCatalog(self.api, self.store)
        self.assertEqual(second.show("amber"), (saved, True))
        self.assertEqual(self.store.load().remote_cards["amber"], saved)
        with self.assertRaisesRegex(CatalogError, "skillTalents"):
            second.show("lisa")

    def test_loads_pre_parser_user_and_remote_cards(self):
        record = {
            "id": "user:old", "name": "Старий запис", "description": "Збережений опис",
            "image_url": "https://example.com/old.png", "rarity": None,
        }
        self.store.path.write_text(json.dumps({
            "version": 1, "source": "old source", "remote_ids": ["amber"],
            "remote_cards": {"amber": {**record, "id": "amber", "name": "Amber"}},
            "custom_cards": {"user:old": record},
        }), encoding="utf-8")
        catalog = CharacterCatalog(self.api, self.store)
        self.assertEqual(catalog.show("user:old")[0].name, "Старий запис")
        self.assertEqual(catalog.data.remote_cards["amber"].to_view_data()["skills"], [])
        catalog.show("amber")
        self.assertEqual(self.store.load().custom_cards["user:old"].name, "Старий запис")
