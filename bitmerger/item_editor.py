"""
Bitmerger Item Editor — master-detail panel for editing individual vault items.

Supports inline editing of all BwItem fields: name, notes, login (username,
password, TOTP, URIs), card, identity, SSH, metadata (folder, collections,
favorite, reprompt), and custom fields.
"""

from typing import Any, Optional, List, Dict, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QCheckBox, QComboBox, QPushButton, QGroupBox, QScrollArea, QFrame,
    QGridLayout, QSpinBox, QDoubleSpinBox, QDialog, QMessageBox,
    QInputDialog, QApplication, QMenu, QTabWidget,
)
from PySide6.QtGui import QAction, QKeySequence

from .core import BwItem, UriEntry, LoginData, SshKeyData, load_vault, save_vault
from .theme import get_theme_manager
from .icons import type_badge_text, type_color, type_color_q


class SecureLineEdit(QLineEdit):
    """Line edit that masks/unmasks its content."""

    def __init__(self, parent: Optional[QWidget] = None, masked: bool = True) -> None:
        super().__init__(parent)
        self._masked = masked
        self.setEchoMode(QLineEdit.EchoMode.Password if masked else QLineEdit.EchoMode.Normal)
        self._btn = QPushButton("👁" if masked else "🙈")
        self._btn.setFlat(True)
        self._btn.setFixedWidth(32)
        self._btn.setStyleSheet("border: none; background: transparent; padding: 2px; font-size: 14px;")
        self._btn.setToolTip("Show/hide password")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._toggle)

    def _toggle(self) -> None:
        self._masked = not self._masked
        self.setEchoMode(QLineEdit.EchoMode.Password if self._masked else QLineEdit.EchoMode.Normal)
        self._btn.setText("👁" if self._masked else "🙈")

    def toggle_button(self) -> QPushButton:
        return self._btn

    def set_masked(self, masked: bool) -> None:
        self._masked = masked
        self.setEchoMode(QLineEdit.EchoMode.Password if masked else QLineEdit.EchoMode.Normal)
        self._btn.setText("👁" if masked else "🙈")


