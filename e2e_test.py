"""Portable offscreen smoke test for the current Bitmerger GUI.

Run with ``QT_QPA_PLATFORM=offscreen python e2e_test.py``.  This is deliberately
self-contained rather than a second, stale test suite; exhaustive behavior lives
under ``tests/``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from typing import cast

from PySide6.QtWidgets import QApplication

from bitmerger.core import load_vault
from bitmerger.gui import BatchSearchWorker, DedupWorker, MainWindow, VaultTable
from bitmerger.theme import Theme, get_theme_manager


ROOT = Path(__file__).resolve().parent
_APP: QApplication | None = None


def app() -> QApplication:
    global _APP
    if _APP is None:
        existing = QApplication.instance()
        _APP = cast(QApplication, existing) if isinstance(existing, QApplication) else QApplication(sys.argv)
    return cast(QApplication, _APP)


def test_gui_imports() -> None:
    assert MainWindow is not None
    assert VaultTable is not None
    assert DedupWorker is not None
    assert BatchSearchWorker is not None


def test_window_and_tabs() -> None:
    app()
    window = MainWindow()
    assert window.windowTitle() == "Bitmerger — Bitwarden + 1Password Vault Utility"
    assert window.minimumWidth() >= 1000
    assert window.minimumHeight() >= 700
    assert [window._tabs.tabText(index) for index in range(window._tabs.count())] == [
        "Vault Overview", "Deduplicate", "Batch Editor", "Merge Vaults"
    ]
    assert window._dual_bw_path is not None
    assert window._dual_1p_path is not None
    assert window._dual_output_dir is not None


def test_vault_table() -> None:
    table = VaultTable()
    assert table.columnCount() == 9
    assert table.selectionBehavior() == VaultTable.SelectionBehavior.SelectRows
    assert table.selectionMode() == VaultTable.SelectionMode.ExtendedSelection


def test_theme_manager() -> None:
    manager = get_theme_manager()
    assert manager.current_theme() in (Theme.DARK, Theme.LIGHT, Theme.AUTO)
    assert {"bg", "accent", "fg"}.issubset(manager.palette())


def test_known_vault_loads() -> None:
    items, raw_data = load_vault(ROOT / "tests" / "test_vault.json")
    assert items
    assert isinstance(raw_data, dict)
    window = MainWindow()
    window._items = items
    window._raw_data = raw_data
    window._overview_table.set_items(items)
    assert window._overview_table.rowCount() == len(items)


def main() -> int:
    tests = [
        ("GUI imports", test_gui_imports),
        ("Window and tabs", test_window_and_tabs),
        ("Vault table", test_vault_table),
        ("Theme manager", test_theme_manager),
        ("Known vault loading", test_known_vault_loads),
    ]
    failures: list[tuple[str, Exception]] = []
    print("Bitmerger GUI smoke test (offscreen)")
    for label, test in tests:
        try:
            test()
            print(f"  PASS  {label}")
        except Exception as exc:  # report every failed smoke check together
            failures.append((label, exc))
            print(f"  FAIL  {label}: {exc}")
    print(f"{len(tests) - len(failures)}/{len(tests)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
