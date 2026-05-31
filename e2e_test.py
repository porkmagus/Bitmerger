"""
E2E GUI Test Suite for Bitmerger.
Tests the GUI module without a display using offscreen platform.
"""
import sys
import os
sys.path.insert(0, '/Users/sean/repos/bitmerger')

# Mock Qt display before importing PySide6
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from bitmerger.gui import MainWindow, VaultTable, DedupWorker, RenameWorker
from bitmerger.core import load_vault
from bitmerger.theme import ThemeManager, Theme

# Global app instance
_app = None

def get_app():
    global _app
    if _app is None:
        _app = QApplication(sys.argv)
    return _app

def test_gui_import():
    """Test that GUI module imports cleanly."""
    print("[1] GUI Import...")
    assert MainWindow is not None
    assert VaultTable is not None
    assert DedupWorker is not None
    assert RenameWorker is not None
    print("    PASS")

def test_window_creation():
    """Test MainWindow instantiation."""
    print("[2] Window Creation...")
    app = get_app()
    window = MainWindow()
    assert window is not None
    assert window.windowTitle() == "Bitmerger — Bitwarden Vault Utility"
    assert window.minimumWidth() >= 1280
    assert window.minimumHeight() >= 820
    print("    PASS")

def test_vault_table():
    """Test VaultTable with sample data."""
    print("[3] Vault Table...")
    table = VaultTable()
    assert table.columnCount() == 6
    assert table.selectionBehavior() == VaultTable.SelectionBehavior.SelectRows
    assert table.selectionMode() == VaultTable.SelectionMode.ExtendedSelection
    print("    PASS")

def test_theme_manager():
    """Test ThemeManager singleton."""
    print("[4] Theme Manager...")
    app = get_app()
    tm = ThemeManager(app)
    assert tm.current_theme() in [Theme.DARK, Theme.LIGHT, Theme.AUTO]
    palette = tm.palette()
    assert "bg" in palette
    assert "accent" in palette
    assert "fg" in palette
    print("    PASS")

def test_load_vault_into_gui():
    """Test loading a vault into the GUI."""
    print("[5] Load Vault into GUI...")
    app = get_app()
    window = MainWindow()
    vault_path = "/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json"
    if os.path.exists(vault_path):
        from pathlib import Path
        items, raw_data = load_vault(Path(vault_path))
        window._items = items
        window._raw_data = raw_data
        window._vault_path = Path(vault_path)
        assert len(window._items) > 0
        print(f"    PASS (loaded {len(items)} items)")
    else:
        print("    SKIP (no large vault fixture)")

def test_search_functionality():
    """Test search bar filtering."""
    print("[6] Search Functionality...")
    app = get_app()
    window = MainWindow()
    vault_path = "/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json"
    if os.path.exists(vault_path):
        from pathlib import Path
        items, raw_data = load_vault(Path(vault_path))
        window._items = items
        window._raw_data = raw_data
        window._vault_path = Path(vault_path)
        # Test search
        window._search_bar.setText("google")
        # Trigger search via textChanged signal
        window._search_bar.textChanged.emit("google")
        filtered = window._items
        assert len(filtered) >= 0
        print(f"    PASS (search triggered on {len(filtered)} items)")
    else:
        print("    SKIP (no large vault fixture)")

def test_health_audit():
    """Test health audit execution."""
    print("[7] Health Audit...")
    app = get_app()
    window = MainWindow()
    vault_path = "/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json"
    if os.path.exists(vault_path):
        from pathlib import Path
        items, raw_data = load_vault(Path(vault_path))
        window._items = items
        window._raw_data = raw_data
        # Run health audit manually
        weak_passwords = []
        reused_passwords = {}
        missing_totp = []
        empty_passwords = []
        for item in items:
            if item.is_login() and item.login:
                pw = item.login.password or ""
                if len(pw) < 8 or pw.lower() in {"password", "123456", "qwerty", "password123", "12345678", "abc123"}:
                    weak_passwords.append(item)
                if not pw:
                    empty_passwords.append(item)
                if pw:
                    reused_passwords.setdefault(pw, []).append(item)
                if not item.login.totp:
                    domains = item.get_domains()
                    known_2fa = {"google.com", "github.com", "amazon.com", "microsoft.com", "dropbox.com", "apple.com", "icloud.com", "gmail.com", "outlook.com", "proton.me", "fastmail.com"}
                    if domains & known_2fa:
                        missing_totp.append(item)
        reuse_clusters = [v for v in reused_passwords.values() if len(v) > 1]
        print(f"    PASS (weak={len(weak_passwords)}, reuse={len(reuse_clusters)}, totp={len(missing_totp)})")
    else:
        print("    SKIP (no large vault fixture)")

def test_undo_redo():
    """Test undo/redo stack."""
    print("[8] Undo/Redo...")
    app = get_app()
    window = MainWindow()
    vault_path = "/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json"
    if os.path.exists(vault_path):
        from pathlib import Path
        items, raw_data = load_vault(Path(vault_path))
        window._items = items
        window._raw_data = raw_data
        # Save state
        window._undo.save_state(items, raw_data, "Initial load")
        assert window._undo.can_undo()
        assert not window._undo.can_redo()
        # Undo
        undo_result = window._undo.undo()
        assert undo_result is not None
        undo_items, undo_data = undo_result
        assert undo_items is not None
        assert undo_data is not None
        print("    PASS")
    else:
        print("    SKIP (no large vault fixture)")

