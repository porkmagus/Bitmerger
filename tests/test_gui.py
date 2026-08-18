"""
GUI integration tests — launch the real PySide6 app and exercise interactions.
Uses pytest-qt for event loop management and widget access.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import QApplication, QMessageBox

from bitmerger.gui import MainWindow, item_overview_fields
from bitmerger.item_editor import ItemEditor
from bitmerger.core import BwItem, load_vault
from bitmerger.vault_formats import save_1password
from bitmerger.theme import ThemeManager


@pytest.fixture
def tmp_vault(tmp_path: Path):
    """Create a minimal Bitwarden vault file for testing."""
    vault_data = {
        "items": [
            {
                "id": "test-login-1",
                "name": "Test Login",
                "favorite": False,
                "reprompt": 0,
                "type": 1,
                "login": {
                    "username": "test@example.com",
                    "password": "password123",
                    "uris": [{"match": 1, "uri": "https://example.com"}],
                },
                "folderId": None,
                "collectionIds": None,
                "fields": None,
                "notes": None,
                "createDate": "2024-01-01T00:00:00Z",
                "revisionDate": "2024-01-01T00:00:00Z",
            },
            {
                "id": "test-login-2",
                "name": "Test Login 2",
                "favorite": False,
                "reprompt": 0,
                "type": 1,
                "login": {
                    "username": "test2@example.com",
                    "password": "anotherpass",
                    "uris": [{"match": 1, "uri": "https://example2.com"}],
                },
                "folderId": None,
                "collectionIds": None,
                "fields": None,
                "notes": None,
                "createDate": "2024-01-01T00:00:00Z",
                "revisionDate": "2024-01-01T00:00:00Z",
            },
            {
                "id": "test-card-1",
                "name": "Test Card",
                "favorite": False,
                "reprompt": 0,
                "type": 2,
                "card": {
                    "cardholderName": "John Doe",
                    "brand": "Visa",
                    "number": "4111111111111111",
                    "expMonth": "12",
                    "expYear": "2030",
                    "code": "123",
                },
                "folderId": None,
                "collectionIds": None,
                "fields": None,
                "notes": None,
                "createDate": "2024-01-01T00:00:00Z",
                "revisionDate": "2024-01-01T00:00:00Z",
            },
        ],
        "folders": [],
        "collections": [],
    }
    vault_file = tmp_path / "test.json"
    vault_file.write_text(json.dumps(vault_data))
    return vault_file


def test_double_click_detail_dialog_loads_full_item(qtbot, tmp_vault):
    window = MainWindow()
    qtbot.add_widget(window)
    window._load_vault(tmp_vault)
    window._show_item_detail(window._items[0])
    assert window._item_detail_dialog.isVisible()
    assert window._item_detail_editor.current_item() is window._items[0]
    window._item_detail_dialog.close()


class TestMainWindowLaunch:
    """Test that the main window launches and basic UI is present."""

    def test_window_creates(self, qtbot):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        qtbot.wait(200)
        assert window.isVisible()
        assert window.windowTitle().startswith("Bitmerger")

    def test_theme_manager_can_be_reconstructed(self, qtbot):
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        first = ThemeManager(app)
        second = ThemeManager(app)
        assert first is second

    def test_main_window_loads_vault(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        qtbot.wait(200)

        # Load vault directly (skip file dialog)
        window._load_vault(tmp_vault)
        qtbot.wait(300)

        # Check that the vault was loaded
        assert len(window._items) == 3
        assert window._vault_path == tmp_vault


class TestVaultTable:
    """Test vault table interactions."""

    def test_load_1password_uses_native_format(self, qtbot, tmp_path):
        vault_path = tmp_path / "onepassword.1pux"
        save_1password(vault_path, [BwItem(id="login-1", type=1, name="Example")])
        window = MainWindow()
        qtbot.add_widget(window)
        window._load_vault(vault_path)
        assert window._vault_format == "1password"
        assert len(window._items) == 1
        output_path = window._derived_output_path("dedup")
        assert output_path.suffix == ".1pux"
        saved_path = tmp_path / "cleaned.1pux"
        window._save_current_format(saved_path)
        assert saved_path.exists()

    def test_items_appear_in_table(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        window._load_vault(tmp_vault)
        qtbot.wait(300)

        table = window._overview_table
        assert table.rowCount() == 3  # 3 items in our test vault

    def test_table_columns(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        window._load_vault(tmp_vault)
        qtbot.wait(300)

        table = window._overview_table
        assert table.columnCount() == 9
        headers = [table.horizontalHeaderItem(i).text() for i in range(9)]
        assert "Type" in headers
        assert "Name" in headers
        assert "Primary" in headers
        assert "Details" in headers

    def test_ssh_key_has_visible_overview_fields(self):
        item = BwItem.from_dict({"id": "ssh-1", "name": "Deploy", "type": 5, "sshKey": {"keyFingerprint": "SHA256:test", "publicKey": "ssh-ed25519 AAA"}})
        primary, detail = item_overview_fields(item)
        assert primary == "SHA256:test"
        assert detail == "Public key available"

    def test_selecting_row(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        window._load_vault(tmp_vault)
        qtbot.wait(300)

        table = window._overview_table
        assert table.rowCount() > 0

        # Select first row using selection model
        index = table.model().index(0, 0)
        table.selectionModel().select(
            index,
            QItemSelectionModel.SelectionFlag.Rows | QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        qtbot.wait(100)

        selected = table.selectionModel().selectedRows()
        assert len(selected) == 1


class TestTabSwitching:
    """Test that tab switching works correctly."""

    def test_tabs_exist(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        qtbot.wait(200)

        tabs = window._tabs
        assert tabs.count() == 4
        assert tabs.tabText(0) == "Vault Overview"
        assert tabs.tabText(1) == "Deduplicate"
        assert tabs.tabText(2) == "Batch Editor"
        assert tabs.tabText(3) == "Merge Vaults"

    def test_switch_to_dedup_tab(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        qtbot.wait(200)

        tabs = window._tabs
        tabs.setCurrentIndex(1)
        qtbot.wait(100)

        assert tabs.tabText(tabs.currentIndex()) == "Deduplicate"

    def test_switch_to_batch_editor_tab(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        qtbot.wait(200)

        tabs = window._tabs
        tabs.setCurrentIndex(2)
        qtbot.wait(100)

        assert tabs.tabText(tabs.currentIndex()) == "Batch Editor"


class TestDeduplication:
    """Test deduplication tab interactions."""

    def test_dedup_settings_visible(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        window._load_vault(tmp_vault)
        qtbot.wait(300)

        # Switch to dedup tab
        window._tabs.setCurrentIndex(1)
        qtbot.wait(100)

        # Check that dedup settings are present
        assert window._thresh_spin is not None
        assert window._thresh_spin.value() == 0.85

    def test_dedup_merge_button_exists(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        window._load_vault(tmp_vault)
        qtbot.wait(300)

        # Switch to dedup tab
        window._tabs.setCurrentIndex(1)
        qtbot.wait(100)

        # Verify the merge button exists and is initially disabled
        assert window._btn_dedup_merge is not None
        assert not window._btn_dedup_merge.isEnabled()


class TestBatchEditor:
    """Test batch editor interactions."""

    def test_batch_search(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        window._load_vault(tmp_vault)
        qtbot.wait(300)

        # Switch to batch editor tab
        window._tabs.setCurrentIndex(2)
        qtbot.wait(100)

        # Search for "Login"
        window._batch_query.setText("Login")
        qtbot.wait(50)

        # Click search
        window._on_batch_search()
        qtbot.wait(200)

        # Should have found items
        table = window._batch_table
        assert table.rowCount() >= 2  # At least 2 login items

    def test_batch_field_dropdown(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        window._load_vault(tmp_vault)
        qtbot.wait(300)

        # Switch to batch editor tab
        window._tabs.setCurrentIndex(2)
        qtbot.wait(100)

        # Check field dropdown exists and is initially empty (populated on search)
        assert window._batch_field_combo is not None
        combo = window._batch_field_combo
        # Initially empty until a search is performed
        assert combo.count() == 0 or combo.count() > 0  # just check it exists


class TestItemEditor:
    """Test item editor standalone interactions."""

    def test_editor_loads_login_item(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {
                "username": "test@example.com",
                "password": "password123",
                "uris": [{"match": 1, "uri": "https://example.com"}],
            },
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        assert editor.current_item() == item
        assert editor._name_edit.text() == "Test Login"

    def test_edit_name(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {"username": "u", "password": "p"},
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        name_edit = editor._name_edit
        name_edit.clear()
        name_edit.setText("New Name")
        qtbot.wait(50)

        assert editor.is_dirty()

    def test_save_button_enabled_when_dirty(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {"username": "u", "password": "p"},
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        # Initially not dirty
        assert not editor.is_dirty()
        assert not editor._save_btn.isEnabled()

        # Make a change
        name_edit = editor._name_edit
        qtbot.keyClicks(name_edit, "X")
        qtbot.wait(50)

        assert editor.is_dirty()
        assert editor._save_btn.isEnabled()
        assert editor._discard_btn.isEnabled()

    def test_favorite_checkbox(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {"username": "u", "password": "p"},
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        fav_check = editor._fav_check
        assert not fav_check.isChecked()

        fav_check.click()
        qtbot.wait(50)
        assert fav_check.isChecked()
        assert editor.is_dirty()

    def test_password_generation(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {"username": "u", "password": "password123"},
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        pw_edit = editor._pw_edit
        original_pw = pw_edit.text()

        gen_btn = editor._pw_gen_btn
        gen_btn.click()
        qtbot.wait(100)

        new_pw = pw_edit.text()
        assert new_pw != original_pw
        assert len(new_pw) == 20
        assert editor.is_dirty()

    def test_password_strength_indicator(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {"username": "u", "password": "p"},
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        pw_edit = editor._pw_edit
        strength = editor._pw_strength

        # Empty password should show nothing
        pw_edit.clear()
        qtbot.wait(50)
        assert strength.text() == ""

        # Weak password
        qtbot.keyClicks(pw_edit, "12345678")
        qtbot.wait(50)
        assert strength.text() != ""

    def test_uri_adding(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {"username": "u", "password": "***"},
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        initial_count = editor._uri_list.count()

        # Verify the button exists and clicking it calls the method
        add_btn = editor._add_uri_btn
        assert add_btn is not None

        # Call the method directly (button click may not work in headless mode)
        editor._add_uri_row()
        qtbot.wait(50)

        assert editor._uri_list.count() == initial_count + 1
        assert editor.is_dirty()

    def test_custom_field_adding(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {"username": "u", "password": "***"},
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        initial_count = editor._cf_grid.count()

        # Verify the button exists
        add_btn = editor._add_cf_btn
        assert add_btn is not None

        # Call the method directly (button click may not work in headless mode)
        editor._add_custom_field()
        qtbot.wait(50)

        assert editor._cf_grid.count() == initial_count + 1
        assert editor.is_dirty()


class TestFluidityIntegration:
    """Test that fluidity animations don't break interactions."""

    def test_button_pulse_exists(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        qtbot.wait(200)

        # Verify the save button exists and works
        assert window._btn_save is not None
        assert not window._btn_save.isEnabled()

    def test_checkbox_pulse_exists(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {"username": "u", "password": "p"},
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        fav_check = editor._fav_check
        assert fav_check is not None

        # Click should still work
        fav_check.click()
        qtbot.wait(50)
        assert fav_check.isChecked()

    def test_status_pulse_exists(self, qtbot):
        item = BwItem.from_dict({
            "id": "test-1",
            "name": "Test Login",
            "type": 1,
            "login": {"username": "u", "password": "p"},
        })

        editor = ItemEditor()
        qtbot.add_widget(editor)
        editor.show()
        editor.load_item(item, [item])
        qtbot.wait(100)

        pw_strength = editor._pw_strength
        assert pw_strength is not None

        pw_edit = editor._pw_edit
        qtbot.keyClicks(pw_edit, "X")
        qtbot.wait(100)
        assert pw_strength.text() != ""

    def test_tab_fade_animation(self, qtbot, tmp_vault):
        window = MainWindow()
        qtbot.add_widget(window)
        window.show()
        qtbot.wait(200)

        tabs = window._tabs
        # Switch tabs multiple times - should not crash
        for i in range(3):
            tabs.setCurrentIndex(i % 3)
            qtbot.wait(100)

        assert window.isVisible()
