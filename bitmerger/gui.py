"""
Bitmerger GUI: cross-platform PySide6 desktop application.

Usage:
    python -m bitmerger.gui
    python -m bitmerger --gui
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QProgressBar, QGroupBox, QComboBox, QTableWidget,
    QTableWidgetItem, QTextEdit, QHeaderView, QTabWidget,
)
from PySide6.QtGui import QFont, QIcon

from .core import (
    BwItem, ClusterInfo, MergeRecord,
    normalize_domain, clean_uri,
    find_duplicates_by_type, cluster_confidence, pick_primary,
    merge_items, build_proposed_records, _accumulate_backfill,
    create_backup, create_merge_log, generate_html_report,
    parse_search_query, filter_items_by_name, create_rename_log,
    apply_batch_edit, create_batch_edit_log, BatchEditRecord,
)
from .fluidity import (
    SmoothVisibility, ButtonPulse, StatusPulse,
    CheckboxPulse, animate_table_refresh,
)
from .theme import get_theme_manager
from .vault_formats import (
    DualMergeResult, MergePreflight, VaultFormatError, decision_key, expected_merge_outputs, load_document, merge_vaults, persist_never_suggest, preflight_merge, source_fingerprint,
    save_bitwarden, save_1password,
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


class DualVaultMergeWorker(QThread):
    """Runs cross-vault processing without freezing the desktop UI."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, bitwarden_path: Path, onepassword_path: Path, output_dir: Path, threshold: float, onepassword_csv_path: Optional[Path] = None, manual_merge_groups: Optional[list[list[str]]] = None, decision_log: Optional[list[dict[str, Any]]] = None, overwrite: bool = False) -> None:
        super().__init__()
        self.bitwarden_path = bitwarden_path
        self.onepassword_path = onepassword_path
        self.output_dir = output_dir
        self.threshold = threshold
        self.onepassword_csv_path = onepassword_csv_path
        self.manual_merge_groups = manual_merge_groups or []
        self.decision_log = decision_log or []
        self.overwrite = overwrite

    def run(self) -> None:
        try:
            self.finished.emit(merge_vaults(self.bitwarden_path, self.onepassword_path, self.output_dir, self.threshold, onepassword_csv_path=self.onepassword_csv_path, manual_merge_groups=self.manual_merge_groups, decision_log=self.decision_log, overwrite=self.overwrite))
        except Exception as exc:
            self.error.emit(str(exc))


class PreflightWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, bitwarden_path: Path, onepassword_path: Path, threshold: float, csv_path: Optional[Path]) -> None:
        super().__init__()
        self.bitwarden_path = bitwarden_path
        self.onepassword_path = onepassword_path
        self.threshold = threshold
        self.csv_path = csv_path

    def run(self) -> None:
        try:
            self.finished.emit(preflight_merge(self.bitwarden_path, self.onepassword_path, self.threshold, self.csv_path))
        except Exception as exc:
            self.error.emit(str(exc))

def item_overview_fields(item: BwItem) -> tuple[str, str]:
    """Compact type-aware fields without exposing passwords or private keys."""
    if item.is_login() and item.login:
        flags = []
        if item.login.totp:
            flags.append("TOTP")
        if item.login.fido2Credentials:
            flags.append(f"{len(item.login.fido2Credentials)} passkey(s)")
        domain = normalize_domain(item.login.uris[0].uri) if item.login.uris else ""
        return item.login.username or "", " · ".join([part for part in [domain, *flags] if part])
    if item.card:
        number = "".join(ch for ch in str(item.card.get("number") or "") if ch.isdigit())
        ending = f"•••• {number[-4:]}" if len(number) >= 4 else "Card number unavailable"
        expiry = "/".join(part for part in (str(item.card.get("expMonth") or ""), str(item.card.get("expYear") or "")) if part)
        return ending, " · ".join(part for part in (str(item.card.get("brand") or ""), expiry) if part)
    if item.identity:
        return str(item.identity.get("email") or item.identity.get("phone") or ""), " ".join(part for part in (str(item.identity.get("firstName") or ""), str(item.identity.get("lastName") or "")) if part)
    if item.sshKey:
        return item.sshKey.keyFingerprint or "SSH key", "Public key available" if item.sshKey.publicKey else "Private key only"
    return "", "Secure note" if item.type == 2 else "Other vault item"


