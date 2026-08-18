"""End-to-end tests for the visible Bitwarden + 1Password merge mode."""

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from bitmerger.core import BwItem, LoginData, UriEntry
from bitmerger.gui import MainWindow
from bitmerger.vault_formats import save_1password


@pytest.fixture
def dual_sources(tmp_path: Path):
    bitwarden_path = tmp_path / "bitwarden.json"
    bitwarden_path.write_text(json.dumps({
        "encrypted": False,
        "items": [{
            "id": "bw-login", "type": 1, "name": "Example", "favorite": False,
            "login": {"username": "alice", "password": "secret", "uris": [{"uri": "https://example.com"}]},
        }],
    }), encoding="utf-8")
    onepassword_path = tmp_path / "onepassword.1pux"
    save_1password(onepassword_path, [
        BwItem(id="1p-login", type=1, name="Example", login=LoginData(
            username="alice", password="secret", uris=[UriEntry(uri="https://example.com")],
        )),
    ])
    return bitwarden_path, onepassword_path, tmp_path / "output"


def test_merge_tab_runs_end_to_end(qtbot, monkeypatch, dual_sources):
    bitwarden_path, onepassword_path, output_dir = dual_sources
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    window = MainWindow()
    qtbot.add_widget(window)
    window._dual_bw_path.setText(str(bitwarden_path))
    window._dual_1p_path.setText(str(onepassword_path))
    window._dual_output_dir.setText(str(output_dir))
    window._on_dual_merge()

    qtbot.waitUntil(lambda: (output_dir / "bitmerger-merged.report.json").exists(), timeout=5000)
    qtbot.waitUntil(window._dual_merge_button.isEnabled, timeout=5000)
    assert (output_dir / "bitmerger-merged.bitwarden.json").is_file()
    assert (output_dir / "bitmerger-merged.1password.1pux").is_file()
    assert "Merged 1 safe duplicate" in window._dual_result.toPlainText()


def test_merge_tab_uses_optional_csv_for_totp_enrichment(qtbot, monkeypatch, dual_sources):
    bitwarden_path, onepassword_path, output_dir = dual_sources
    csv_path = onepassword_path.with_suffix(".csv")
    csv_path.write_text("Title,Url,Username,Password,OTPAuth,Favorite,Archived,Tags,Notes\nExample,https://example.com,alice,secret,otpauth://totp/Example?secret=JBSWY3DPEHPK3PXP,FALSE,FALSE,,\n", encoding="utf-8")
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    window = MainWindow()
    qtbot.add_widget(window)
    window._dual_bw_path.setText(str(bitwarden_path))
    window._dual_1p_path.setText(str(onepassword_path))
    window._dual_csv_path.setText(str(csv_path))
    window._dual_output_dir.setText(str(output_dir))
    window._on_dual_merge()
    qtbot.waitUntil(lambda: (output_dir / "bitmerger-merged.report.json").exists(), timeout=5000)
    output = json.loads((output_dir / "bitmerger-merged.bitwarden.json").read_text(encoding="utf-8"))
    assert output["items"][0]["login"]["totp"].startswith("otpauth://totp/")

def test_merge_tab_refuses_existing_output_without_replace_confirmation(qtbot, monkeypatch, dual_sources):
    bitwarden_path, onepassword_path, output_dir = dual_sources
    output_dir.mkdir()
    (output_dir / "bitmerger-merged.bitwarden.json").write_text("keep-me", encoding="utf-8")
    calls = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: calls.append(args[1]) or QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    window = MainWindow()
    qtbot.add_widget(window)
    window._dual_bw_path.setText(str(bitwarden_path))
    window._dual_1p_path.setText(str(onepassword_path))
    window._dual_output_dir.setText(str(output_dir))
    window._on_dual_merge()

    assert (output_dir / "bitmerger-merged.bitwarden.json").read_text(encoding="utf-8") == "keep-me"
    assert any("Replace" in title for title in calls)
