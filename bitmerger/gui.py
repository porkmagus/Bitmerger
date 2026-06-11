"""
Bitmerger GUI: cross-platform PySide6 desktop application.

Usage:
    python -m bitmerger.gui
    python -m bitmerger --gui
"""

import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QProgressBar, QGroupBox, QComboBox, QTableWidget,
    QTableWidgetItem, QTextEdit, QHeaderView,
)
from PySide6.QtGui import QFont, QIcon

from .core import (
    BwItem, ClusterInfo, MergeRecord,
    normalize_domain, clean_uri,
    find_duplicates_by_type, cluster_confidence, pick_primary,
    merge_items, build_proposed_records, _accumulate_backfill,
    create_backup, create_merge_log, generate_html_report,
    parse_search_query, filter_items_by_name, create_rename_log,
    load_vault, save_vault,
    apply_batch_edit, create_batch_edit_log, BatchEditRecord,
)
from .fluidity import (
    SmoothVisibility, FadeTabWidget, ButtonPulse, StatusPulse,
    CheckboxPulse, HoverHighlight, animate_table_refresh,
)

# ---------------------------------------------------------------------------
# Worker threads (non-blocking)
# ---------------------------------------------------------------------------

class DedupWorker(QThread):
    finished = Signal(list, int, list)  # clusters, total_comp, all_items
    error = Signal(str)

    def __init__(self, items: list[BwItem], threshold: float, fast: bool, target_types: set[int]) -> None:
        super().__init__()
        self.items = items
        self.threshold = threshold
        self.fast = fast
        self.target_types = target_types

    def run(self) -> None:
        try:
            dedup_items = [i for i in self.items if i.type in self.target_types]
            clusters, total_comp = find_duplicates_by_type(dedup_items, threshold=self.threshold, fast=self.fast)
            self.finished.emit(clusters, total_comp, self.items)
        except Exception as e:
            self.error.emit(str(e))


class BatchSearchWorker(QThread):
    finished = Signal(list, list)  # matches, all_items
    error = Signal(str)

    def __init__(self, items: list[BwItem], terms: list[str], target_types: set[int], folder_map: Optional[Dict[str, str]] = None) -> None:
        super().__init__()
        self.items = items
        self.terms = terms
        self.target_types = target_types
        self.folder_map = folder_map

    def run(self) -> None:
        try:
            matches = filter_items_by_name(self.items, self.terms, self.target_types, self.folder_map)
            self.finished.emit(matches, self.items)
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Vault table widget (reusable)
# ---------------------------------------------------------------------------

