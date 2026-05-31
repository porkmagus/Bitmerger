"""
Bitmerger icon & badge helpers.

Provides type icons, colored badges, and confidence score bars that work across
themes (light / dark).  Uses Unicode glyphs + styled QTableWidgetItem cells.
"""

from typing import Optional, Tuple
from PySide6.QtWidgets import QTableWidgetItem
from PySide6.QtGui import QColor, QBrush
from PySide6.QtCore import Qt

from .theme import ThemeManager, get_theme_manager

# ---------------------------------------------------------------------------
# Type constants
# ---------------------------------------------------------------------------

TYPE_META: dict[int, Tuple[str, str, str]] = {
    1: ("Login", "🔑", "#58a6ff"),       # Blue
    2: ("Note", "📝", "#8b949e"),        # Gray
    3: ("Card", "💳", "#3fb950"),        # Green
    4: ("Identity", "🪪", "#a371f7"),    # Purple
    5: ("SSH", "🔐", "#d29922"),         # Orange
}

# Dark-theme variants (slightly muted so they don't bleed)
TYPE_META_DARK: dict[int, Tuple[str, str, str]] = {
    1: ("Login", "🔑", "#79b8ff"),
    2: ("Note", "📝", "#b0b8c1"),
    3: ("Card", "💳", "#56d364"),
    4: ("Identity", "🪪", "#bc8cff"),
    5: ("SSH", "🔐", "#e3b341"),
}


def _get_meta(type_code: int) -> Tuple[str, str, str]:
    tm = get_theme_manager()
    if tm.is_dark():
        return TYPE_META_DARK.get(type_code, ("Other", "❓", "#8b949e"))
    return TYPE_META.get(type_code, ("Other", "❓", "#656d76"))


def type_name(type_code: int) -> str:
    return _get_meta(type_code)[0]


def type_icon(type_code: int) -> str:
    return _get_meta(type_code)[1]


def type_color(type_code: int) -> str:
    return _get_meta(type_code)[2]


def type_color_q(type_code: int) -> QColor:
    return QColor(type_color(type_code))


def type_badge_text(type_code: int) -> str:
    icon, name = type_icon(type_code), type_name(type_code)
    # Use ASCII fallback on Windows if emoji renders as blank
    import sys
    if sys.platform == "win32":
        fallbacks = {"🔑": "[L]", "📝": "[N]", "💳": "[C]", "🪪": "[I]", "🔐": "[S]", "❓": "[?]"}
        icon = fallbacks.get(icon, icon)
    return f"{icon} {name}"

# ---------------------------------------------------------------------------
# Confidence badge
# ---------------------------------------------------------------------------

def confidence_badge(conf: float) -> Tuple[str, str]:
    """Return (text, color_hex) for a confidence score."""
    if conf >= 0.95:
        return ("🟢 High", "#3fb950" if get_theme_manager().is_dark() else "#1a7f37")
    if conf >= 0.85:
        return ("🟡 Medium", "#d29922" if get_theme_manager().is_dark() else "#9a6700")
    return ("🔴 Low", "#f85149" if get_theme_manager().is_dark() else "#cf222e")


def confidence_bar_blocks(conf: float) -> str:
    """A small 5-block bar rendered in text."""
    filled = int(conf * 5)
    empty = 5 - filled
    return "█" * filled + "░" * empty

# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

def make_type_item(type_code: int) -> QTableWidgetItem:
    """Return a QTableWidgetItem with the type badge pre-styled."""
    name, icon, color = _get_meta(type_code)
    item = QTableWidgetItem(f"{icon} {name}")
    item.setForeground(QBrush(QColor(color)))
    item.setData(Qt.ItemDataRole.UserRole, type_code)
    item.setToolTip(name)
    return item


def make_confidence_item(conf: float) -> QTableWidgetItem:
    """Return a QTableWidgetItem with confidence text + color."""
    text, color = confidence_badge(conf)
    bar = confidence_bar_blocks(conf)
    item = QTableWidgetItem(f"{bar}  {text}  ({conf:.0%})")
    item.setForeground(QBrush(QColor(color)))
    item.setData(Qt.ItemDataRole.UserRole, conf)
    item.setToolTip(f"Confidence: {conf:.2%}")
    return item


def make_domain_item(domain: str) -> QTableWidgetItem:
    """Domain item with subtle styling."""
    item = QTableWidgetItem(domain)
    item.setForeground(QBrush(QColor("#8b949e" if get_theme_manager().is_dark() else "#656d76")))
    return item
