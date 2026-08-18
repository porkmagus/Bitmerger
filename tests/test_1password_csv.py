"""1Password CSV login/TOTP enrichment tests."""

import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bitmerger.vault_formats import load_document, merge_vaults


class Test1PasswordCsv(unittest.TestCase):
    def _write_csv(self, path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Title", "Url", "Username", "Password", "OTPAuth", "Favorite", "Archived", "Tags", "Notes"])
            writer.writeheader()
            writer.writerow({"Title": "Example", "Url": "https://example.com", "Username": "alice", "Password": "secret", "OTPAuth": "otpauth://totp/Example?secret=JBSWY3DPEHPK3PXP", "Favorite": "TRUE", "Archived": "TRUE", "Tags": "work;important", "Notes": "csv note"})

    def _write_1pux(self, path: Path) -> None:
        data = {"accounts": [{"attrs": {"uuid": "account"}, "vaults": [{"attrs": {"uuid": "vault", "name": "Personal"}, "items": [{"uuid": "item", "favIndex": 0, "state": "active", "categoryUuid": "001", "overview": {"title": "Example", "urls": [{"url": "https://example.com"}], "tags": []}, "details": {"loginFields": [{"value": "alice", "designation": "username"}, {"value": "secret", "designation": "password"}], "notesPlain": ""}}]}]}]}
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("export.attributes", json.dumps({"version": 3}))
            archive.writestr("export.data", json.dumps(data))

    def test_csv_maps_otpauth_and_login_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vault.csv"
            self._write_csv(path)
            document = load_document(path)
            self.assertEqual(document.format, "1password_csv")
            self.assertEqual(len(document.items), 1)
            item = document.items[0]
            assert item.login is not None
            self.assertTrue(item.favorite)
            assert item.login.totp is not None
            self.assertTrue(item.login.totp.startswith("otpauth://totp/"))
            self.assertIn({"name": "1Password state", "value": "archived", "type": 0}, item.fields or [])
            self.assertEqual(sum(field["name"] == "1Password tag" for field in item.fields or []), 2)

    def test_csv_enriches_matching_1pux_login_with_totp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitwarden = root / "bitwarden.json"
            bitwarden.write_text(json.dumps({"items": []}), encoding="utf-8")
            onepassword = root / "vault.1pux"
            csv_path = root / "vault.csv"
            self._write_1pux(onepassword)
            self._write_csv(csv_path)
            result = merge_vaults(bitwarden, onepassword, root / "output", onepassword_csv_path=csv_path)
            merged = json.loads(result.bitwarden_output.read_text(encoding="utf-8"))["items"]
            self.assertEqual(len(merged), 1)
            self.assertTrue(merged[0]["login"]["totp"].startswith("otpauth://totp/"))


if __name__ == "__main__":
    unittest.main()
