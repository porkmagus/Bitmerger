"""Regression tests for import-shaped 1PUX and companion CSV outputs."""

from __future__ import annotations

import base64
import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from bitmerger.core import BwItem, LoginData, UriEntry
from bitmerger.vault_formats import merge_vaults, save_1password


class TestMergeExportSummary(unittest.TestCase):
    def test_generated_1pux_uses_1password_style_ids_and_retains_totp_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cleaned.1pux"
            item = BwItem(
                id="source-login",
                type=1,
                name="Example",
                login=LoginData(
                    username="alice",
                    password="secret",
                    totp="otpauth://totp/Example?secret=JBSWY3DPEHPK3PXP",
                    uris=[UriEntry(uri="https://example.com")],
                ),
            )
            save_1password(output, [item])

            with zipfile.ZipFile(output) as archive:
                data = json.loads(archive.read("export.data"))
            account = data["accounts"][0]
            vault = account["vaults"][0]
            exported = vault["items"][0]

            # 1Password exports use unpadded base32 IDs, not RFC 4122 UUID strings.
            for value in (account["attrs"]["uuid"], vault["attrs"]["uuid"], exported["uuid"]):
                self.assertEqual(len(value), 26)
                base64.b32decode(value.upper() + "======")
            fields = exported["details"]["sections"][0]["fields"]
            self.assertIn("otpauth://totp/Example?secret=JBSWY3DPEHPK3PXP", [field["value"]["concealed"] for field in fields])

    def test_merge_writes_login_csv_and_auditable_preservation_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitwarden = root / "bitwarden.json"
            bitwarden.write_text(json.dumps({"items": [{
                "id": "bw-login", "type": 1, "name": "Example",
                "login": {
                    "username": "alice", "password": "secret",
                    "totp": "otpauth://totp/Example?secret=JBSWY3DPEHPK3PXP",
                    "fido2Credentials": [
                        {"credentialId": "credential-1", "keyType": "public-key", "userHandle": "user-1"},
                        {"credentialId": "credential-2", "keyType": "public-key", "userHandle": "user-2"},
                    ],
                    "uris": [{"uri": "https://example.com"}],
                },
            }]}), encoding="utf-8")
            onepassword = root / "source.1pux"
            save_1password(onepassword, [])

            result = merge_vaults(bitwarden, onepassword, root / "output")

            self.assertTrue(result.csv_output.is_file())
            self.assertEqual(result.totp_count, 1)
            self.assertEqual(result.passkey_count, 2)
            self.assertEqual(result.password_login_count, 1)
            self.assertTrue(result.passkey_recovery_output.is_file())
            with result.csv_output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Title"], "Example")
            self.assertEqual(rows[0]["OTPAuth"], "otpauth://totp/Example?secret=JBSWY3DPEHPK3PXP")
            self.assertNotIn("credential-1", result.csv_output.read_text(encoding="utf-8"))
            with zipfile.ZipFile(result.onepassword_output) as archive:
                onepassword_data = archive.read("export.data").decode("utf-8")
            self.assertNotIn("credential-1", onepassword_data)
            recovery = json.loads(result.passkey_recovery_output.read_text(encoding="utf-8"))
            self.assertEqual(recovery["items"][0]["login"]["fido2Credentials"], [
                {"credentialId": "credential-1", "keyType": "public-key", "userHandle": "user-1"},
                {"credentialId": "credential-2", "keyType": "public-key", "userHandle": "user-2"},
            ])
            report = json.loads(result.report_output.read_text(encoding="utf-8"))
            self.assertNotIn("credential-1", result.report_output.read_text(encoding="utf-8"))
            self.assertEqual(report["preservation"]["totp_codes"], 1)
            self.assertEqual(report["preservation"]["passkeys"], 2)
            self.assertEqual(report["preservation"]["password_login_entries"], 1)
            migration = report["passkey_migration"]
            self.assertEqual(migration["status"], "manual_passkey_transfer_required")
            self.assertEqual(migration["credential_count"], 2)
            self.assertEqual(len(migration["credential_fingerprints"]), 2)
            self.assertEqual(migration["recovery_artifact"], str(result.passkey_recovery_output))

    def test_failed_overwrite_restores_the_complete_previous_output_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitwarden = root / "bitwarden.json"
            bitwarden.write_text(json.dumps({"items": [{
                "id": "bw-login", "type": 1, "name": "Example",
                "login": {"username": "alice", "password": "old", "uris": [{"uri": "https://example.com"}]},
            }]}), encoding="utf-8")
            onepassword = root / "source.1pux"
            save_1password(onepassword, [])
            output_dir = root / "output"
            first = merge_vaults(bitwarden, onepassword, output_dir)
            outputs = [first.bitwarden_output, first.onepassword_output, first.csv_output, first.passkey_recovery_output, first.report_output]
            before = {path.name: path.read_bytes() for path in outputs}

            bitwarden.write_text(json.dumps({"items": [{
                "id": "bw-login", "type": 1, "name": "Example",
                "login": {"username": "alice", "password": "new", "uris": [{"uri": "https://example.com"}]},
            }]}), encoding="utf-8")
            real_replace = Path.replace

            def fail_when_publishing_1pux(source: Path, target: Path) -> Path:
                if source.parent.name.startswith(".bitmerger-staging-") and source.name == "bitmerger-merged.1password.1pux" and target.name == "bitmerger-merged.1password.1pux":
                    raise OSError("simulated publication failure")
                return real_replace(source, target)

            with patch.object(Path, "replace", fail_when_publishing_1pux):
                with self.assertRaisesRegex(OSError, "simulated publication failure"):
                    merge_vaults(bitwarden, onepassword, output_dir, overwrite=True)
            self.assertEqual({path.name: path.read_bytes() for path in outputs}, before)


if __name__ == "__main__":
    unittest.main()