class VaultTable(QTableWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._folder_map: Dict[str, str] = {}
        self._current_items: list[BwItem] = []
        self.setColumnCount(9)
        self.setHorizontalHeaderLabels(["Type", "Name", "Primary", "Details", "Favorite", "Reprompt", "Folder", "Notes", "ID"])
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
                primary, detail = item_overview_fields(item)
                fav = "Yes" if item.favorite else ""
                rep = "Yes" if item.reprompt else ""
                folder = self._folder_map.get(item.folderId or "", "") or (item.folderId or "")
                notes = (item.notes or "")[:40]

                self.setItem(row, 0, QTableWidgetItem(tname))
                self.setItem(row, 1, QTableWidgetItem(item.name))
                self.setItem(row, 2, QTableWidgetItem(primary))
                self.setItem(row, 3, QTableWidgetItem(detail))
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
        self.setWindowTitle("Bitmerger — Bitwarden + 1Password Vault Utility")
        self.setWindowIcon(QIcon())  # Placeholder for custom icon
        self.setMinimumSize(1000, 700)

        self._vault_path: Optional[Path] = None
        self._vault_format = "bitwarden"
        self._items: list[BwItem] = []
        self._raw_data: dict[str, Any] = {}
        self._folder_map: Dict[str, str] = {}
        self._clusters: list[list[BwItem]] = []
        self._cluster_infos: list[ClusterInfo] = []
        self._dedup_worker: Optional[DedupWorker] = None
        self._batch_worker: Optional[BatchSearchWorker] = None
        self._dual_merge_worker: Optional[DualVaultMergeWorker] = None
        self._preflight_worker: Optional[PreflightWorker] = None
        self._latest_preflight: Optional[MergePreflight] = None
        self._review_decisions: list[dict[str, Any]] = []

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
        header = QLabel("Bitmerger — Bitwarden + 1Password Vault Utility")
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

        # Native tabs avoid a Windows Qt repaint defect in QTableHeaderView
        # triggered by opacity effects on pages containing tables.
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, 1)

        self._tabs.addTab(self._build_overview_tab(), "Vault Overview")
        self._tabs.addTab(self._build_dedup_tab(), "Deduplicate")
        self._tabs.addTab(self._build_batch_editor_tab(), "Batch Editor")
        self._tabs.addTab(self._build_dual_vault_tab(), "Merge Vaults")

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
        # Deliberately no group-box hover stylesheet: Windows Qt recomputes
        # group-box contents margins while the pointer crosses its children.
        # That caused spin controls to visibly resize.

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
                out_path = self._derived_output_path("edited")
                self._save_current_format(out_path)
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
            self, "Open Bitwarden JSON, 1Password 1PUX, or 1Password CSV Export", "",
            "Vault exports (*.json *.1pux *.csv);;Bitwarden JSON (*.json);;1Password 1PUX (*.1pux);;1Password CSV (*.csv);;All Files (*)",
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
            document = load_document(self._vault_path)
            self._items = document.items
            self._raw_data = document.raw_data
            self._vault_format = document.format
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

    def _save_current_format(self, path: Path) -> Path:
        """Persist the active format; a single-vault workflow never silently converts it."""
        if self._vault_format in {"1password", "1password_csv"}:
            return save_1password(path, self._items)
        return save_bitwarden(path, self._items, self._raw_data)

    def _derived_output_path(self, label: str) -> Path:
        if not self._vault_path:
            raise ValueError("No vault path is available")
        suffix = ".1pux" if self._vault_format in {"1password", "1password_csv"} else ".json"
        return self._vault_path.with_name(f"{self._vault_path.stem}.{label}{suffix}")

    def _on_save_vault(self) -> None:
        if not self._items:
            QMessageBox.warning(self, "Warning", "No vault loaded to save.")
            return
        is_onepassword = self._vault_format in {"1password", "1password_csv"}
        extension = ".1pux" if is_onepassword else ".json"
        format_label = "1Password 1PUX (*.1pux)" if is_onepassword else "Bitwarden JSON (*.json)"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Vault Export", f"vault_clean{extension}", f"{format_label};;All Files (*)"
        )
        if not path:
            return
        try:
            self._save_current_format(Path(path))
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
                        before_uris = {(uri.uri.strip(), uri.match) for uri in primary.login.uris if uri.uri} if primary.login else set()
                        primary, backfilled = merge_items(primary, c)
                        merged_away_ids.add(c.id)
                        if backfilled.get("uris") and primary.login:
                            all_new_uris.extend(
                                uri.uri for uri in primary.login.uris
                                if uri.uri and (uri.uri.strip(), uri.match) not in before_uris
                            )
                        for k, v in backfilled.items():
                            if k != "uris":
                                _accumulate_backfill(all_backfilled, {k: v})

                unique_new = list(dict.fromkeys(all_new_uris))

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
                out_path = self._derived_output_path("dedup")
                self._save_current_format(out_path)
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

    # --- Cross-format Merge Vaults ---

    def _build_dual_vault_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        intro = QLabel(
            "Select one decrypted Bitwarden JSON export and one 1Password 1PUX export. "
            "Bitmerger creates new, local-only output files for both applications; it never modifies either source file."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        plaintext_note = QLabel(
            "Security note: exports and generated files contain plaintext secrets. Choose a private local folder; Bitmerger restricts new output files to the current user where supported."
        )
        plaintext_note.setWordWrap(True)
        plaintext_note.setToolTip("Bitwarden JSON and 1Password 1PUX exports are unencrypted.")
        layout.addWidget(plaintext_note)

        sources = QGroupBox("Source vaults")
        sources_layout = QVBoxLayout(sources)
        self._dual_controls: list[QWidget] = []
        self._dual_browse_buttons: list[QPushButton] = []
        self._dual_bw_path = QLineEdit()
        self._dual_bw_path.setReadOnly(True)
        self._dual_bw_path.setPlaceholderText("Choose a Bitwarden JSON export…")
        self._dual_1p_path = QLineEdit()
        self._dual_1p_path.setReadOnly(True)
        self._dual_1p_path.setPlaceholderText("Choose a 1Password .1pux export…")
        self._dual_csv_path = QLineEdit()
        self._dual_csv_path.setReadOnly(True)
        self._dual_csv_path.setPlaceholderText("Optional: choose a 1Password CSV to enrich logins and TOTP…")
        for label, target, callback in (
            ("Bitwarden JSON", self._dual_bw_path, self._choose_dual_bitwarden),
            ("1Password 1PUX", self._dual_1p_path, self._choose_dual_onepassword),
            ("1Password CSV (optional)", self._dual_csv_path, self._choose_dual_csv),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            target.setAccessibleName(label)
            target.setAccessibleDescription(f"Selected {label} source file")
            row.addWidget(target, 1)
            button = QPushButton("Choose…")
            button.setAccessibleName(f"Choose {label}")
            button.clicked.connect(callback)
            self._dual_browse_buttons.append(button)
            row.addWidget(button)
            sources_layout.addLayout(row)
        layout.addWidget(sources)

        output = QGroupBox("Safe merge settings")
        output_layout = QVBoxLayout(output)
        output_row = QHBoxLayout()
        self._dual_output_dir = QLineEdit()
        self._dual_output_dir.setReadOnly(True)
        self._dual_output_dir.setAccessibleName("Output folder")
        self._dual_output_dir.setAccessibleDescription("Folder where the cleaned vaults and audit report are written")
        self._dual_output_dir.setPlaceholderText("Choose a folder for the two new vault files…")
        output_row.addWidget(QLabel("Output folder"))
        output_row.addWidget(self._dual_output_dir, 1)
        choose_output = QPushButton("Choose…")
        choose_output.setAccessibleName("Choose output folder")
        choose_output.clicked.connect(self._choose_dual_output_dir)
        self._dual_browse_buttons.append(choose_output)
        output_row.addWidget(choose_output)
        output_layout.addLayout(output_row)
        strict_row = QHBoxLayout()
        strict_row.addWidget(QLabel("Strict duplicate confidence"))
        self._dual_threshold = QDoubleSpinBox()
        self._dual_threshold.setAccessibleName("Strict duplicate confidence")
        self._dual_threshold.setRange(0.90, 1.00)
        self._dual_threshold.setSingleStep(0.01)
        self._dual_threshold.setDecimals(2)
        self._dual_threshold.setValue(0.95)
        self._dual_threshold.setToolTip("Only records at or above this confidence are combined. Higher is safer.")
        self._dual_controls.append(self._dual_threshold)
        strict_row.addWidget(self._dual_threshold)
        strict_row.addStretch()
        output_layout.addLayout(strict_row)
        self._dual_versioned_dir = QCheckBox("Create a unique timestamped run folder")
        self._dual_versioned_dir.setChecked(True)
        self._dual_versioned_dir.setToolTip("Keeps each merge's plaintext artifacts separate for audit and rollback.")
        self._dual_controls.append(self._dual_versioned_dir)
        output_layout.addWidget(self._dual_versioned_dir)
        layout.addWidget(output)

        self._dual_preview_button = QPushButton("Preview Safety & Duplicates")
        self._dual_preview_button.clicked.connect(self._on_dual_preflight)
        layout.addWidget(self._dual_preview_button)

        self._dual_merge_button = QPushButton("Merge and Create Both Vaults")
        self._dual_merge_button.setAccessibleName("Merge selected vaults")
        self._dual_merge_button.setToolTip("Writes a Bitwarden JSON import file, a 1Password 1PUX archive, and an audit report.")
        self._dual_merge_button.clicked.connect(self._on_dual_merge)
        layout.addWidget(self._dual_merge_button)

        self._dual_result = QTextEdit()
        self._dual_result.setReadOnly(True)
        self._dual_result.setPlaceholderText("Output paths and any format-preservation warnings will appear here.")
        layout.addWidget(self._dual_result, 1)
        review_row = QHBoxLayout()
        self._review_combo = QComboBox()
        self._review_combo.setPlaceholderText("Run a preflight to load ambiguous candidates")
        review_row.addWidget(self._review_combo, 1)
        merge_choice = QPushButton("Merge Selected")
        merge_choice.clicked.connect(lambda: self._record_review_decision("merge"))
        keep_choice = QPushButton("Keep Separate")
        keep_choice.clicked.connect(lambda: self._record_review_decision("keep"))
        never_choice = QPushButton("Never Suggest")
        never_choice.clicked.connect(lambda: self._record_review_decision("never"))
        for button in (merge_choice, keep_choice, never_choice):
            review_row.addWidget(button)
        layout.addLayout(review_row)
        return widget

    def _choose_dual_bitwarden(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Choose Bitwarden JSON Export", "", "Bitwarden JSON (*.json)")
        if filename:
            self._dual_bw_path.setText(filename)
            if not self._dual_output_dir.text():
                self._dual_output_dir.setText(str(Path(filename).parent / "bitmerger-output"))

    def _choose_dual_onepassword(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Choose 1Password 1PUX Export", "", "1Password Unencrypted Export (*.1pux)")
        if filename:
            self._dual_1p_path.setText(filename)
            if not self._dual_output_dir.text():
                self._dual_output_dir.setText(str(Path(filename).parent / "bitmerger-output"))

    def _choose_dual_csv(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Choose Optional 1Password CSV Export", "", "1Password CSV (*.csv)")
        if filename:
            self._dual_csv_path.setText(filename)
            if not self._dual_output_dir.text():
                self._dual_output_dir.setText(str(Path(filename).parent / "bitmerger-output"))
    def _choose_dual_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose Output Folder", self._dual_output_dir.text())
        if directory:
            self._dual_output_dir.setText(directory)

    def _set_dual_merge_running(self, running: bool) -> None:
        """Freeze all source settings so displayed paths match the active worker."""
        self._dual_merge_button.setEnabled(not running)
        self._dual_preview_button.setEnabled(not running)
        for control in self._dual_controls + self._dual_browse_buttons:
            control.setEnabled(not running)

    def _record_review_decision(self, action: str) -> None:
        candidate = self._review_combo.currentData()
        if not isinstance(candidate, dict):
            return
        entry = {"action": action, "ids": candidate.get("ids", []), "names": candidate.get("names", []), "confidence": candidate.get("confidence")}
        self._review_decisions = [item for item in self._review_decisions if item.get("ids") != entry["ids"]]
        self._review_decisions.append(entry)
        if action == "never" and self._latest_preflight:
            persist_never_suggest(self._latest_preflight.source_fingerprints, entry["ids"])
            self._review_combo.removeItem(self._review_combo.currentIndex())
        self._status.setText(f"Review decision recorded: {action} selected candidate")
    def _on_dual_preflight(self) -> None:
        bw = Path(self._dual_bw_path.text()) if self._dual_bw_path.text() else None
        one = Path(self._dual_1p_path.text()) if self._dual_1p_path.text() else None
        csv_path = Path(self._dual_csv_path.text()) if self._dual_csv_path.text() else None
        if not bw or not one or not bw.is_file() or not one.is_file() or (csv_path and not csv_path.is_file()):
            QMessageBox.warning(self, "Missing source", "Choose existing Bitwarden JSON and 1Password 1PUX source files first.")
            return
        self._dual_preview_button.setEnabled(False)
        self._status.setText("Analyzing merge safety and duplicate candidates…")
        self._preflight_worker = PreflightWorker(bw, one, self._dual_threshold.value(), csv_path)
        self._preflight_worker.finished.connect(self._on_dual_preflight_finished)
        self._preflight_worker.error.connect(self._on_dual_preflight_error)
        self._preflight_worker.start()

    def _on_dual_preflight_finished(self, result: object) -> None:
        self._dual_preview_button.setEnabled(True)
        if not isinstance(result, MergePreflight):
            self._on_dual_preflight_error("Unexpected preflight result")
            return
        self._latest_preflight = result
        self._review_decisions = []
        self._review_combo.clear()
        for index, candidate in enumerate(result.ambiguous_candidates, start=1):
            self._review_combo.addItem(f"{index}. {candidate['confidence']:.0%} — {' / '.join(candidate['names'])}", candidate)
        lines = [f"Preflight: {result.input_count} input items", f"Safe automatic merges at current threshold: {result.strict_candidates}", f"Ambiguous candidates kept separate: {len(result.ambiguous_candidates)}", f"Bitwarden passkeys retained: {result.passkey_count}", f"Attachment/document manifest entries: {result.attachment_count}", f"1Password vaults: {', '.join(result.vault_names) or '(none)'}"]
        if result.ambiguous_candidates:
            lines.extend(["", "Review queue (kept separate):", *[f"• {entry['confidence']:.0%} — {entry['size']} items: {' / '.join(entry['names'])}" for entry in result.ambiguous_candidates[:20]]])
        if result.warnings:
            lines.extend(["", "Fidelity and migration notes:", *[f"• {warning}" for warning in result.warnings]])
        self._dual_result.setPlainText("\n".join(lines))
        self._status.setText("Preflight complete — review notes, then create outputs when ready")

    def _on_dual_preflight_error(self, message: str) -> None:
        self._dual_preview_button.setEnabled(True)
        self._status.setText("Preflight failed")
        self._dual_result.setPlainText(f"Preflight failed:\n{message}")
        QMessageBox.critical(self, "Merge Preflight Failed", message)
    def _on_dual_merge(self) -> None:
        bitwarden_path = Path(self._dual_bw_path.text()) if self._dual_bw_path.text() else None
        onepassword_path = Path(self._dual_1p_path.text()) if self._dual_1p_path.text() else None
        csv_path = Path(self._dual_csv_path.text()) if self._dual_csv_path.text() else None
        output_dir = Path(self._dual_output_dir.text()) if self._dual_output_dir.text() else None
        if not bitwarden_path or not onepassword_path or not output_dir:
            QMessageBox.warning(self, "Missing source", "Choose both source vaults and an output folder first.")
            return
        if not bitwarden_path.is_file() or not onepassword_path.is_file():
            QMessageBox.warning(self, "Missing source", "One or both selected vault files no longer exist.")
            return
        if csv_path and not csv_path.is_file():
            QMessageBox.warning(self, "Missing CSV", "The selected optional 1Password CSV file no longer exists.")
            return
        if self._latest_preflight:
            current = {str(path): source_fingerprint(path) for path in (bitwarden_path, onepassword_path) if path}
            if csv_path:
                current[str(csv_path)] = source_fingerprint(csv_path)
            if current != self._latest_preflight.source_fingerprints:
                QMessageBox.warning(self, "Sources changed", "A source changed after preflight. Preview safety and duplicates again before creating outputs.")
                return
        if self._dual_versioned_dir.isChecked():
            output_dir = output_dir / f"bitmerger-run-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
        overwrite = False
        existing_outputs = [path for path in expected_merge_outputs(output_dir) if path.exists()]
        if existing_outputs:
            names = "\n".join(f"• {path.name}" for path in existing_outputs)
            reply = QMessageBox.question(
                self,
                "Replace Existing Outputs?",
                "The following plaintext output file(s) already exist:\n\n"
                f"{names}\n\nReplace them? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        reply = QMessageBox.question(
            self,
            "Create merged vaults?",
            "Bitmerger will create two new plaintext export files and an audit report in the output folder. "
            "The two selected source files will not be changed. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._dual_result.clear()
        self._set_dual_merge_running(True)
        self._progress_smooth.show()
        self._status.setText("Merging Bitwarden and 1Password vaults…")
        manual_groups = [entry["ids"] for entry in self._review_decisions if entry.get("action") == "merge"]
        self._dual_merge_worker = DualVaultMergeWorker(bitwarden_path, onepassword_path, output_dir, self._dual_threshold.value(), onepassword_csv_path=csv_path, manual_merge_groups=manual_groups, decision_log=self._review_decisions, overwrite=overwrite)
        self._dual_merge_worker.finished.connect(self._on_dual_merge_finished)
        self._dual_merge_worker.error.connect(self._on_dual_merge_error)
        self._dual_merge_worker.start()

    def _on_dual_merge_finished(self, result: object) -> None:
        self._progress_smooth.hide()
        self._set_dual_merge_running(False)
        if not isinstance(result, DualMergeResult):
            self._on_dual_merge_error("Unexpected merge result")
            return
        lines = [
            f"Merged {result.merged_count} safe duplicate(s) across {result.input_count} input items.",
            f"Final item count: {result.output_count}",
            "",
            f"Bitwarden JSON: {result.bitwarden_output}",
            f"1Password 1PUX: {result.onepassword_output}",
            f"Audit report: {result.report_output}",
        ]
        if result.warnings:
            lines.extend(["", "Format notes:", *[f"• {warning}" for warning in result.warnings]])
        self._dual_result.setPlainText("\n".join(lines))
        self._status.setText(f"Created both vault outputs ({result.output_count} items)")
        QMessageBox.information(self, "Merged Vaults Created", "\n".join(lines[:6]))

    def _on_dual_merge_error(self, message: str) -> None:
        self._progress_smooth.hide()
        self._set_dual_merge_running(False)
        self._status.setText("Cross-vault merge failed")
        self._dual_result.setPlainText(f"Merge failed:\n{message}")
        QMessageBox.critical(self, "Cross-vault Merge Failed", message)

    # --- Batch Editor ---

    # (handlers moved above into the main event-handlers section)


def run() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Bitmerger")
    app.setOrganizationName("bitmerger")
    app.setFont(QFont("Segoe UI", 10))
    get_theme_manager(app)._apply_stylesheet()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
