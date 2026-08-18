"""Tests for Bitwarden ↔ 1Password 1PUX compatibility and dual-vault merge."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bitmerger.core import BwItem, LoginData, UriEntry
from bitmerger.vault_formats import (
    VaultFormatError,
    detect_vault_format,
    load_document,
    merge_vaults,
    save_1password,
)


def write_1pux(path: Path, items: list[dict], *, attachment: bool = False) -> None:
    export_data = {
        "accounts": [{
            "attrs": {"accountName": "Test", "name": "Test", "uuid": "account-1", "domain": ""},
            "vaults": [{"attrs": {"uuid": "vault-1", "name": "Personal", "type": "P"}, "items": items}],
        }]
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("export.attributes", json.dumps({"version": 3, "description": "1Password Unencrypted Export", "createdAt": 1}))
        archive.writestr("export.data", json.dumps(export_data))
        if attachment:
            archive.writestr("files/example.txt", "not secret test content")


class Test1PasswordFormat(unittest.TestCase):
    def test_load_1pux_login_preserves_portable_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.1pux"
            write_1pux(path, [{
                "uuid": "login-1", "favIndex": 1, "categoryUuid": "001", "state": "active",
                "overview": {"title": "GitHub", "url": "https://github.com", "urls": [{"label": "", "url": "https://github.com"}], "tags": ["work"]},
                "details": {
                    "notesPlain": "important", "loginFields": [
                        {"designation": "username", "value": "alice"}, {"designation": "password", "value": "secret"},
                    ],
                    "sections": [{"title": "Recovery", "fields": [{"title": "backup code", "value": {"concealed": "code-123"}}]}],
                },
            }])
            document = load_document(path)
            self.assertEqual(document.format, "1password")
            self.assertEqual(len(document.items), 1)
            item = document.items[0]
            self.assertEqual(item.type, 1)
            self.assertEqual(item.name, "GitHub")
            self.assertTrue(item.favorite)
            self.assertIsNotNone(item.login)
            assert item.login is not None
            self.assertEqual(item.login.username, "alice")
            self.assertEqual(item.login.password, "secret")
            self.assertEqual(item.login.uris[0].uri, "https://github.com")
            self.assertIsNotNone(item.fields)
            assert item.fields is not None
            self.assertEqual(item.fields[0]["value"], "code-123")

    def test_1pux_round_trip_is_a_valid_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cleaned.1pux"
            original = BwItem(
                id="bw-1", type=1, name="GitHub", favorite=True, notes="n",
                fields=[{"name": "backup", "value": "abc", "type": 1}, {"name": "1Password tag", "value": "work", "type": 0}],
                login=LoginData(uris=[UriEntry(uri="https://github.com")], username="alice", password="secret"),
            )
            save_1password(path, [original])
            self.assertEqual(detect_vault_format(path), "1password")
            loaded = load_document(path)
            self.assertEqual(len(loaded.items), 1)
            item = loaded.items[0]
            self.assertEqual(item.name, "GitHub")
            assert item.login is not None
            self.assertEqual(item.login.username, "alice")
            self.assertEqual(item.login.password, "secret")
            self.assertIsNotNone(item.fields)
            assert item.fields is not None
    def test_attachment_warning_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.1pux"
            write_1pux(path, [], attachment=True)
            document = load_document(path)
            self.assertTrue(any("attachment" in warning for warning in document.warnings))

    def test_rejects_non_vault_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-a-vault.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("hello.txt", "hello")
            with self.assertRaises(VaultFormatError):
                detect_vault_format(path)


class TestDualVaultMerge(unittest.TestCase):
    def test_merges_same_login_and_outputs_both_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitwarden = root / "bitwarden.json"
            bitwarden.write_text(json.dumps({"folders": [], "items": [{
                "id": "bw-1", "type": 1, "name": "GitHub", "favorite": False,
                "login": {"uris": [{"uri": "https://github.com"}], "username": "alice", "password": "secret"},
            }]}), encoding="utf-8")
            onepassword = root / "onepassword.1pux"
            write_1pux(onepassword, [{
                "uuid": "1p-1", "favIndex": 1, "categoryUuid": "001", "state": "active",
                "overview": {"title": "GitHub", "url": "https://github.com", "urls": [{"label": "", "url": "https://github.com"}]},
                "details": {"loginFields": [{"designation": "username", "value": "alice"}, {"designation": "password", "value": "secret"}]},
            }])
            result = merge_vaults(bitwarden, onepassword, root / "output")
            self.assertEqual(result.input_count, 2)
            self.assertEqual(result.output_count, 1)
            self.assertEqual(result.merged_count, 1)
            self.assertTrue(result.bitwarden_output.is_file())
            self.assertTrue(result.onepassword_output.is_file())
            self.assertTrue(result.report_output.is_file())
            bw_document = load_document(result.bitwarden_output)
            op_document = load_document(result.onepassword_output)
            self.assertEqual(len(bw_document.items), 1)
            self.assertEqual(len(op_document.items), 1)
            self.assertTrue(bw_document.items[0].favorite)

    def test_refuses_existing_outputs_without_explicit_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitwarden = root / "bitwarden.json"
            bitwarden.write_text(json.dumps({"items": []}), encoding="utf-8")
            onepassword = root / "onepassword.1pux"
            write_1pux(onepassword, [])
            output = root / "output"
            output.mkdir()
            existing = output / "bitmerger-merged.bitwarden.json"
            existing.write_text("do-not-replace", encoding="utf-8")
            with self.assertRaises(VaultFormatError):
                merge_vaults(bitwarden, onepassword, output)
            self.assertEqual(existing.read_text(encoding="utf-8"), "do-not-replace")

    def test_never_allows_an_output_to_replace_a_selected_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitwarden = root / "bitmerger-merged.bitwarden.json"
            original = json.dumps({"items": []})
            bitwarden.write_text(original, encoding="utf-8")
            onepassword = root / "source.1pux"
            write_1pux(onepassword, [])
            with self.assertRaises(VaultFormatError):
                merge_vaults(bitwarden, onepassword, root, overwrite=True)
            self.assertEqual(bitwarden.read_text(encoding="utf-8"), original)

    def test_does_not_merge_distinct_passwords(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitwarden = root / "bitwarden.json"
            bitwarden.write_text(json.dumps({"items": [{"id": "a", "type": 1, "name": "GitHub", "login": {"uris": [{"uri": "https://github.com"}], "username": "alice", "password": "old"}}]}), encoding="utf-8")
            onepassword = root / "onepassword.1pux"
            write_1pux(onepassword, [{"uuid": "b", "categoryUuid": "001", "overview": {"title": "GitHub", "urls": [{"url": "https://github.com"}]}, "details": {"loginFields": [{"designation": "username", "value": "alice"}, {"designation": "password", "value": "new"}]}}])
            result = merge_vaults(bitwarden, onepassword, root / "output")
            self.assertEqual(result.output_count, 2)
            self.assertEqual(result.merged_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
