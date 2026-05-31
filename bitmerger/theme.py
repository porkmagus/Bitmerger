"""
Bitmerger theme manager — Dark / Light / Auto mode support.

Provides palette constants, stylesheet generators, and a stateful ThemeManager.
"""

from enum import Enum, auto
from typing import Dict, Any, Optional
from PySide6.QtCore import QObject, Signal, QSettings
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor


class Theme(Enum):
    LIGHT = auto()
    DARK = auto()
    AUTO = auto()


class ThemeManager(QObject):
    theme_changed = Signal()

    _instance: Optional["ThemeManager"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, app: Optional[QApplication] = None) -> None:
        super().__init__(None)
        self._app = app
        self._theme = Theme.AUTO
        self._load_theme()

    def _load_theme(self) -> None:
        settings = QSettings("bitmerger", "Bitmerger")
        raw = str(settings.value("theme", "auto") or "auto")
        try:
            self._theme = Theme[raw.upper()]
        except (KeyError, AttributeError):
            self._theme = Theme.AUTO

    def save_theme(self) -> None:
        settings = QSettings("bitmerger", "Bitmerger")
        settings.setValue("theme", self._theme.name.lower())

    def set_theme(self, theme: Theme) -> None:
        if self._theme == theme:
            return
        self._theme = theme
        self._apply_stylesheet()
        self.save_theme()
        self.theme_changed.emit()

    def current_theme(self) -> Theme:
        if self._theme == Theme.AUTO:
            # Detect system dark mode via QApplication
            if self._app:
                # macOS / modern Qt: palette or style hints
                # Simple heuristic: use QStyleHints
                try:
                    from PySide6.QtCore import Qt
                    color_scheme = self._app.styleHints().colorScheme()
                    if color_scheme == Qt.ColorScheme.Dark:
                        return Theme.DARK
                except Exception:
                    pass
        # Fallback: check palette darkness if styleHints fails
        try:
            if self._app:
                palette = self._app.palette()
                bg = palette.color(self._app.palette().ColorRole.Window)
                if bg.lightness() < 128:
                    return Theme.DARK
        except Exception:
            pass
        return self._theme if self._theme != Theme.AUTO else Theme.LIGHT

    def is_dark(self) -> bool:
        return self.current_theme() == Theme.DARK

    def palette(self) -> Dict[str, str]:
        if self.is_dark():
            return {
                "bg": "#0d1117",
                "fg": "#c9d1d9",
                "surface": "#161b22",
                "border": "#30363d",
                "accent": "#58a6ff",
                "accent_hover": "#79b8ff",
                "success": "#3fb950",
                "warning": "#d29922",
                "danger": "#f85149",
                "muted": "#8b949e",
                "selection": "#1f6feb",
                "row_alt": "#161b22",
                "row": "#0d1117",
                "input_bg": "#21262d",
                "header": "#1f242c",
            }
        else:
            return {
                "bg": "#ffffff",
                "fg": "#24292f",
                "surface": "#f6f8fa",
                "border": "#d0d7de",
                "accent": "#0969da",
                "accent_hover": "#0550ae",
                "success": "#1a7f37",
                "warning": "#9a6700",
                "danger": "#cf222e",
                "muted": "#656d76",
                "selection": "#0969da",
                "row_alt": "#f6f8fa",
                "row": "#ffffff",
                "input_bg": "#ffffff",
                "header": "#eaeef2",
            }

    def _apply_stylesheet(self, widget=None) -> None:
        target = widget or self._app
        if target:
            target.setStyleSheet(self.stylesheet())

    def stylesheet(self) -> str:
        p = self.palette()
        return f"""
        QMainWindow {{
            background: {p["bg"]};
            color: {p["fg"]};
        }}
        QFrame, QScrollArea, QStackedWidget {{
            background: {p["bg"]};
            border: none;
        }}
        /* Round 1: Global smooth transitions */
        QPushButton, QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox::indicator {{
            transition: all 150ms ease;
        }}
        QGroupBox {{
            font-weight: bold;
            border: 1px solid {p["border"]};
            border-radius: 10px;
            margin-top: 12px;
            padding-top: 12px;
            padding-bottom: 12px;
            padding-left: 14px;
            padding-right: 14px;
            background: {p["surface"]};
            font-size: 13px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 8px;
            color: {p["accent"]};
            font-weight: 600;
        }}
        QPushButton {{
            background: {p["input_bg"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            padding: 6px 16px;
            color: {p["fg"]};
            font-weight: 500;
        }}
        QPushButton:hover {{
            background: {p["border"]};
            border-color: {p["accent"]};
            color: {p["accent"]};
        }}
        QPushButton:focus {{
            border-color: {p["accent"]};
            outline: 2px solid {p["accent"]};
            outline-offset: 2px;
        }}
        QPushButton:pressed {{
            background: {p["accent"]};
            color: {p["bg"]};
        }}
        QPushButton:disabled {{
            background: {p["surface"]};
            color: {p["muted"]};
            border-color: {p["border"]};
        }}
        QLineEdit, QTextEdit {{
            background: {p["input_bg"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            padding: 6px;
            color: {p["fg"]};
            selection-background-color: {p["accent"]};
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border-color: {p["accent"]};
            background: {p["surface"]};
            outline: none;
        }}
        QLineEdit:hover, QTextEdit:hover {{
            border-color: {p["muted"]};
        }}
        QComboBox {{
            background: {p["input_bg"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            padding: 6px 10px;
            color: {p["fg"]};
            font-size: 13px;
        }}
        QComboBox:hover {{
            border-color: {p["muted"]};
        }}
        QComboBox:focus {{
            border-color: {p["accent"]};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background: {p["surface"]};
            color: {p["fg"]};
            border: 1px solid {p["border"]};
            selection-background-color: {p["accent"]};
        }}
        QTableWidget {{
            background: {p["bg"]};
            alternate-background-color: {p["row_alt"]};
            gridline-color: {p["border"]};
            border: 1px solid {p["border"]};
            border-radius: 8px;
            selection-background-color: {p["selection"]};
            color: {p["fg"]};
            outline: none;
        }}
        QTableWidget::item:hover {{
            background: {p["border"]};
        }}
        QTableWidget::item:selected {{
            background: {p["selection"]};
            color: {p["bg"]};
            border-radius: 4px;
        }}
        QTableWidget::item {{
            padding: 6px 8px;
            border: none;
        }}
        QHeaderView::section {{
            background: {p["header"]};
            padding: 10px 12px;
            border: 1px solid {p["border"]};
            font-weight: 600;
            color: {p["fg"]};
            font-size: 13px;
        }}
        QHeaderView::section:hover {{
            background: {p["border"]};
        }}
        QTabWidget::pane {{
            border: 1px solid {p["border"]};
            border-radius: 8px;
            background: {p["surface"]};
            top: -1px;
        }}
        QTabBar::tab {{
            background: {p["surface"]};
            border: 1px solid {p["border"]};
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            padding: 10px 20px;
            margin-right: 3px;
            color: {p["muted"]};
            font-weight: 500;
            font-size: 13px;
        }}
        QTabBar::tab:selected {{
            background: {p["bg"]};
            color: {p["accent"]};
            border-bottom: 3px solid {p["accent"]};
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            color: {p["fg"]};
            background: {p["border"]};
        }}
        QProgressBar {{
            border: 1px solid {p["border"]};
            border-radius: 6px;
            text-align: center;
            background: {p["surface"]};
            font-size: 12px;
            font-weight: 500;
            color: {p["fg"]};
            min-height: 20px;
            max-height: 20px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {p["accent"]}, stop:1 {p["accent_hover"]});
            border-radius: 5px;
            margin: 1px;
        }}
        QCheckBox {{
            spacing: 6px;
            color: {p["fg"]};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 2px solid {p["border"]};
            background: {p["input_bg"]};
        }}
        QCheckBox::indicator:hover {{
            border-color: {p["accent"]};
        }}
        QCheckBox::indicator:checked {{
            background: {p["accent"]};
            border-color: {p["accent"]};
            image: none;
        }}
        QCheckBox::indicator:checked::after {{
            content: "✓";
            color: {p["bg"]};
            font-weight: bold;
        }}
        QSpinBox, QDoubleSpinBox {{
            background: {p["input_bg"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            padding: 4px 8px;
            color: {p["fg"]};
            font-size: 13px;
        }}
        QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {p["muted"]};
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {p["accent"]};
        }}
        QScrollBar:vertical {{
            background: {p["surface"]};
            width: 12px;
            border-radius: 6px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {p["border"]};
            border-radius: 6px;
            min-height: 30px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {p["muted"]};
        }}
        QScrollBar::handle:vertical:pressed {{
            background: {p["accent"]};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: {p["surface"]};
            height: 12px;
            border-radius: 6px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {p["border"]};
            border-radius: 6px;
            min-width: 30px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {p["muted"]};
        }}
        QScrollBar::handle:horizontal:pressed {{
            background: {p["accent"]};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QLabel {{
            color: {p["fg"]};
        }}
        QLabel[muted="true"] {{
            color: {p["muted"]};
        }}
        QSplitter::handle {{
            background: {p["border"]};
            border-radius: 2px;
        }}
        QSplitter::handle:hover {{
            background: {p["accent"]};
        }}
        QSplitter::handle:horizontal {{
            width: 4px;
            margin: 0 2px;
        }}
        QSplitter::handle:vertical {{
            height: 4px;
            margin: 2px 0;
        }}
        QMenu {{
            background: {p["surface"]};
            border: 1px solid {p["border"]};
            color: {p["fg"]};
            border-radius: 8px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 8px 16px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background: {p["accent"]};
            color: {p["bg"]};
        }}
        QMenu::separator {{
            height: 1px;
            background: {p["border"]};
            margin: 6px 12px;
        }}
        QMenuBar {{
            background: {p["surface"]};
            color: {p["fg"]};
        }}
        QMenuBar::item:selected {{
            background: {p["accent"]};
            color: {p["bg"]};
        }}
        QToolTip {{
            background: {p["surface"]};
            color: {p["fg"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 500;
        }}
        QDialogButtonBox QPushButton {{
            background: {p["input_bg"]};
            border: 1px solid {p["border"]};
            border-radius: 6px;
            padding: 4px 12px;
            color: {p["fg"]};
            font-weight: 500;
        }}
        QDialogButtonBox QPushButton:hover {{
            background: {p["border"]};
            border-color: {p["accent"]};
        }}
        """

    def get_color(self, key: str) -> QColor:
        return QColor(self.palette().get(key, "#000000"))


def get_theme_manager(app: Optional[QApplication] = None) -> ThemeManager:
    return ThemeManager(app)
