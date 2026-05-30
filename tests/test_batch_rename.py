#!/usr/bin/env python3
"""Comprehensive tests for batch rename functionality."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from bw_dedup import (
    BwItem, LoginData, UriEntry,
    parse_search_query, item_matches_terms, filter_items_by_name,
    create_rename_log, show_rename_preview,
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


class TestIntegration(unittest.TestCase):
    def test_end_to_end_rename(self):
        vault = {
            "items": [
                {"id": "a", "type": 1, "name": "Google", "login": {"uris": [], "username": "u", "password": "p"}},
                {"id": "b", "type": 1, "name": "mail.google.com", "login": {"uris": [], "username": "u", "password": "p"}},
                {"id": "c", "type": 1, "name": "GitHub", "login": {"uris": [], "username": "u", "password": "p"}},
            ]
        }
        items = [BwItem.from_dict(i) for i in vault["items"]]
        terms = parse_search_query("google")
        matches = filter_items_by_name(items, terms, {1, 2, 3, 4, 5})
        self.assertEqual(len(matches), 2)

        for item in items:
            if item in matches:
                item.name = "Google Unified"

        names = [i.name for i in items]
        self.assertEqual(names, ["Google Unified", "Google Unified", "GitHub"])

    def test_end_to_end_or_rename(self):
        vault = {
            "items": [
                {"id": "a", "type": 1, "name": "Microsoft", "login": {"uris": [], "username": "u", "password": "p"}},
                {"id": "b", "type": 1, "name": "live.com", "login": {"uris": [], "username": "u", "password": "p"}},
                {"id": "c", "type": 1, "name": "GitHub", "login": {"uris": [], "username": "u", "password": "p"}},
            ]
        }
        items = [BwItem.from_dict(i) for i in vault["items"]]
        terms = parse_search_query("microsoft+live.com")
        matches = filter_items_by_name(items, terms, {1, 2, 3, 4, 5})
        self.assertEqual(len(matches), 2)

        for item in items:
            if item in matches:
                item.name = "Microsoft"

        names = [i.name for i in items]
        self.assertEqual(names, ["Microsoft", "Microsoft", "GitHub"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
