#!/usr/bin/env python3
"""Comprehensive unit + integration tests for Bitmerger engine."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

# Ensure we import the local module
sys.path.insert(0, str(Path(__file__).parent.parent))

from bw_dedup import (
    BwItem, LoginData, UriEntry, SshKeyData,
    normalize_text, normalize_domain, clean_uri,
    fuzzy_name_similarity, login_similarity, item_similarity,
    cluster_confidence, pick_primary, merge_items,
    find_duplicates_by_type, create_backup, create_merge_log,
    generate_html_report, MergeRecord,
)


class TestNormalization(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("Hello World!"), "hello world")
        self.assertEqual(normalize_text("  GitHub  "), "github")
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text("a-b_c"), "abc")

    def test_normalize_domain(self):
        self.assertEqual(normalize_domain("https://github.com/login"), "github.com")
        self.assertEqual(normalize_domain("http://api.sub.example.co.uk/path"), "example.co.uk")
        self.assertEqual(normalize_domain(""), "")
        self.assertEqual(normalize_domain("not-a-url"), "not-a-url")

    def test_clean_uri(self):
        self.assertEqual(clean_uri("https://example.com/path?foo=bar#frag"), "https://example.com/path")
        self.assertEqual(clean_uri(""), "")


class TestFuzzySimilarity(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(fuzzy_name_similarity("GitHub", "github"), 1.0)

    def test_partial_match(self):
        self.assertGreater(fuzzy_name_similarity("GitHub", "GitHub Old"), 0.7)

    def test_empty(self):
        self.assertEqual(fuzzy_name_similarity("", "test"), 0.0)


class TestLoginSimilarity(unittest.TestCase):
    def make_login(self, name: str, uris: list[str], username: str, password: str) -> BwItem:
        return BwItem(
            id="x", type=1, name=name,
            login=LoginData(uris=[UriEntry(uri=u) for u in uris], username=username, password=password)
        )

    def test_exact_domain_user_pass(self):
        a = self.make_login("GitHub", ["https://github.com"], "alice", "secret")
        b = self.make_login("GitHub Old", ["https://github.com"], "alice", "secret")
        self.assertAlmostEqual(login_similarity(a, b), 1.0, delta=0.03)

    def test_different_password(self):
        a = self.make_login("GitHub", ["https://github.com"], "alice", "secret")
        b = self.make_login("GitHub", ["https://github.com"], "alice", "other")
        s = login_similarity(a, b)
        self.assertGreater(s, 0.5)
        self.assertLess(s, 1.0)

    def test_no_domain_match(self):
        a = self.make_login("GitHub", ["https://github.com"], "alice", "secret")
        b = self.make_login("Twitter", ["https://twitter.com"], "alice", "secret")
        s = login_similarity(a, b)
        self.assertLess(s, 0.85)
        self.assertGreater(s, 0.5)


class TestItemSimilarity(unittest.TestCase):
    def test_different_types(self):
        a = BwItem(id="a", type=1, name="x", login=LoginData())
        b = BwItem(id="b", type=2, name="x", secureNote={"type": 0})
        self.assertEqual(item_similarity(a, b), 0.0)


class TestClusterConfidence(unittest.TestCase):
    def test_exact_login_cluster(self):
        a = BwItem(id="a", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"
        ))
        b = BwItem(id="b", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"
        ))
        self.assertEqual(cluster_confidence([a, b]), 1.0)

    def test_single_item(self):
        a = BwItem(id="a", type=1, name="X", login=LoginData())
        self.assertEqual(cluster_confidence([a]), 1.0)


class TestPickPrimary(unittest.TestCase):
    def test_login_prefers_uris(self):
        a = BwItem(id="a", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="u", password="p"
        ))
        b = BwItem(id="b", type=1, name="GitHub", login=LoginData(
            uris=[], username="u", password="p"
        ))
        cluster = [a, b]
        self.assertEqual(pick_primary(cluster), 0)

    def test_login_prefers_passkeys(self):
        a = BwItem(id="a", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="u", password="p", fido2Credentials=[{"credentialId": "abc"}]
        ))
        b = BwItem(id="b", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="u", password="p", totp="123"
        ))
        cluster = [a, b]
        self.assertEqual(pick_primary(cluster), 0)


class TestMergeItems(unittest.TestCase):
    def test_login_backfill_empty(self):
        target = BwItem(id="t", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"
        ))
        source = BwItem(id="s", type=1, name="GitHub", login=LoginData(
            uris=[], username="", password="", totp="totp123"
        ))
        merged, _backfilled = merge_items(target, source)
        assert merged.login is not None
        self.assertEqual(merged.login.totp, "totp123")
        self.assertIn("totp", _backfilled)

    def test_login_different_username_absorbed_to_notes(self):
        """If both have non-empty different usernames, secondary must be absorbed."""
        target = BwItem(id="t", type=1, name="GitHub", notes="Primary note",
                        login=LoginData(uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"))
        source = BwItem(id="s", type=1, name="GitHub", notes="Secondary note",
                        login=LoginData(uris=[], username="bob", password="secret2", totp="totp123"))
        merged, _backfilled = merge_items(target, source)
        # alice must stay
        assert merged.login is not None
        self.assertEqual(merged.login.username, "alice")
        # bob must appear in notes
        self.assertIn("bob", merged.notes or "")
        self.assertIn("Primary note", merged.notes or "")
        self.assertIn("Secondary note", merged.notes or "")
        self.assertIn("conflicts", _backfilled)

    def test_login_different_password_absorbed_to_notes(self):
        target = BwItem(id="t", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"
        ))
        source = BwItem(id="s", type=1, name="GitHub", login=LoginData(
            uris=[], username="alice", password="other"
        ))
        merged, _backfilled = merge_items(target, source)
        assert merged.login is not None
        self.assertEqual(merged.login.password, "secret")
        self.assertIn("alternate password", (merged.notes or "").lower())
        self.assertIn("conflicts", _backfilled)

    def test_passkey_deduplication(self):
        target = BwItem(id="t", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="alice", password="secret",
            fido2Credentials=[{"credentialId": "abc", "key": "val1"}]
        ))
        source = BwItem(id="s", type=1, name="GitHub", login=LoginData(
            uris=[], username="alice", password="secret",
            fido2Credentials=[{"credentialId": "abc", "key": "val2"}, {"credentialId": "def", "key": "val3"}]
        ))
        merged, _backfilled = merge_items(target, source)
        assert merged.login is not None
        assert merged.login.fido2Credentials is not None
        cids = [c.get("credentialId") for c in merged.login.fido2Credentials]
        self.assertEqual(len(cids), 2)
        self.assertIn("abc", cids)
        self.assertIn("def", cids)
        self.assertEqual(_backfilled.get("passkeys"), 1)

    def test_notes_concatenation(self):
        target = BwItem(id="t", type=1, name="GitHub", notes="Note A", login=LoginData())
        source = BwItem(id="s", type=1, name="GitHub", notes="Note B", login=LoginData())
        merged, _backfilled = merge_items(target, source)
        self.assertIn("Note A", merged.notes or "")
        self.assertIn("Note B", merged.notes or "")
        self.assertIn("notes", _backfilled)

    def test_notes_no_duplicate(self):
        target = BwItem(id="t", type=1, name="GitHub", notes="Same note", login=LoginData())
        source = BwItem(id="s", type=1, name="GitHub", notes="Same note", login=LoginData())
        merged, _backfilled = merge_items(target, source)
        self.assertEqual(merged.notes, "Same note")

    def test_card_merge(self):
        target = BwItem(id="t", type=3, name="Visa", card={"brand": "Visa", "number": "1234"})
        source = BwItem(id="s", type=3, name="Visa", card={"brand": "Visa", "number": "1234", "expMonth": "12"})
        merged, _backfilled = merge_items(target, source)
        assert merged.card is not None
        self.assertEqual(merged.card.get("expMonth"), "12")
        self.assertIn("card_expMonth", _backfilled)

    def test_identity_merge(self):
        target = BwItem(id="t", type=4, name="Me", identity={"firstName": "Alice", "email": "a@example.com"})
        source = BwItem(id="s", type=4, name="Me", identity={"firstName": "Alice", "email": "a@example.com", "phone": "555"})
        merged, _backfilled = merge_items(target, source)
        assert merged.identity is not None
        self.assertEqual(merged.identity.get("phone"), "555")

    def test_ssh_merge(self):
        target = BwItem(id="t", type=5, name="Key", sshKey=SshKeyData(keyFingerprint="fp1"))
        source = BwItem(id="s", type=5, name="Key", sshKey=SshKeyData(privateKey="priv", publicKey="pub"))
        merged, _backfilled = merge_items(target, source)
        assert merged.sshKey is not None
        self.assertEqual(merged.sshKey.keyFingerprint, "fp1")
        self.assertEqual(merged.sshKey.privateKey, "priv")
        self.assertEqual(merged.sshKey.publicKey, "pub")

    def test_collections_merge(self):
        target = BwItem(id="t", type=1, name="GitHub", collectionIds=["c1"],
                        login=LoginData(uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"))
        source = BwItem(id="s", type=1, name="GitHub", collectionIds=["c2", "c1"],
                        login=LoginData(uris=[], username="alice", password="secret"))
        merged, _backfilled = merge_items(target, source)
        self.assertEqual(set(merged.collectionIds or []), {"c1", "c2"})

    def test_folder_merge(self):
        target = BwItem(id="t", type=1, name="GitHub", folderId="f1",
                        login=LoginData(uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"))
        source = BwItem(id="s", type=1, name="GitHub", folderId="f2",
                        login=LoginData(uris=[], username="alice", password="secret"))
        merged, _backfilled = merge_items(target, source)
        self.assertEqual(merged.folderId, "f1")
        self.assertIn("conflicts", _backfilled)
        self.assertIn("f2", merged.notes or "")


class TestFindDuplicates(unittest.TestCase):
    def test_find_login_duplicates(self):
        a = BwItem(id="a", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"
        ))
        b = BwItem(id="b", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"
        ))
        c = BwItem(id="c", type=1, name="Twitter", login=LoginData(
            uris=[UriEntry(uri="https://twitter.com")], username="alice", password="secret"
        ))
        items: list[BwItem] = [a, b, c]
        clusters, _ = find_duplicates_by_type(items, threshold=0.85)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 2)

    def test_no_false_positives(self):
        a = BwItem(id="a", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"
        ))
        b = BwItem(id="b", type=1, name="Twitter", login=LoginData(
            uris=[UriEntry(uri="https://twitter.com")], username="bob", password="other"
        ))
        items: list[BwItem] = [a, b]
        clusters, _ = find_duplicates_by_type(items, threshold=0.85)
        self.assertEqual(len(clusters), 0)

    def test_no_monster_cluster(self):
        """Same username+password across many different domains must NOT collapse into one cluster."""
        items: list[BwItem] = []
        for i in range(60):
            items.append(BwItem(
                id=f"item{i}", type=1, name=f"Site {i}",
                login=LoginData(
                    uris=[UriEntry(uri=f"https://site{i}.com")],
                    username="alice", password="secret"
                )
            ))
        clusters, _ = find_duplicates_by_type(items, threshold=0.85)
        # Should find 0 clusters because each has a different domain and name
        self.assertEqual(len(clusters), 0)

    def test_notes_substring_concat(self):
        """Notes that are substrings of target notes must still be concatenated."""
        target = BwItem(id="t", type=1, name="GitHub", notes="Note about GitHub", login=LoginData())
        source = BwItem(id="s", type=1, name="GitHub", notes="GitHub", login=LoginData())
        merged, _backfilled = merge_items(target, source)
        self.assertIn("Note about GitHub", merged.notes or "")
        self.assertIn("GitHub", merged.notes or "")
        self.assertIn("notes", _backfilled)

    def test_backfill_accumulation(self):
        """Merging multiple secondaries must accumulate numeric backfill counters."""
        target = BwItem(id="t", type=1, name="GitHub", login=LoginData(
            uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"
        ))
        # Each secondary adds 1 custom field
        s1 = BwItem(id="s1", type=1, name="GitHub", fields=[{"name": "f1", "value": "v1"}], login=LoginData())
        s2 = BwItem(id="s2", type=1, name="GitHub", fields=[{"name": "f2", "value": "v2"}], login=LoginData())
        s3 = BwItem(id="s3", type=1, name="GitHub", fields=[{"name": "f3", "value": "v3"}], login=LoginData())
        target, bf1 = merge_items(target, s1)
        self.assertEqual(bf1.get("fields"), 1)
        target, bf2 = merge_items(target, s2)
        self.assertEqual(bf2.get("fields"), 1)
        target, bf3 = merge_items(target, s3)
        self.assertEqual(bf3.get("fields"), 1)
        # Verify target has all 3 fields
        self.assertEqual(len(target.fields or []), 3)


class TestRoundTrip(unittest.TestCase):
    def test_bw_item_roundtrip(self):
        raw: dict[str, Any] = {  # type: ignore[type-arg]
            "id": "abc-123",
            "type": 1,
            "name": "GitHub",
            "notes": "My note",
            "favorite": True,
            "reprompt": 0,
            "login": {
                "uris": [{"match": None, "uri": "https://github.com"}],
                "username": "alice",
                "password": "secret",
                "totp": "totp123",
            },
            "collectionIds": ["col1"],
            "folderId": "fold1",
            "organizationId": "org1",
            "passwordHistory": [{"lastUsedDate": "2024-01-01", "password": "old"}],
            "revisionDate": "2024-01-01T00:00:00.000Z",
            "creationDate": "2023-01-01T00:00:00.000Z",
        }
        item = BwItem.from_dict(raw)
        out = item.to_dict()
        self.assertEqual(out["id"], "abc-123")
        assert out["login"] is not None
        self.assertEqual(out["login"]["username"], "alice")
        self.assertEqual(out["collectionIds"], ["col1"])
        self.assertEqual(out["folderId"], "fold1")
        self.assertEqual(out["organizationId"], "org1")
        self.assertEqual(out["passwordHistory"][0]["password"], "old")
        self.assertEqual(out["revisionDate"], "2024-01-01T00:00:00.000Z")

    def test_empty_login_not_emitted(self):
        raw: dict[str, Any] = {"id": "x", "type": 2, "name": "Note", "secureNote": {"type": 0}}  # type: ignore[type-arg]
        item = BwItem.from_dict(raw)
        out = item.to_dict()
        self.assertNotIn("login", out)
        self.assertNotIn("sshKey", out)


class TestBackupAndLog(unittest.TestCase):
    def test_backup(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"items":[]}')
            path = Path(f.name)
        backup: Path | None = None
        try:
            backup = create_backup(path)
            self.assertTrue(backup.exists())
            self.assertIn(".original.", backup.name)
        finally:
            path.unlink(missing_ok=True)
            if backup is not None:
                backup.unlink(missing_ok=True)

    def test_merge_log(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.json"
            rec = MergeRecord(
                cluster_id=1,
                primary=BwItem(id="p", type=1, name="GitHub", login=LoginData()),
                merged=[BwItem(id="m", type=1, name="GitHub", login=LoginData())],
                new_uris=["https://github.com"],
                backfilled={"totp": True},
            )
            log_path = create_merge_log([rec], out_path)
            self.assertTrue(log_path.exists())
            data = json.loads(log_path.read_text())
            self.assertEqual(data[0]["cluster_id"], 1)
            self.assertEqual(data[0]["backfilled"], {"totp": True})


class TestHTMLReport(unittest.TestCase):
    def test_generates(self):
        with tempfile.TemporaryDirectory() as td:
            rec = MergeRecord(
                cluster_id=1,
                primary=BwItem(id="p", type=1, name="GitHub", login=LoginData(
                    uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"
                )),
                merged=[BwItem(id="m", type=1, name="GitHub", login=LoginData())],
                new_uris=["https://github.com"],
                backfilled={"totp": True},
            )
            report_path = Path(td) / "report.html"
            generate_html_report(
                records=[rec],
                stats={"original": 2, "final": 1, "merged": 1, "clusters": 1},
                threshold=0.85,
                filename="test.json",
                output_path=report_path,
            )
            self.assertTrue(report_path.exists())
            self.assertGreater(report_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