class VaultTable(QTableWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._folder_map: Dict[str, str] = {}
        self._current_items: list[BwItem] = []
        self.setColumnCount(9)
        self.setHorizontalHeaderLabels(["Type", "Name", "Username", "Domain", "Favorite", "Reprompt", "Folder", "Notes", "ID"])
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setHighlightSections(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        # Smooth per-pixel scrolling
        self.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

    def set_folder_map(self, folder_map: Dict[str, str]) -> None:
        self._folder_map = folder_map

    def set_items(self, items: list[BwItem]) -> None:
        self._current_items = items

        def _populate() -> None:
            self.setSortingEnabled(False)
            self.blockSignals(True)
            self.setUpdatesEnabled(False)

            self.clearContents()
            self.setRowCount(0)
            self.setRowCount(len(items))
            type_names = {1: "Login", 2: "Note", 3: "Card", 4: "Identity", 5: "SSH"}
            for row, item in enumerate(items):
                tname = type_names.get(item.type, "Other")
                username = ""
                domain = ""
                if item.login:
                    username = item.login.username or ""
                    if item.login.uris:
                        domain = normalize_domain(item.login.uris[0].uri) or ""
                fav = "Yes" if item.favorite else ""
                rep = "Yes" if item.reprompt else ""
                folder = self._folder_map.get(item.folderId or "", "") or (item.folderId or "")
                notes = (item.notes or "")[:40]

                self.setItem(row, 0, QTableWidgetItem(tname))
                self.setItem(row, 1, QTableWidgetItem(item.name))
                self.setItem(row, 2, QTableWidgetItem(username))
                self.setItem(row, 3, QTableWidgetItem(domain))
                self.setItem(row, 4, QTableWidgetItem(fav))
                self.setItem(row, 5, QTableWidgetItem(rep))
                self.setItem(row, 6, QTableWidgetItem(folder))
                self.setItem(row, 7, QTableWidgetItem(notes))
                self.setItem(row, 8, QTableWidgetItem(item.id))

            self.setUpdatesEnabled(True)
            self.blockSignals(False)
            self.setSortingEnabled(True)
            self.viewport().update()

        # Only animate for substantial tables; small tables populate instantly.
        if len(items) > 10:
            animate_table_refresh(self, _populate)
        else:
            _populate()

    def get_selected_items(self, all_items: list[BwItem]) -> list[BwItem]:
        selected: list[BwItem] = []
        for idx in self.selectionModel().selectedRows():
            row = idx.row()
            item_widget = self.item(row, 8)
            if item_widget is None:
                continue
            item_id = item_widget.text()
            for item in all_items:
                if item.id == item_id:
                    selected.append(item)
                    break
        return selected

    def get_current_items(self) -> list[BwItem]:
        return self._current_items


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bitmerger — Bitwarden Vault Utility")
        self.setWindowIcon(QIcon())  # Placeholder for custom icon
        self.setMinimumSize(1000, 700)

        self._vault_path: Optional[Path] = None
        self._items: list[BwItem] = []
        self._raw_data: dict[str, Any] = {}
        self._folder_map: Dict[str, str] = {}
        self._clusters: list[list[BwItem]] = []
        self._cluster_infos: list[ClusterInfo] = []
        self._dedup_worker: Optional[DedupWorker] = None
        self._batch_worker: Optional[BatchSearchWorker] = None

        self._build_ui()
        self._apply_fluidity()


    # --- UI construction ---

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header
        header = QLabel("Bitmerger — Bitwarden Vault Utility")
        header_font = QFont()
        header_font.setPointSize(18)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        # Vault file row
        file_row = QHBoxLayout()
        self._file_label = QLabel("No vault loaded")
        file_row.addWidget(self._file_label, 1)

        btn_load = QPushButton("Load Vault…")
        btn_load.setToolTip("Open a Bitwarden JSON export")
        btn_load.clicked.connect(self._on_load_vault)
        file_row.addWidget(btn_load)

        btn_save = QPushButton("Save Vault…")
        btn_save.setToolTip("Save modified vault to a new JSON file")
        btn_save.clicked.connect(self._on_save_vault)
        btn_save.setEnabled(False)
        self._btn_save = btn_save
        file_row.addWidget(btn_save)

        layout.addLayout(file_row)

        # Stats bar
        self._stats_label = QLabel("Items: 0 | Logins: 0 | Notes: 0 | Cards: 0 | Identities: 0 | SSH: 0")
        self._stats_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._stats_label)

        # Tabs — use FadeTabWidget for smooth transitions
        self._tabs = FadeTabWidget()
        layout.addWidget(self._tabs, 1)

        self._tabs.addTab(self._build_overview_tab(), "Vault Overview")
        self._tabs.addTab(self._build_dedup_tab(), "Deduplicate")
        self._tabs.addTab(self._build_batch_editor_tab(), "Batch Editor")

        # Status bar
        self._status = QLabel("Ready")
        self._status.setStyleSheet("padding: 4px;")
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

    def _apply_fluidity(self) -> None:
        """Wire up fluidity helpers after UI is constructed."""
        # Smooth progress bar fade in/out
        self._progress_smooth = SmoothVisibility(self._progress)

        # Status label flash on text change
        StatusPulse(self._status)

        # Button pulse on primary action buttons
        ButtonPulse(self._btn_save)

    def _build_overview_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self._overview_table = VaultTable()
        layout.addWidget(self._overview_table)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(lambda: self._overview_table.set_items(self._items))
        layout.addWidget(btn_refresh)

        return w

    def _build_dedup_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        # Settings group
        settings = QGroupBox("Deduplication Settings")
        settings_layout = QVBoxLayout(settings)
        settings_layout.setSpacing(10)

        # Threshold
        thresh_row = QHBoxLayout()
        thresh_row.addWidget(QLabel("Similarity Threshold:"))
        self._thresh_spin = QDoubleSpinBox()
        self._thresh_spin.setRange(0.0, 1.0)
        self._thresh_spin.setSingleStep(0.05)
        self._thresh_spin.setValue(0.85)
        self._thresh_spin.setDecimals(2)
        self._thresh_spin.setToolTip("Minimum similarity score (0.0–1.0) to consider items duplicates. Higher = fewer matches, more strict.")
        thresh_row.addWidget(self._thresh_spin)
        thresh_row.addStretch()
        settings_layout.addLayout(thresh_row)

        # Types checkboxes
        types_row = QHBoxLayout()
        types_row.addWidget(QLabel("Item Types:"))
        self._type_checks: dict[int, QCheckBox] = {}
        type_labels = {1: "Logins", 2: "Notes", 3: "Cards", 4: "Identities", 5: "SSH Keys"}
        for code, label in type_labels.items():
            cb = QCheckBox(label)
            cb.setChecked(True)
            self._type_checks[code] = cb
            types_row.addWidget(cb)
        types_row.addStretch()
        settings_layout.addLayout(types_row)

        # Confidence filter
        conf_row = QHBoxLayout()
        self._conf_check = QCheckBox("Only auto-merge clusters above confidence:")
        self._conf_check.setToolTip("Skip low-confidence clusters to avoid false positives")
        self._conf_spin = QDoubleSpinBox()
        self._conf_spin.setRange(0.0, 1.0)
        self._conf_spin.setSingleStep(0.05)
        self._conf_spin.setValue(0.95)
        self._conf_spin.setDecimals(2)
        self._conf_spin.setEnabled(False)
        self._conf_spin.setToolTip("Confidence threshold for auto-merge. 0.95 = very high confidence only.")
        self._conf_check.toggled.connect(self._conf_spin.setEnabled)
        conf_row.addWidget(self._conf_check)
        conf_row.addWidget(self._conf_spin)
        conf_row.addStretch()
        settings_layout.addLayout(conf_row)

        # Fast mode
        self._fast_check = QCheckBox("Fast mode (skip expensive fuzzy matching)")
        self._fast_check.setToolTip("Skip fuzzy name matching for ~2x speed. May miss duplicates with similar but not identical names.")
        settings_layout.addWidget(self._fast_check)

        # Buttons
        btn_row = QHBoxLayout()
        btn_analyze = QPushButton("Analyze Duplicates")
        btn_analyze.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        btn_analyze.clicked.connect(self._on_dedup_analyze)
        btn_row.addWidget(btn_analyze)

        self._btn_dedup_merge = QPushButton("Execute Merge")
        self._btn_dedup_merge.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self._btn_dedup_merge.setEnabled(False)
        self._btn_dedup_merge.clicked.connect(self._on_dedup_merge)
        btn_row.addWidget(self._btn_dedup_merge)

        btn_dry = QPushButton("Dry Run + Report")
        btn_dry.clicked.connect(self._on_dedup_dry_run)
        btn_row.addWidget(btn_dry)

        btn_row.addStretch()
        settings_layout.addLayout(btn_row)

        layout.addWidget(settings)

        # Results
        results = QGroupBox("Duplicate Clusters")
        results_layout = QVBoxLayout(results)

        self._dedup_table = QTableWidget()
        self._dedup_table.setColumnCount(6)
        self._dedup_table.setHorizontalHeaderLabels(["Cluster", "Type", "Count", "Names", "Confidence", "Key"])
        self._dedup_table.horizontalHeader().setStretchLastSection(True)
        self._dedup_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._dedup_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._dedup_table.setAlternatingRowColors(True)
        self._dedup_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._dedup_table.setSortingEnabled(True)
        # Smooth per-pixel scrolling
        self._dedup_table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self._dedup_table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        results_layout.addWidget(self._dedup_table)

        self._dedup_detail = QTextEdit()
        self._dedup_detail.setReadOnly(True)
        self._dedup_detail.setMaximumHeight(140)
        self._dedup_detail.setPlaceholderText("Select a cluster to view details. Run 'Analyze Duplicates' to find duplicate items.")
        self._dedup_detail.setStyleSheet("font-size: 12px; padding: 8px;")
        results_layout.addWidget(self._dedup_detail)

        self._dedup_table.itemSelectionChanged.connect(self._on_dedup_selection_changed)

        layout.addWidget(results, 1)

        # Apply fluidity to dedup tab widgets
        ButtonPulse(btn_analyze)
        ButtonPulse(self._btn_dedup_merge)
        CheckboxPulse(self._conf_check)
        CheckboxPulse(self._fast_check)
        for cb in self._type_checks.values():
            CheckboxPulse(cb)
        HoverHighlight(settings)
        HoverHighlight(results)

        return w

    def _build_batch_editor_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        # Search group
        search_group = QGroupBox("Search & Filter")
        search_layout = QVBoxLayout(search_group)

        # Search query
        query_row = QHBoxLayout()
        query_row.addWidget(QLabel("Search Query:"))
        self._batch_query = QLineEdit()
        self._batch_query.setPlaceholderText("google+type:login+favorite:true — '+' means OR")
        self._batch_query.setToolTip(
            "Enter search terms. Use + to OR. Supports field:value syntax: "
            "name, username, domain, uri, notes, folder, type, favorite, reprompt, id, org, collection."
        )
        query_row.addWidget(self._batch_query, 1)
        search_layout.addLayout(query_row)

        # Types
        rtypes_row = QHBoxLayout()
        rtypes_row.addWidget(QLabel("Item Types:"))
        self._batch_type_checks: dict[int, QCheckBox] = {}
        type_labels = {1: "Logins", 2: "Notes", 3: "Cards", 4: "Identities", 5: "SSH Keys"}
        for code, label in type_labels.items():
            cb = QCheckBox(label)
            cb.setChecked(True)
            self._batch_type_checks[code] = cb
            rtypes_row.addWidget(cb)
        rtypes_row.addStretch()
        search_layout.addLayout(rtypes_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_search = QPushButton("Search")
        btn_search.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        btn_search.clicked.connect(self._on_batch_search)
        btn_row.addWidget(btn_search)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._on_batch_clear)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()
        search_layout.addLayout(btn_row)

        layout.addWidget(search_group)

        # Results table
        results = QGroupBox("Matched Items")
        results_layout = QVBoxLayout(results)

        self._batch_table = VaultTable()
        self._batch_table.itemSelectionChanged.connect(self._on_batch_selection_changed)
        results_layout.addWidget(self._batch_table)

        self._batch_status = QLabel("No search performed yet")
        results_layout.addWidget(self._batch_status)

        layout.addWidget(results, 1)

        # Bulk Edit group
        edit_group = QGroupBox("Bulk Edit")
        edit_layout = QVBoxLayout(edit_group)

        field_row = QHBoxLayout()
        field_row.addWidget(QLabel("Field:"))
        self._batch_field_combo = QComboBox()
        self._batch_field_combo.setToolTip("Select the field to edit for all selected (or all visible) items")
        self._batch_field_combo.currentTextChanged.connect(self._on_batch_field_changed)
        field_row.addWidget(self._batch_field_combo)

        self._batch_value_label = QLabel("Value:")
        field_row.addWidget(self._batch_value_label)
        self._batch_value_edit = QLineEdit()
        self._batch_value_edit.setToolTip("New value for the selected field")
        field_row.addWidget(self._batch_value_edit, 1)

        self._batch_bool_check = QCheckBox("Enable")
        self._batch_bool_check.setVisible(False)
        field_row.addWidget(self._batch_bool_check)

        field_row.addStretch()
        edit_layout.addLayout(field_row)

        self._batch_apply_btn = QPushButton("Apply")
        self._batch_apply_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self._batch_apply_btn.setToolTip("Apply the value to selected rows. If no rows are selected, applies to all visible matches.")
        self._batch_apply_btn.clicked.connect(self._on_batch_apply)
        edit_layout.addWidget(self._batch_apply_btn)

        layout.addWidget(edit_group)

        # Apply fluidity to batch editor tab widgets
        ButtonPulse(btn_search)
        ButtonPulse(self._batch_apply_btn)
        for cb in self._batch_type_checks.values():
            CheckboxPulse(cb)
        HoverHighlight(search_group)
        HoverHighlight(results)
        HoverHighlight(edit_group)

        return w

    def _update_batch_field_combo(self, items: list[BwItem]) -> None:
        """Populate the field dropdown based on what fields are present in the matched items."""
        has_name = any(i.name for i in items)
        has_username = any(i.login and i.login.username for i in items)
        has_domain = any(i.login and i.login.uris for i in items)
        has_notes = any(i.notes for i in items)
        has_folder = any(i.folderId for i in items)

        fields: list[str] = []
        if has_name:
            fields.append("Name")
        if has_username:
            fields.append("Username")
        if has_domain:
            fields.append("Domain")
        if has_notes:
            fields.append("Notes")
        # Always show these since they are flags on every item
        fields.append("Favorite")
        fields.append("Reprompt")
        if has_folder:
            fields.append("Folder")

        if not fields:
            fields = ["Name", "Favorite", "Reprompt"]

        current = self._batch_field_combo.currentText()
        self._batch_field_combo.clear()
        self._batch_field_combo.addItems(fields)
        if current in fields:
            self._batch_field_combo.setCurrentText(current)
        else:
            self._batch_field_combo.setCurrentIndex(0)
        self._on_batch_field_changed(self._batch_field_combo.currentText())

    def _on_batch_selection_changed(self) -> None:
        selected = self._batch_table.get_selected_items(self._items)
        if selected:
            self._batch_apply_btn.setText(f"Apply to {len(selected)} Selected")
        else:
            visible = self._batch_table.rowCount()
            self._batch_apply_btn.setText(f"Apply to All ({visible})")

    def _on_batch_field_changed(self, text: str) -> None:
        is_bool = text in ("Favorite", "Reprompt")
        self._batch_value_edit.setVisible(not is_bool)
        self._batch_value_label.setVisible(not is_bool)
        self._batch_bool_check.setVisible(is_bool)
        if is_bool:
            self._batch_bool_check.setText(f"Set {text}")
            self._batch_bool_check.setChecked(True)
        self._on_batch_selection_changed()

    def _on_batch_search(self) -> None:
        if not self._items:
            QMessageBox.warning(self, "Warning", "Load a vault first.")
            return

        query = self._batch_query.text().strip()
        if not query:
            QMessageBox.warning(self, "Warning", "Enter a search query.")
            return

        self._progress_smooth.show()
        self._status.setText("Searching…")
        self._batch_table.setRowCount(0)
        self._batch_status.setText("")

        terms = parse_search_query(query)
        target_types = {c for c, cb in self._batch_type_checks.items() if cb.isChecked()}

        self._batch_worker = BatchSearchWorker(self._items, terms, target_types, self._folder_map)
        self._batch_worker.finished.connect(self._on_batch_finished)
        self._batch_worker.error.connect(self._on_batch_error)
        self._batch_worker.start()

    def _on_batch_finished(self, matches: list[BwItem], all_items: list[BwItem]) -> None:
        self._progress_smooth.hide()
        self._batch_table.set_items(matches)
        self._batch_status.setText(f"Found {len(matches)} matching item(s)")
        self._status.setText(f"Search complete: {len(matches)} matches")
        self._update_batch_field_combo(matches)
        self._on_batch_selection_changed()

    def _on_batch_error(self, msg: str) -> None:
        self._progress_smooth.hide()
        QMessageBox.critical(self, "Error", f"Search failed:\n{msg}")

    def _on_batch_clear(self) -> None:
        self._batch_table.clearContents()
        self._batch_table.setRowCount(0)
        self._batch_status.setText("No search performed yet")
        self._batch_query.clear()
        self._batch_apply_btn.setText("Apply")
        self._batch_field_combo.clear()

    def _on_batch_apply(self) -> None:
        field = self._batch_field_combo.currentText().lower()
        value: Any
        if field in ("favorite", "reprompt"):
            value = self._batch_bool_check.isChecked()
        else:
            value = self._batch_value_edit.text().strip()
            if not value:
                QMessageBox.warning(self, "Warning", "Enter a value to apply.")
                return

        matches = self._batch_table.get_selected_items(self._items)
        target_desc = f"{len(matches)} selected"
        if not matches:
            # apply to all visible
            matches = []
            for i in range(self._batch_table.rowCount()):
                cell = self._batch_table.item(i, 8)
                if cell is None:
                    continue
                item_id = cell.text()
                for item in self._items:
                    if item.id == item_id:
                        matches.append(item)
                        break
            target_desc = f"all {len(matches)} visible"

        if not matches:
            QMessageBox.warning(self, "Warning", "No items to edit.")
            return

        reply = QMessageBox.question(
            self, "Confirm Batch Edit",
            f"Apply '{field}' = '{value}' to {target_desc} item(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            records = apply_batch_edit(self._items, matches, field, value)
            self._batch_table.set_items(matches)
            self._overview_table.set_items(self._items)
            self._update_stats()
            self._batch_status.setText(f"Edited {len(records)} item(s) — field: {field}")
            self._status.setText(f"Batch edit complete: {len(records)} items")
            self._on_batch_selection_changed()

            if self._vault_path:
                backup = create_backup(self._vault_path)
                out_path = self._vault_path.with_suffix(".edited.json")
                save_vault(out_path, self._items, self._raw_data)
                if records:
                    create_batch_edit_log(records, out_path)
                QMessageBox.information(
                    self, "Batch Edit Complete",
                    f"Edited {len(records)} items.\n"
                    f"Saved to: {out_path}\n"
                    f"Backup: {backup}"
                )
            else:
                QMessageBox.information(
                    self, "Batch Edit Complete",
                    f"Edited {len(records)} items.\n\n"
                    f"Use 'Save Vault…' to write the export."
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Batch edit failed:\n{e}")

    # --- Event handlers ---

    def _on_load_vault(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Bitwarden Vault Export", "", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        self._load_vault(Path(path))

    def _load_vault(self, path: Path) -> None:
        """Load a vault from a Path (bypasses file dialog for testing)."""
        try:
            # Stop any running background workers before swapping data
            if self._dedup_worker and self._dedup_worker.isRunning():
                self._dedup_worker.quit()
                self._dedup_worker.wait(2000)
            if self._batch_worker and self._batch_worker.isRunning():
                self._batch_worker.quit()
                self._batch_worker.wait(2000)

            self._vault_path = Path(path)
            self._items, self._raw_data = load_vault(self._vault_path)
            self._file_label.setText(str(self._vault_path))

            # Build folder ID -> name map
            folders = self._raw_data.get("folders", [])
            self._folder_map = {
                f["id"]: f.get("name", "")
                for f in folders
                if isinstance(f, dict) and "id" in f
            }
            self._overview_table.set_folder_map(self._folder_map)
            self._batch_table.set_folder_map(self._folder_map)

            self._btn_save.setEnabled(True)
            self._update_stats()
            self._overview_table.set_items(self._items)
            self._status.setText(f"Loaded {len(self._items)} items from {self._vault_path.name}")

            # Clear all dedup state from previous vault
            self._clusters = []
            self._cluster_infos = []
            self._dedup_table.clearContents()
            self._dedup_table.setRowCount(0)
            self._dedup_detail.clear()
            self._btn_dedup_merge.setEnabled(False)

            # Clear all batch editor state from previous vault
            self._batch_table.clearContents()
            self._batch_table.setRowCount(0)
            self._batch_status.setText("No search performed yet")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load vault:\n{e}")

    def _on_save_vault(self) -> None:
        if not self._items:
            QMessageBox.warning(self, "Warning", "No vault loaded to save.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Vault Export", "vault_clean.json", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            save_vault(Path(path), self._items, self._raw_data)
            self._status.setText(f"Saved to {Path(path).name}")
            QMessageBox.information(self, "Saved", f"Vault saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save vault:\n{e}")

    def _update_stats(self) -> None:
        counts: dict[int, int] = {}
        for item in self._items:
            counts[item.type] = counts.get(item.type, 0) + 1
        type_names = {1: "Logins", 2: "Notes", 3: "Cards", 4: "Identities", 5: "SSH"}
        parts = [f"{type_names.get(t, f'Type{t}')}: {c}" for t, c in sorted(counts.items())]
        self._stats_label.setText(f"Items: {len(self._items)} | " + " | ".join(parts))

    # --- Deduplication ---

    def _on_dedup_analyze(self) -> None:
        if not self._items:
            QMessageBox.warning(self, "Warning", "Load a vault first.")
            return

        self._progress_smooth.show()
        self._status.setText("Analyzing duplicates…")
        self._clusters = []
        self._cluster_infos = []
        self._dedup_table.clearContents()
        self._dedup_table.setRowCount(0)
        self._dedup_detail.clear()
        self._btn_dedup_merge.setEnabled(False)

        threshold = self._thresh_spin.value()
        fast = self._fast_check.isChecked()
        target_types = {c for c, cb in self._type_checks.items() if cb.isChecked()}

        self._dedup_worker = DedupWorker(self._items, threshold, fast, target_types)
        self._dedup_worker.finished.connect(self._on_dedup_finished)
        self._dedup_worker.error.connect(self._on_dedup_error)
        self._dedup_worker.start()

    def _on_dedup_finished(self, clusters: list[list[BwItem]], total_comp: int, all_items: list[BwItem]) -> None:
        self._progress_smooth.hide()
        self._clusters = clusters
        self._status.setText(f"Found {len(clusters)} clusters ({total_comp:,} comparisons)")

        if not clusters:
            QMessageBox.information(self, "No Duplicates", "No duplicate clusters found.")
            return

        self._btn_dedup_merge.setEnabled(True)
        self._populate_dedup_table(clusters)

    def _on_dedup_error(self, msg: str) -> None:
        self._progress_smooth.hide()
        QMessageBox.critical(self, "Error", f"Analysis failed:\n{msg}")

    def _populate_dedup_table(self, clusters: list[list[BwItem]]) -> None:
        def _populate() -> None:
            self._dedup_table.blockSignals(True)
            self._dedup_table.setUpdatesEnabled(False)
            header = self._dedup_table.horizontalHeader()
            old_resize = header.sectionResizeMode(0)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

            self._dedup_table.clearContents()
            self._dedup_table.setRowCount(0)
            self._dedup_table.setRowCount(len(clusters))
            type_names = {1: "Login", 2: "Note", 3: "Card", 4: "Identity", 5: "SSH"}
            for idx, cluster in enumerate(clusters):
                first = cluster[0]
                tname = type_names.get(first.type, "Other")
                names = "\n".join(c.name for c in cluster)
                conf = cluster_confidence(cluster)
                conf_str = f"{conf:.0%}"

                key = ""
                if first.is_login():
                    key = (first.login.username or "") if first.login else ""
                elif first.is_card():
                    key = first.get_card_fingerprint() or ""
                elif first.is_identity():
                    key = first.identity.get("email", "") if first.identity else ""
                elif first.is_ssh_key():
                    key = (first.sshKey.keyFingerprint or "") if first.sshKey else ""

                self._dedup_table.setItem(idx, 0, QTableWidgetItem(str(idx + 1)))
                self._dedup_table.setItem(idx, 1, QTableWidgetItem(tname))
                self._dedup_table.setItem(idx, 2, QTableWidgetItem(str(len(cluster))))
                self._dedup_table.setItem(idx, 3, QTableWidgetItem(names))
                self._dedup_table.setItem(idx, 4, QTableWidgetItem(conf_str))
                self._dedup_table.setItem(idx, 5, QTableWidgetItem(key))

            header.setSectionResizeMode(old_resize)
            self._dedup_table.setUpdatesEnabled(True)
            self._dedup_table.blockSignals(False)
            header.resizeSections(QHeaderView.ResizeMode.ResizeToContents)
            self._dedup_table.viewport().update()

        if len(clusters) > 10:
            animate_table_refresh(self._dedup_table, _populate)
        else:
            _populate()

    def _on_dedup_selection_changed(self) -> None:
        selected = self._dedup_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        if row < 0 or row >= len(self._clusters):
            return

        cluster = self._clusters[row]
        lines = [f"Cluster #{row + 1} — {len(cluster)} items (confidence: {cluster_confidence(cluster):.0%})"]
        for i, item in enumerate(cluster):
            marker = "★" if i == pick_primary(cluster) else " "
            lines.append(f"  {marker} {item.name}")
            if item.login:
                lines.append(f"      User: {item.login.username or '(none)'} | Domain: {item.get_domains() or '(none)'}")
        self._dedup_detail.setPlainText("\n".join(lines))

    def _on_dedup_merge(self) -> None:
        if not self._clusters or not self._items:
            return

        reply = QMessageBox.question(
            self, "Confirm Merge",
            f"This will merge {len(self._clusters)} duplicate clusters.\n\n"
            "A backup of the original file will be created.\n\n"
            "Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            threshold = self._thresh_spin.value()
            target_types = {c for c, cb in self._type_checks.items() if cb.isChecked()}
            dedup_items = [i for i in self._items if i.type in target_types]
            pass_through = [i for i in self._items if i.type not in target_types]

            cluster_infos: list[ClusterInfo] = []
            for idx, cluster in enumerate(self._clusters):
                best_idx = pick_primary(cluster)
                conf = cluster_confidence(cluster)
                cluster_infos.append(ClusterInfo(
                    cluster_id=idx,
                    items=cluster,
                    selected_primary=best_idx,
                    confidence=conf,
                ))

            # Apply confidence filter
            if self._conf_check.isChecked():
                confidence = self._conf_spin.value()
                for ci in cluster_infos:
                    if ci.confidence < confidence:
                        ci.skipped = True

            merged_away_ids: set[str] = set()
            merge_records: list[MergeRecord] = []

            for ci in cluster_infos:
                if ci.skipped:
                    continue
                primary = ci.items[ci.selected_primary]
                all_new_uris: list[str] = []
                all_backfilled: dict[str, Any] = {}

                for i, c in enumerate(ci.items):
                    if i != ci.selected_primary:
                        primary, backfilled = merge_items(primary, c)
                        merged_away_ids.add(c.id)
                        for k, v in backfilled.items():
                            if k == "uris":
                                if c.login:
                                    all_new_uris.extend([clean_uri(u.uri) for u in c.login.uris])
                            else:
                                _accumulate_backfill(all_backfilled, {k: v})

                seen: set[str] = {clean_uri(u.uri).lower() for u in primary.login.uris} if primary.login else set()
                unique_new: list[str] = []
                for u_str in all_new_uris:
                    cu_cleaned = clean_uri(u_str).lower()
                    if cu_cleaned not in seen:
                        unique_new.append(u_str)
                        seen.add(cu_cleaned)

                merge_records.append(MergeRecord(
                    cluster_id=ci.cluster_id + 1,
                    primary=primary,
                    merged=ci.items,
                    new_uris=unique_new,
                    backfilled=all_backfilled,
                ))

            kept = [i for i in dedup_items if i.id not in merged_away_ids]
            self._items = kept + pass_through
            self._overview_table.set_items(self._items)
            self._update_stats()

            if self._vault_path and not self._vault_path.exists():
                self._vault_path = None

            # Save immediately
            if self._vault_path:
                backup = create_backup(self._vault_path)
                out_path = self._vault_path.with_suffix(".dedup.json")
                save_vault(out_path, self._items, self._raw_data)
                if merge_records:
                    create_merge_log(merge_records, out_path)
                generate_html_report(
                    records=merge_records,
                    stats={"original": len(kept) + len(pass_through) + len(merged_away_ids),
                           "final": len(self._items), "merged": len(merged_away_ids),
                           "clusters": len(self._clusters)},
                    threshold=threshold,
                    filename=self._vault_path.name,
                    output_path=self._vault_path.with_suffix(".report.html"),
                )
                self._status.setText(f"Merged {len(merged_away_ids)} items. Saved to {out_path.name}")
                QMessageBox.information(
                    self, "Merge Complete",
                    f"Merged {len(merged_away_ids)} duplicate items.\n"
                    f"Saved to: {out_path}\n"
                    f"Backup: {backup}"
                )
            else:
                self._status.setText(f"Merged {len(merged_away_ids)} items. Save vault to persist.")
                QMessageBox.information(
                    self, "Merge Complete",
                    f"Merged {len(merged_away_ids)} duplicate items.\n\n"
                    f"Use 'Save Vault…' to write the cleaned export."
                )

            self._dedup_table.setRowCount(0)
            self._dedup_detail.clear()
            self._btn_dedup_merge.setEnabled(False)
            self._clusters = []

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Merge failed:\n{e}")

    def _on_dedup_dry_run(self) -> None:
        if not self._items:
            QMessageBox.warning(self, "Warning", "Load a vault first.")
            return
        if not self._clusters:
            QMessageBox.information(self, "Dry Run", "No clusters analyzed yet. Click 'Analyze Duplicates' first.")
            return

        try:
            cluster_infos: list[ClusterInfo] = []
            for idx, cluster in enumerate(self._clusters):
                cluster_infos.append(ClusterInfo(
                    cluster_id=idx,
                    items=cluster,
                    selected_primary=pick_primary(cluster),
                    confidence=cluster_confidence(cluster),
                ))

            if self._conf_check.isChecked():
                confidence = self._conf_spin.value()
                for ci in cluster_infos:
                    if ci.confidence < confidence:
                        ci.skipped = True

            proposed = build_proposed_records(cluster_infos)
            stats = {
                "original": len(self._items),
                "final": len(self._items) - len(proposed),
                "merged": len(proposed),
                "clusters": len(self._clusters),
            }

            if self._vault_path:
                generate_html_report(
                    records=proposed,
                    stats=stats,
                    threshold=self._thresh_spin.value(),
                    filename=self._vault_path.name,
                    output_path=self._vault_path.with_suffix(".report.html"),
                )
                QMessageBox.information(
                    self, "Dry Run Complete",
                    f"Would merge {len(proposed)} clusters.\n"
                    f"Report saved to {self._vault_path.with_suffix('.report.html')}"
                )
            else:
                QMessageBox.information(
                    self, "Dry Run Complete",
                    f"Would merge {len(proposed)} clusters.\n"
                    f"Load a vault file to generate an HTML report."
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Dry run failed:\n{e}")

    # --- Batch Editor ---

    # (handlers moved above into the main event-handlers section)


def run() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Bitmerger")
    app.setOrganizationName("bitmerger")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