class ItemEditor(QScrollArea):
    """Scrollable item editor widget."""

    item_changed = Signal()  # Emitted when any field changes

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._item: Optional[BwItem] = None
        self._dirty = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._build_ui()
        self._clear_ui()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._container = QWidget()
        self.setWidget(self._container)
        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header: Type badge + Name
        header = QHBoxLayout()
        self._type_badge = QLabel("")
        self._type_badge.setStyleSheet("font-size: 16px; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
        header.addWidget(self._type_badge)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Item name")
        self._name_edit.setStyleSheet("font-size: 14px; font-weight: 500;")
        self._name_edit.textChanged.connect(self._mark_dirty)
        header.addWidget(self._name_edit, 1)
        layout.addLayout(header)

        # Favorite + Reprompt row
        flags_row = QHBoxLayout()
        flags_row.setSpacing(16)
        self._fav_check = QCheckBox("⭐ Favorite")
        self._fav_check.setStyleSheet("font-size: 13px;")
        self._fav_check.toggled.connect(self._mark_dirty)
        flags_row.addWidget(self._fav_check)
        self._reprompt_check = QCheckBox("🔒 Master password re-prompt")
        self._reprompt_check.setStyleSheet("font-size: 13px;")
        self._reprompt_check.toggled.connect(self._mark_dirty)
        flags_row.addWidget(self._reprompt_check)
        flags_row.addStretch()
        layout.addLayout(flags_row)

        # Tabs for type-specific sections
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet("QTabWidget::pane { border-radius: 8px; }")
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setStyleSheet("QTabWidget::pane { border-radius: 8px; }")
        layout.addWidget(self._tabs, 1)

        # --- Login Tab ---
        login_tab = QWidget()
        login_layout = QVBoxLayout(login_tab)
        login_layout.setSpacing(8)

        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("Username / email")
        self._user_edit.textChanged.connect(self._mark_dirty)
        login_layout.addWidget(QLabel("Username"))
        login_layout.addWidget(self._user_edit)

        pw_row = QHBoxLayout()
        self._pw_edit = SecureLineEdit(masked=True)
        self._pw_edit.textChanged.connect(self._mark_dirty)
        self._pw_edit.textChanged.connect(self._update_pw_strength)
        pw_row.addWidget(self._pw_edit, 1)
        pw_row.addWidget(self._pw_edit.toggle_button())
        self._pw_gen_btn = QPushButton("🔧 Generate")
        self._pw_gen_btn.setToolTip("Generate a strong password")
        self._pw_gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pw_gen_btn.clicked.connect(self._generate_password)
        pw_row.addWidget(self._pw_gen_btn)
        login_layout.addWidget(QLabel("Password"))
        login_layout.addLayout(pw_row)

        # Password strength meter
        self._pw_strength = QLabel("")
        self._pw_strength.setStyleSheet("font-size: 12px; padding: 6px 8px; border-radius: 4px;")
        self._pw_strength.setWordWrap(True)
        login_layout.addWidget(self._pw_strength)

        self._totp_edit = QLineEdit()
        self._totp_edit.setPlaceholderText("TOTP secret / authenticator key")
        self._totp_edit.textChanged.connect(self._mark_dirty)
        login_layout.addWidget(QLabel("TOTP"))
        login_layout.addWidget(self._totp_edit)

        # TOTP countdown timer
        self._totp_timer = QLabel("")
        self._totp_timer.setStyleSheet("font-size: 11px; color: #656d76; padding: 4px 0;")
        login_layout.addWidget(self._totp_timer)
        from PySide6.QtCore import QTimer
        self._totp_countdown = QTimer(self)
        self._totp_countdown.setInterval(1000)
        self._totp_countdown.timeout.connect(self._update_totp_timer)

        # URI list
        uri_group = QGroupBox("URIs")
        uri_layout = QVBoxLayout(uri_group)
        uri_layout.setSpacing(6)
        self._uri_list = QVBoxLayout()
        self._uri_list.setSpacing(4)
        uri_layout.addLayout(self._uri_list)
        btn_add_uri = QPushButton("+ Add URI")
        btn_add_uri.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_uri.setToolTip("Add a new URI for this login")
        btn_add_uri.clicked.connect(self._add_uri_row)
        uri_layout.addWidget(btn_add_uri)
        login_layout.addWidget(uri_group)

        login_layout.addStretch()
        self._tabs.addTab(login_tab, " Login")

        # --- Card Tab ---
        card_tab = QWidget()
        card_layout = QVBoxLayout(card_tab)
        card_layout.setSpacing(8)
        self._card_fields: Dict[str, QLineEdit] = {}
        for label, key in [
            ("Cardholder Name", "cardholderName"),
            ("Number", "number"),
            ("Brand", "brand"),
            ("Exp Month", "expMonth"),
            ("Exp Year", "expYear"),
            ("Code (CVV)", "code"),
        ]:
            card_layout.addWidget(QLabel(label))
            if key == "number":
                edit = QLineEdit()
                edit.setMaxLength(19)
                edit.setPlaceholderText("4111 1111 1111 1111")
            elif key == "expMonth":
                edit = QLineEdit()
                edit.setMaxLength(2)
                edit.setPlaceholderText("MM")
            elif key == "expYear":
                edit = QLineEdit()
                edit.setMaxLength(4)
                edit.setPlaceholderText("YYYY")
            elif key == "code":
                edit = QLineEdit()
                edit.setMaxLength(4)
                edit.setPlaceholderText("CVV")
            else:
                edit = QLineEdit()
            edit.textChanged.connect(self._mark_dirty)
            card_layout.addWidget(edit)
            self._card_fields[key] = edit
        card_layout.addStretch()
        self._tabs.addTab(card_tab, " Card")

        # --- Identity Tab ---
        id_tab = QWidget()
        id_layout = QVBoxLayout(id_tab)
        id_layout.setSpacing(8)
        self._id_fields: Dict[str, QLineEdit] = {}
        for label, key in [
            ("Title", "title"),
            ("First Name", "firstName"),
            ("Middle Name", "middleName"),
            ("Last Name", "lastName"),
            ("Address 1", "address1"),
            ("Address 2", "address2"),
            ("Address 3", "address3"),
            ("City", "city"),
            ("State", "state"),
            ("Postal Code", "postalCode"),
            ("Country", "country"),
            ("Company", "company"),
            ("Email", "email"),
            ("Phone", "phone"),
            ("SSN", "ssn"),
            ("Username", "username"),
            ("Passport", "passportNumber"),
            ("License", "licenseNumber"),
        ]:
            id_layout.addWidget(QLabel(label))
            edit = QLineEdit()
            edit.textChanged.connect(self._mark_dirty)
            id_layout.addWidget(edit)
            self._id_fields[key] = edit
        id_layout.addStretch()
        self._tabs.addTab(id_tab, " Identity")

        # --- SSH Tab ---
        ssh_tab = QWidget()
        ssh_layout = QVBoxLayout(ssh_tab)
        ssh_layout.setSpacing(8)
        self._ssh_fp = QLineEdit()
        self._ssh_fp.setReadOnly(True)
        self._ssh_fp.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ssh_layout.addWidget(QLabel("Fingerprint"))
        ssh_layout.addWidget(self._ssh_fp)
        self._ssh_pub = QTextEdit()
        self._ssh_pub.setPlaceholderText("Public key")
        self._ssh_pub.setMaximumHeight(80)
        self._ssh_pub.textChanged.connect(self._mark_dirty)
        ssh_layout.addWidget(QLabel("Public Key"))
        ssh_layout.addWidget(self._ssh_pub)
        self._ssh_priv = SecureLineEdit(masked=True)
        self._ssh_priv.textChanged.connect(self._mark_dirty)
        priv_row = QHBoxLayout()
        priv_row.addWidget(self._ssh_priv, 1)
        priv_row.addWidget(self._ssh_priv.toggle_button())
        ssh_layout.addWidget(QLabel("Private Key"))
        ssh_layout.addLayout(priv_row)
        ssh_layout.addStretch()
        self._tabs.addTab(ssh_tab, " SSH")

        # --- Notes Tab ---
        notes_tab = QWidget()
        notes_layout = QVBoxLayout(notes_tab)
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Notes / comments")
        self._notes_edit.setStyleSheet("font-size: 13px; padding: 8px;")
        self._notes_edit.textChanged.connect(self._mark_dirty)
        self._notes_edit.textChanged.connect(self._update_notes_count)
        notes_layout.addWidget(self._notes_edit)
        self._notes_count = QLabel("")
        self._notes_count.setStyleSheet("font-size: 11px; color: #656d76; padding: 4px 0;")
        notes_layout.addWidget(self._notes_count)
        self._tabs.addTab(notes_tab, " Notes")

        # --- Custom Fields Tab ---
        cf_tab = QWidget()
        cf_layout = QVBoxLayout(cf_tab)
        self._cf_grid = QGridLayout()
        self._cf_grid.setSpacing(6)
        cf_layout.addLayout(self._cf_grid)
        btn_add_cf = QPushButton("+ Add Custom Field")
        btn_add_cf.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_cf.setToolTip("Add a new custom field")
        btn_add_cf.clicked.connect(self._add_custom_field)
        cf_layout.addWidget(btn_add_cf)
        cf_layout.addStretch()
        self._tabs.addTab(cf_tab, " Custom Fields")

        # Metadata (folder, collections)
        meta = QGroupBox("Metadata")
        meta_layout = QVBoxLayout(meta)
        self._folder_combo = QComboBox()
        self._folder_combo.setEditable(True)
        self._folder_combo.currentTextChanged.connect(self._mark_dirty)
        meta_layout.addWidget(QLabel("Folder"))
        meta_layout.addWidget(self._folder_combo)
        self._collections_edit = QLineEdit()
        self._collections_edit.setPlaceholderText("Collection IDs (comma-separated)")
        self._collections_edit.textChanged.connect(self._mark_dirty)
        # UUID format validation
        from PySide6.QtGui import QRegularExpressionValidator
        from PySide6.QtCore import QRegularExpression
        self._collections_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9a-fA-F\-,. ]*$")))
        meta_layout.addWidget(QLabel("Collections:"))
        meta_layout.addWidget(self._collections_edit)
        layout.addWidget(meta)

        # Bottom actions
        actions = QHBoxLayout()
        self._save_btn = QPushButton("💾 Save Changes")
        self._save_btn.setStyleSheet("font-weight: 600; padding: 8px 16px;")
        self._save_btn.clicked.connect(self._save_changes)
        self._save_btn.setEnabled(False)
        actions.addWidget(self._save_btn)
        from PySide6.QtGui import QShortcut, QKeySequence
        self._save_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._save_shortcut.activated.connect(self._save_changes)
        self._discard_btn = QPushButton("❌ Discard")
        self._discard_btn.setStyleSheet("padding: 8px 16px;")
        self._discard_btn.clicked.connect(self._on_discard)
        self._discard_btn.setEnabled(False)
        actions.addWidget(self._discard_btn)
        actions.addStretch()
        layout.addLayout(actions)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Populate / Clear
    # ------------------------------------------------------------------

    def load_item(self, item: BwItem, all_items: List[BwItem]) -> None:
        self._item = item
        self._all_items = all_items
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)
        # Start TOTP timer when a login item is loaded
        if item.is_login() and item.login and item.login.totp:
            self._totp_countdown.start()
        else:
            self._totp_countdown.stop()
            self._totp_timer.setText("")

        # Header
        self._type_badge.setText(type_badge_text(item.type))
        color = type_color(item.type)
        self._type_badge.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
        self._name_edit.setText(item.name)
        self._fav_check.setChecked(item.favorite)
        self._reprompt_check.setChecked(bool(item.reprompt))

        # Login
        if item.is_login() and item.login:
            self._user_edit.setText(item.login.username or "")
            self._pw_edit.setText(item.login.password or "")
            self._pw_edit.set_masked(True)
            self._totp_edit.setText(item.login.totp or "")
            self._clear_uris()
            for u in item.login.uris:
                self._add_uri_row(u.uri, u.match)
            self._tabs.setTabEnabled(0, True)
        else:
            self._tabs.setTabEnabled(0, False)

        # Card
        if item.is_card() and item.card:
            for key, widget in self._card_fields.items():
                val = item.card.get(key, "")
                if isinstance(widget, QSpinBox):
                    try:
                        widget.setValue(int(val) if val else (1 if key == "expMonth" else 2025))
                    except ValueError:
                        widget.setValue(1 if key == "expMonth" else 2025)
                else:
                    widget.setText(str(val))
            self._tabs.setTabEnabled(1, True)
        else:
            self._tabs.setTabEnabled(1, False)

        # Identity
        if item.is_identity() and item.identity:
            for key, edit in self._id_fields.items():
                edit.setText(str(item.identity.get(key, "")))
            self._tabs.setTabEnabled(2, True)
        else:
            self._tabs.setTabEnabled(2, False)

        # SSH
        if item.is_ssh_key() and item.sshKey:
            self._ssh_fp.setText(item.sshKey.keyFingerprint or "")
            self._ssh_pub.setPlainText(item.sshKey.publicKey or "")
            self._ssh_priv.setText(item.sshKey.privateKey or "")
            self._ssh_priv.set_masked(True)
            self._tabs.setTabEnabled(3, True)
        else:
            self._tabs.setTabEnabled(3, False)

        # Notes
        self._notes_edit.setPlainText(item.notes or "")

        # Custom fields
        self._clear_custom_fields()
        if item.fields:
            for f in item.fields:
                if isinstance(f, dict):
                    self._add_custom_field(f.get("name", ""), f.get("value", ""), f.get("type", 0))

        # Folder combo
        self._folder_combo.clear()
        folders = set()
        for i in all_items:
            if i.folderId:
                folders.add(i.folderId)
        self._folder_combo.addItem("(none)")
        for fid in sorted(folders):
            self._folder_combo.addItem(fid)
        self._folder_combo.setCurrentText(item.folderId or "(none)")

        # Collections
        if item.collectionIds:
            self._collections_edit.setText(", ".join(item.collectionIds))
        else:
            self._collections_edit.setText("")

        self._dirty = False
        self._save_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)

    def _clear_ui(self) -> None:
        self._item = None
        self._totp_countdown.stop()
        self._totp_timer.setText("")
        self._name_edit.clear()
        self._fav_check.setChecked(False)
        self._reprompt_check.setChecked(False)
        self._user_edit.clear()
        self._pw_edit.clear()
        self._totp_edit.clear()
        self._clear_uris()
        self._clear_custom_fields()
        for edit in self._card_fields.values():
            edit.clear()
        for edit in self._id_fields.values():
            edit.clear()
        self._ssh_fp.clear()
        self._ssh_pub.clear()
        self._ssh_priv.clear()
        self._notes_edit.clear()
        self._folder_combo.clear()
        self._collections_edit.clear()
        self._save_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)
        for i in range(self._tabs.count()):
            self._tabs.setTabEnabled(i, False)

    def _clear_uris(self) -> None:
        while self._uri_list.count():
            child = self._uri_list.takeAt(0)
            if child is None:
                continue
            w = child.widget()
            if w:
                w.deleteLater()
            del child

    def _clear_custom_fields(self) -> None:
        while self._cf_grid.count():
            child = self._cf_grid.takeAt(0)
            if child is None:
                continue
            w = child.widget()
            if w:
                w.deleteLater()
            del child
        self._cf_row = 0

    # ------------------------------------------------------------------
    # URI match helpers (Bitwarden uses int 0-5 or null for default)
    # ------------------------------------------------------------------
    _MATCH_LABELS = {
        None: "Default",
        0: "Base domain",
        1: "Host",
        2: "Starts with",
        3: "Exact",
        4: "Regular expression",
        5: "Never",
    }
    _MATCH_VALUES = {v: k for k, v in _MATCH_LABELS.items()}

    # ------------------------------------------------------------------
    # Dynamic rows
    # ------------------------------------------------------------------

    def _add_uri_row(self, uri: str = "", match: Optional[int] = None) -> None:
        row = QHBoxLayout()
        edit = QLineEdit(uri)
        edit.setPlaceholderText("https://example.com")
        edit.textChanged.connect(self._mark_dirty)
        # Validate URI format
        edit.textChanged.connect(lambda text: edit.setStyleSheet(
            "color: #f85149;" if text and not (text.startswith("http://") or text.startswith("https://") or text.startswith("ftp://") or "." in text) else ""
        ))
        row.addWidget(edit, 1)
        combo = QComboBox()
        combo.addItems(list(self._MATCH_LABELS.values()))
        combo.setCurrentText(self._MATCH_LABELS.get(match, "Default"))
        combo.currentTextChanged.connect(self._mark_dirty)
        row.addWidget(combo)
        btn = QPushButton("✕")
        btn.setFixedWidth(24)
        btn.setStyleSheet("border: none; color: #f85149;")
        btn.clicked.connect(lambda: self._remove_uri_row(row))  # type: ignore[misc]
        row.addWidget(btn)
        self._uri_list.addLayout(row)

    def _remove_uri_row(self, layout: QHBoxLayout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            if child is None:
                continue
            w = child.widget()
            if w:
                w.deleteLater()
            del child
        self._mark_dirty()

    def _add_custom_field(self, name: str = "", value: str = "", type_code: int = 0) -> None:
        row = QHBoxLayout()
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("Field name")
        name_edit.textChanged.connect(self._mark_dirty)
        row.addWidget(name_edit)
        val_edit = QLineEdit(value)
        val_edit.setPlaceholderText("Value")
        val_edit.textChanged.connect(self._mark_dirty)
        row.addWidget(val_edit, 1)
        type_combo = QComboBox()
        type_combo.addItems(["Text", "Hidden", "Boolean"])
        type_combo.setCurrentIndex(min(type_code, 2))
        type_combo.currentIndexChanged.connect(self._mark_dirty)
        row.addWidget(type_combo)
        btn = QPushButton("✕")
        btn.setFixedWidth(24)
        btn.setStyleSheet("border: none; color: #f85149;")
        btn.clicked.connect(lambda: self._remove_cf_row(row))  # type: ignore[misc]
        row.addWidget(btn)
        self._cf_grid.addLayout(row, self._cf_row, 0)
        self._cf_row += 1

    def _remove_cf_row(self, layout: QHBoxLayout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            if child is None:
                continue
            w = child.widget()
            if w:
                w.deleteLater()
            del child
        self._mark_dirty()

    # ------------------------------------------------------------------
    # Dirty handling
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        if not self._item:
            return
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._discard_btn.setEnabled(True)

    def _on_discard(self) -> None:
        if self._dirty:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Discard Changes",
                "You have unsaved changes. Discard them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._reload_item()

    def _reload_item(self) -> None:
        if self._item:
            self.load_item(self._item, self._all_items)

    def _generate_password(self) -> None:
        import secrets, string
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_+="
        pw = "".join(secrets.choice(alphabet) for _ in range(20))
        self._pw_edit.setText(pw)
        self._mark_dirty()

    def _update_pw_strength(self) -> None:
        pw = self._pw_edit.text()
        if not pw:
            self._pw_strength.setText("")
            return
        score = 0
        # Check common passwords
        common = {"password", "123456", "qwerty", "abc123", "letmein", "welcome", "admin", "login", "passw0rd", "111111", "123123", "password123", "1234567890", "admin123"}
        if pw.lower() in common:
            self._pw_strength.setText("<span style='color:#f85149;'>⚠️ Common password - easily guessed!</span>")
            return
        if len(pw) >= 8:
            score += 1
        if len(pw) >= 16:
            score += 1
        if any(c.isupper() for c in pw):
            score += 1
        if any(c.islower() for c in pw):
            score += 1
        if any(c.isdigit() for c in pw):
            score += 1
        if any(c in "!@#$%^&*-_+=" for c in pw):
            score += 1
        labels = ["🔴 Very Weak", "🟡 Weak", "🟠 Fair", "🟢 Good", "🟢 Strong", "🟢 Excellent"]
        colors = ["#f85149", "#d29922", "#d29922", "#3fb950", "#3fb950", "#58a6ff"]
        idx = min(score, len(labels) - 1)
        self._pw_strength.setText(f"<span style='color:{colors[idx]};'>{labels[idx]}</span>")

    def _update_totp_timer(self) -> None:
        import time
        now = int(time.time())
        remaining = 30 - (now % 30)
        if self._totp_edit.text():
            self._totp_timer.setText(f"⏱ TOTP expires in {remaining}s")
        else:
            self._totp_timer.setText("")

    def _update_notes_count(self) -> None:
        text = self._notes_edit.toPlainText()
        words = len(text.split()) if text else 0
        chars = len(text)
        self._notes_count.setText(f"{words} words, {chars} chars")

    # ------------------------------------------------------------------
    # Save back to item
    # ------------------------------------------------------------------

    def _save_changes(self) -> None:
        if not self._item or not self._dirty:
            return
        # Track old password for history
        old_password = None
        if self._item.is_login() and self._item.login:
            old_password = self._item.login.password

        item = self._item
        item.name = self._name_edit.text().strip()
        item.favorite = self._fav_check.isChecked()
        item.reprompt = 1 if self._reprompt_check.isChecked() else 0
        item.notes = self._notes_edit.toPlainText().strip() or None
        # Update revisionDate on any edit (Bitwarden schema compliance)
        from datetime import datetime, timezone
        item.revisionDate = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Login
        if item.is_login():
            if item.login is None:
                item.login = LoginData()
            item.login.username = self._user_edit.text().strip() or None
            item.login.password = self._pw_edit.text() or None
            item.login.totp = self._totp_edit.text().strip() or None
            uris: List[UriEntry] = []
            for i in range(self._uri_list.count()):
                layout = self._uri_list.itemAt(i)
                if not layout or not isinstance(layout, QHBoxLayout):
                    continue
                item0 = layout.itemAt(0)
                item1 = layout.itemAt(1)
                edit = item0.widget() if item0 else None
                combo = item1.widget() if item1 else None
                if isinstance(edit, QLineEdit) and isinstance(combo, QComboBox):
                    u = edit.text().strip()
                    if u:
                        match_val = self._MATCH_VALUES.get(combo.currentText())
                        uris.append(UriEntry(match=match_val, uri=u))
            item.login.uris = uris

        # Card
        if item.is_card():
            if item.card is None:
                item.card = {}
            for key, edit in self._card_fields.items():
                item.card[key] = edit.text().strip() or None

        # Identity
        if item.is_identity():
            if item.identity is None:
                item.identity = {}
            for key, edit in self._id_fields.items():
                item.identity[key] = edit.text().strip() or None

        # SSH
        if item.is_ssh_key():
            if item.sshKey is None:
                item.sshKey = SshKeyData()
            item.sshKey.publicKey = self._ssh_pub.toPlainText().strip() or None
            item.sshKey.privateKey = self._ssh_priv.text() or None

        # Custom fields
        fields: List[Dict[str, Any]] = []
        seen_names: set[str] = set()
        for i in range(self._cf_grid.count()):
            layout = self._cf_grid.itemAt(i)
            if not layout or not isinstance(layout, QHBoxLayout):
                continue
            widgets = []
            for j in range(layout.count()):
                it = layout.itemAt(j)
                widgets.append(it.widget() if it else None)
            if len(widgets) >= 3:
                name_edit = widgets[0]
                val_edit = widgets[1]
                type_combo = widgets[2]
                if isinstance(name_edit, QLineEdit) and isinstance(val_edit, QLineEdit) and isinstance(type_combo, QComboBox):
                    n = name_edit.text().strip()
                    v = val_edit.text().strip()
                    if n and n not in seen_names:
                        seen_names.add(n)
                        fields.append({
                            "name": n,
                            "value": v,
                            "type": type_combo.currentIndex(),
                        })
        item.fields = fields if fields else None

        # Folder
        folder = self._folder_combo.currentText().strip()
        item.folderId = folder if folder != "(none)" else None

        # Collections
        ctext = self._collections_edit.text().strip()
        if ctext:
            item.collectionIds = [c.strip() for c in ctext.split(",") if c.strip()]
        else:
            item.collectionIds = None

        # Update password history if password changed
        if old_password and self._item.login:
            new_password = self._item.login.password
            if new_password and new_password != old_password:
                if self._item.passwordHistory is None:
                    self._item.passwordHistory = []
                self._item.passwordHistory.append({
                    "lastUsedDate": self._item.revisionDate,
                    "password": old_password
                })
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)
        self.item_changed.emit()

    def _validate_card(self, number: str) -> bool:
        """Luhn algorithm validation for credit card numbers."""
        if not number:
            return True
        digits = [int(c) for c in number if c.isdigit()]
        if len(digits) < 13:
            return False
        if len(digits) > 19:
            return False
        check = digits.pop()
        digits.reverse()
        for i in range(len(digits)):
            if i % 2 == 0:
                digits[i] *= 2
                if digits[i] > 9:
                    digits[i] -= 9
        return (sum(digits) + check) % 10 == 0

    def _validate_card_expiry(self) -> bool:
        """Check if card expiry is in the future."""
        month_str = self._card_fields.get("expMonth", QLineEdit()).text().strip()
        year_str = self._card_fields.get("expYear", QLineEdit()).text().strip()
        if not month_str or not year_str:
            return True
        try:
            from datetime import datetime
            month = int(month_str)
            year = int(year_str)
            if year < 100:
                year += 2000
            if month < 1 or month > 12:
                return False
            expiry = datetime(year, month, 1)
            return expiry >= datetime.now()
        except (ValueError, OverflowError):
            return False

    def is_dirty(self) -> bool:
        return self._dirty

    def current_item(self) -> Optional[BwItem]:
        return self._item