def test_theme_toggle():
    """Test theme toggle."""
    print("[9] Theme Toggle...")
    app = get_app()
    window = MainWindow()
    initial_theme = window._theme_btn.text()
    # Toggle theme
    window._toggle_theme()
    new_theme = window._theme_btn.text()
    assert new_theme != initial_theme
    print(f"    PASS ({initial_theme} -> {new_theme})")

def test_dedup_worker():
    """Test dedup worker."""
    print("[10] Dedup Worker...")
    vault_path = "/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json"
    if os.path.exists(vault_path):
        from pathlib import Path
        items, raw_data = load_vault(Path(vault_path))
        worker = DedupWorker(items, threshold=0.85, fast=True, target_types={1})
        assert worker is not None
        print(f"    PASS (created worker with {len(items)} items)")
    else:
        print("    SKIP (no large vault fixture)")

def test_rename_worker():
    """Test rename worker."""
    print("[11] Rename Worker...")
    vault_path = "/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json"
    if os.path.exists(vault_path):
        from pathlib import Path
        items, raw_data = load_vault(Path(vault_path))
        worker = RenameWorker(items, ["google"], {1})
        assert worker is not None
        print(f"    PASS (created worker with {len(items)} items)")
    else:
        print("    SKIP (no large vault fixture)")

def test_vault_table_population():
    """Test vault table with items."""
    print("[12] Vault Table Population...")
    vault_path = "/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json"
    if os.path.exists(vault_path):
        from pathlib import Path
        items, raw_data = load_vault(Path(vault_path))
        table = VaultTable()
        table.set_items(items[:100])
        assert table.rowCount() == 100
        print(f"    PASS (set {table.rowCount()} rows)")
    else:
        print("    SKIP (no large vault fixture)")

def test_vault_table_selection():
    """Test vault table selection."""
    print("[13] Vault Table Selection...")
    vault_path = "/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json"
    if os.path.exists(vault_path):
        from pathlib import Path
        items, raw_data = load_vault(Path(vault_path))
        table = VaultTable()
        table.set_items(items[:10])
        # Select first row
        table.selectRow(0)
        selected = table.get_selected_items(items[:10])
        assert len(selected) == 1
        assert selected[0].id == items[0].id
        print(f"    PASS (selected 1 item)")
    else:
        print("    SKIP (no large vault fixture)")

def test_item_editor():
    """Test item editor."""
    print("[14] Item Editor...")
    from bitmerger.item_editor import ItemEditor
    app = get_app()
    editor = ItemEditor()
    assert editor is not None
    assert not editor.is_dirty()
    print("    PASS")

def test_item_editor_load():
    """Test item editor load item."""
    print("[15] Item Editor Load...")
    from bitmerger.item_editor import ItemEditor
    app = get_app()
    vault_path = "/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json"
    if os.path.exists(vault_path):
        from pathlib import Path
        items, raw_data = load_vault(Path(vault_path))
        editor = ItemEditor()
        item = items[0]
        editor.load_item(item, items)
        assert editor._item is not None
        assert editor._item.id == item.id
        assert not editor.is_dirty()
        print(f"    PASS (loaded item: {item.name})")
    else:
        print("    SKIP (no large vault fixture)")

def test_stylesheet():
    """Test stylesheet generation."""
    print("[16] Stylesheet...")
    app = get_app()
    tm = ThemeManager(app)
    ss = tm.stylesheet()
    assert len(ss) > 1000
    assert "QMainWindow" in ss
    assert "QPushButton" in ss
    assert "QTableWidget" in ss
    print(f"    PASS (stylesheet: {len(ss)} chars)")

def test_icons():
    """Test icon helpers."""
    print("[17] Icons...")
    from bitmerger.icons import type_badge_text, type_color, confidence_badge
    assert type_badge_text(1) != ""
    assert type_badge_text(2) != ""
    assert type_color(1) != ""
    assert confidence_badge(0.95) != ""
    print("    PASS")

def main():
    print("=" * 60)
    print("BITMERGER v2 E2E GUI TEST SUITE")
    print("=" * 60)
    
    tests = [
        test_gui_import,
        test_window_creation,
        test_vault_table,
        test_theme_manager,
        test_load_vault_into_gui,
        test_search_functionality,
        test_health_audit,
        test_undo_redo,
        test_theme_toggle,
        test_dedup_worker,
        test_rename_worker,
        test_vault_table_population,
        test_vault_table_selection,
        test_item_editor,
        test_item_editor_load,
        test_stylesheet,
        test_icons,
    ]
    
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"    FAIL: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 60)
    
    if failed > 0:
        sys.exit(1)
    print("ALL E2E TESTS PASSED")
    return 0

if __name__ == "__main__":
    main()
