#!/usr/bin/env python3
"""Comprehensive tests for batch editor search and edit functionality."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from bitmerger.core import (
    BwItem, LoginData, UriEntry,
    parse_search_query, item_matches_terms, filter_items_by_name,
    create_rename_log, create_batch_edit_log,
    apply_batch_edit, BatchEditRecord,
)


class TestParseSearchQuery(unittest.TestCase):
    def test_single_term(self):
        self.assertEqual(parse_search_query("google"), ["google"])

    def test_multiple_terms(self):
        self.assertEqual(parse_search_query("microsoft+live.com"), ["microsoft", "live.com"])

    def test_whitespace_trim(self):
        self.assertEqual(parse_search_query("  google  +  mail.google  "), ["google", "mail.google"])

    def test_empty_parts_ignored(self):
        self.assertEqual(parse_search_query("google++live"), ["google", "live"])

    def test_empty_string(self):
        self.assertEqual(parse_search_query(""), [])


class TestItemMatchesTerms(unittest.TestCase):
    def test_single_match(self):
        item = BwItem(id="x", type=1, name="Google", login=LoginData())
        self.assertTrue(item_matches_terms(item, ["google"]))

    def test_no_match(self):
        item = BwItem(id="x", type=1, name="GitHub", login=LoginData())
        self.assertFalse(item_matches_terms(item, ["google"]))

    def test_or_match_first(self):
        item = BwItem(id="x", type=1, name="Microsoft", login=LoginData())
        self.assertTrue(item_matches_terms(item, ["microsoft", "live.com"]))

    def test_or_match_second(self):
        item = BwItem(id="x", type=1, name="live.com", login=LoginData())
        self.assertTrue(item_matches_terms(item, ["microsoft", "live.com"]))

    def test_case_insensitive(self):
        item = BwItem(id="x", type=1, name="GOOGLE", login=LoginData())
        self.assertTrue(item_matches_terms(item, ["google"]))

    def test_empty_name(self):
        item = BwItem(id="x", type=1, name="", login=LoginData())
        self.assertFalse(item_matches_terms(item, ["google"]))

    def test_empty_terms(self):
        item = BwItem(id="x", type=1, name="Google", login=LoginData())
        self.assertFalse(item_matches_terms(item, []))

    def test_substring_match(self):
        item = BwItem(id="x", type=1, name="mail.google.com", login=LoginData())
        self.assertTrue(item_matches_terms(item, ["google"]))

    def test_substring_no_false_match(self):
        item = BwItem(id="x", type=1, name="google", login=LoginData())
        self.assertFalse(item_matches_terms(item, ["google.com"]))

    def test_favorite_true(self):
        item = BwItem(id="x", type=1, name="Google", favorite=True, login=LoginData())
        self.assertTrue(item_matches_terms(item, ["favorite:true"]))
        self.assertFalse(item_matches_terms(item, ["favorite:false"]))

    def test_reprompt_true(self):
        item = BwItem(id="x", type=1, name="Google", reprompt=1, login=LoginData())
        self.assertTrue(item_matches_terms(item, ["reprompt:1"]))
        self.assertFalse(item_matches_terms(item, ["reprompt:0"]))

    def test_type_login(self):
        item = BwItem(id="x", type=1, name="Google", login=LoginData())
        self.assertTrue(item_matches_terms(item, ["type:login"]))
        self.assertFalse(item_matches_terms(item, ["type:note"]))

    def test_username_search(self):
        item = BwItem(id="x", type=1, name="Google", login=LoginData(username="alice"))
        self.assertTrue(item_matches_terms(item, ["username:alice"]))
        self.assertFalse(item_matches_terms(item, ["username:bob"]))

    def test_domain_search(self):
        item = BwItem(id="x", type=1, name="Google", login=LoginData(uris=[UriEntry(uri="https://github.com")]))
        self.assertTrue(item_matches_terms(item, ["domain:github.com"]))
        self.assertFalse(item_matches_terms(item, ["domain:google.com"]))

    def test_notes_search(self):
        item = BwItem(id="x", type=1, name="Google", notes="backup code", login=LoginData())
        self.assertTrue(item_matches_terms(item, ["notes:backup"]))
        self.assertFalse(item_matches_terms(item, ["notes:missing"]))

    def test_folder_search(self):
        item = BwItem(id="x", type=1, name="Google", folderId="f1", login=LoginData())
        folder_map = {"f1": "Personal"}
        self.assertTrue(item_matches_terms(item, ["folder:Personal"], folder_map=folder_map))
        self.assertTrue(item_matches_terms(item, ["folder:f1"], folder_map=folder_map))
        self.assertFalse(item_matches_terms(item, ["folder:Work"], folder_map=folder_map))

    def test_id_search(self):
        item = BwItem(id="abc-123", type=1, name="Google", login=LoginData())
        self.assertTrue(item_matches_terms(item, ["id:abc"]))
        self.assertFalse(item_matches_terms(item, ["id:xyz"]))

    def test_collection_search(self):
        item = BwItem(id="x", type=1, name="Google", collectionIds=["c1", "c2"], login=LoginData())
        self.assertTrue(item_matches_terms(item, ["collection:c1"]))
        self.assertFalse(item_matches_terms(item, ["collection:c3"]))

    def test_org_search(self):
        item = BwItem(id="x", type=1, name="Google", organizationId="org1", login=LoginData())
        self.assertTrue(item_matches_terms(item, ["org:org1"]))
        self.assertFalse(item_matches_terms(item, ["org:org2"]))


class TestFilterItemsByName(unittest.TestCase):
    def make_login(self, name: str) -> BwItem:
        return BwItem(id="x", type=1, name=name, login=LoginData())

    def test_filters_by_type(self):
        items = [
            BwItem(id="a", type=1, name="Google", login=LoginData()),
            BwItem(id="b", type=2, name="Google Note", secureNote={"type": 0}),
        ]
        result = filter_items_by_name(items, ["google"], {1})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "a")

    def test_returns_all_matches(self):
        items = [
            self.make_login("Google"),
            self.make_login("GitHub"),
            self.make_login("Google Old"),
        ]
        result = filter_items_by_name(items, ["google"], {1, 2, 3, 4, 5})
        self.assertEqual(len(result), 2)
        self.assertEqual([r.name for r in result], ["Google", "Google Old"])

    def test_field_filter_favorite(self):
        items = [
            BwItem(id="a", type=1, name="A", favorite=True, login=LoginData()),
            BwItem(id="b", type=1, name="B", favorite=False, login=LoginData()),
        ]
        result = filter_items_by_name(items, ["favorite:true"], {1})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "a")


class TestCreateRenameLog(unittest.TestCase):
    def test_creates_log(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.json"
            renamed = [
                ("id1", "Old Name", "New Name"),
                ("id2", "Another Old", "New Name"),
            ]
            log_path = create_rename_log(renamed, out_path)
            self.assertTrue(log_path.exists())
            self.assertIn("rename-log", log_path.name)
            data = json.loads(log_path.read_text())
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["id"], "id1")
            self.assertEqual(data[0]["old_name"], "Old Name")
            self.assertEqual(data[0]["new_name"], "New Name")

    def test_empty_log(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.json"
            log_path = create_rename_log([], out_path)
            self.assertTrue(log_path.exists())
            data = json.loads(log_path.read_text())
            self.assertEqual(data, [])


class TestBatchEdit(unittest.TestCase):
    def test_apply_name(self):
        items = [
            BwItem(id="a", type=1, name="Old", login=LoginData()),
            BwItem(id="b", type=1, name="Other", login=LoginData()),
        ]
        matches = [items[0]]
        records = apply_batch_edit(items, matches, "name", "New")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].field, "name")
        self.assertEqual(records[0].old_value, "Old")
        self.assertEqual(records[0].new_value, "New")
        self.assertEqual(items[0].name, "New")
        self.assertEqual(items[1].name, "Other")

    def test_apply_favorite(self):
        items = [
            BwItem(id="a", type=1, name="A", favorite=False, login=LoginData()),
            BwItem(id="b", type=1, name="B", favorite=False, login=LoginData()),
        ]
        records = apply_batch_edit(items, items, "favorite", True)
        self.assertTrue(all(i.favorite for i in items))
        self.assertEqual(len(records), 2)

    def test_apply_reprompt(self):
        items = [
            BwItem(id="a", type=1, name="A", reprompt=0, login=LoginData()),
        ]
        records = apply_batch_edit(items, items, "reprompt", True)
        self.assertEqual(items[0].reprompt, 1)
        self.assertEqual(records[0].new_value, True)

    def test_apply_username_creates_login(self):
        items = [
            BwItem(id="a", type=1, name="A", login=None),
        ]
        records = apply_batch_edit(items, items, "username", "alice")
        assert items[0].login is not None
        self.assertEqual(items[0].login.username, "alice")

    def test_apply_folder(self):
        items = [
            BwItem(id="a", type=1, name="A", folderId=None, login=LoginData()),
        ]
        records = apply_batch_edit(items, items, "folder", "f1")
        self.assertEqual(items[0].folderId, "f1")

    def test_apply_domain_existing_uri(self):
        items = [
            BwItem(id="a", type=1, name="A", login=LoginData(uris=[UriEntry(uri="https://old.com/path")])),
        ]
        records = apply_batch_edit(items, items, "domain", "new.com")
        assert items[0].login is not None
        assert items[0].login.uris
        self.assertEqual(items[0].login.uris[0].uri, "https://new.com/path")
        self.assertEqual(records[0].old_value, "old.com")
        self.assertEqual(records[0].new_value, "new.com")

    def test_apply_domain_full_url_value(self):
        items = [
            BwItem(id="a", type=1, name="A", login=LoginData(uris=[UriEntry(uri="https://old.com/path")])),
        ]
        records = apply_batch_edit(items, items, "domain", "http://localhost:8080")
        assert items[0].login is not None
        assert items[0].login.uris
        self.assertEqual(items[0].login.uris[0].uri, "http://localhost:8080")

    def test_apply_domain_creates_uri(self):
        items = [
            BwItem(id="a", type=1, name="A", login=LoginData()),
        ]
        records = apply_batch_edit(items, items, "domain", "192.168.1.1")
        assert items[0].login is not None
        assert items[0].login.uris
        self.assertEqual(items[0].login.uris[0].uri, "http://192.168.1.1")

    def test_apply_domain_preserves_port(self):
        items = [
            BwItem(id="a", type=1, name="A", login=LoginData(uris=[UriEntry(uri="https://old.com:8443/path")])),
        ]
        records = apply_batch_edit(items, items, "domain", "new.com")
        assert items[0].login is not None
        assert items[0].login.uris
        self.assertEqual(items[0].login.uris[0].uri, "https://new.com:8443/path")

    def test_apply_domain_no_login(self):
        items = [
            BwItem(id="a", type=1, name="A", login=None),
        ]
        records = apply_batch_edit(items, items, "domain", "example.com")
        assert items[0].login is not None
        assert items[0].login.uris
        self.assertEqual(items[0].login.uris[0].uri, "http://example.com")

    def test_get_domain_value(self):
        item = BwItem(id="a", type=1, name="A", login=LoginData(uris=[UriEntry(uri="https://github.com")]))
        from bitmerger.core import _get_field_value
        self.assertEqual(_get_field_value(item, "domain"), "github.com")

    def test_get_domain_no_uris(self):
        item = BwItem(id="a", type=1, name="A", login=LoginData())
        from bitmerger.core import _get_field_value
        self.assertIsNone(_get_field_value(item, "domain"))

    def test_get_domain_no_login(self):
        item = BwItem(id="a", type=1, name="A", login=None)
        from bitmerger.core import _get_field_value
        self.assertIsNone(_get_field_value(item, "domain"))


class TestBatchEditLog(unittest.TestCase):
    def test_creates_log(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.json"
            records = [
                BatchEditRecord(item_id="a", field="favorite", old_value=False, new_value=True),
            ]
            log_path = create_batch_edit_log(records, out_path)
            self.assertTrue(log_path.exists())
            self.assertIn("batch-edit-log", log_path.name)
            data = json.loads(log_path.read_text())
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["field"], "favorite")
            self.assertEqual(data[0]["old"], False)
            self.assertEqual(data[0]["new"], True)


class TestIntegration(unittest.TestCase):
    def test_end_to_end_edit(self):
        vault = {
            "items": [
                {"id": "a", "type": 1, "name": "Google", "favorite": False, "login": {"uris": [], "username": "u", "password": "p"}},
                {"id": "b", "type": 1, "name": "mail.google.com", "favorite": True, "login": {"uris": [], "username": "u", "password": "p"}},
                {"id": "c", "type": 1, "name": "GitHub", "favorite": False, "login": {"uris": [], "username": "u", "password": "p"}},
            ]
        }
        items = [BwItem.from_dict(i) for i in vault["items"]]
        terms = parse_search_query("favorite:true")
        matches = filter_items_by_name(items, terms, {1, 2, 3, 4, 5})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "b")

        records = apply_batch_edit(items, matches, "name", "Google Unified")
        self.assertEqual(len(records), 1)
        names = [i.name for i in items]
        self.assertEqual(names, ["Google", "Google Unified", "GitHub"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
