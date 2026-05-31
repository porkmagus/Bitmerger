"""
Premium visual effects for Bitmerger — shadows, animations, toasts, empty states.

All helpers are non-invasive: they wrap or augment existing widgets without
changing their internal structure or behaviour.
"""

from __future__ import annotations

from typing import Optional, Callable, Any

from PySide6.QtCore import (
    QPropertyAnimation, QEasingCurve, QTimer, Qt, QPoint, QRect, QParallelAnimationGroup, QSequentialAnimationGroup
)
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QWidget, QHBoxLayout,
    QLabel, QFrame, QVBoxLayout, QPushButton, QTableWidget, QGraphicsEffect
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QBrush, QPen

from .theme import get_theme_manager


# ---------------------------------------------------------------------------
# Shadow helpers
# ---------------------------------------------------------------------------

def add_shadow(
    widget: QWidget,
    color: str = "#000000",
    blur: int = 20,
    x_offset: int = 0,
    y_offset: int = 4,
    opacity: float = 0.15,
) -> QGraphicsDropShadowEffect:
    """Add a subtle drop shadow to a widget.

    Returns the effect so callers can tweak it later.
    """
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    # Qt's drop shadow effect doesn't have a direct opacity setter on the effect
    # itself; opacity is baked into the color's alpha.
    c = QColor(color)
    c.setAlpha(int(255 * opacity))
    shadow.setColor(c)
    shadow.setOffset(x_offset, y_offset)
    widget.setGraphicsEffect(shadow)
    return shadow


def add_soft_shadow(widget: QWidget, dark: bool = True) -> QGraphicsDropShadowEffect:
    """Add a premium soft shadow appropriate for the current theme."""
    return add_shadow(widget, color="#000000", blur=24, x_offset=0, y_offset=6, opacity=0.12)


def add_inner_glow(widget: QWidget, color: str, radius: int = 10) -> None:
    """Add a subtle inner glow via stylesheet (no extra effect needed)."""
    widget.setStyleSheet(widget.styleSheet() + f"""
        {widget.__class__.__name__} {{
            border: 1px solid {color};
        }}
    """)


# ---------------------------------------------------------------------------
# Animation helpers
# ---------------------------------------------------------------------------

def animate_opacity(
    widget: QWidget,
    start: float = 0.0,
    end: float = 1.0,
    duration: int = 400,
    easing: QEasingCurve.Type = QEasingCurve.Type.InOutCubic,
) -> QPropertyAnimation:
    """Fade a widget in or out.  Creates a QGraphicsOpacityEffect if needed."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(start)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(easing)
    anim.start()
    return anim


def fade_in(widget: QWidget, duration: int = 400) -> QPropertyAnimation:
    """Smooth fade-in."""
    return animate_opacity(widget, 0.0, 1.0, duration)


def fade_out(widget: QWidget, duration: int = 300, on_finished: Optional[Callable[[], None]] = None) -> QPropertyAnimation:
    """Smooth fade-out with optional callback."""
    anim = animate_opacity(widget, 1.0, 0.0, duration)
    if on_finished:
        anim.finished.connect(on_finished)
    return anim


def slide_up(
    widget: QWidget,
    distance: int = 20,
    duration: int = 400,
    fade: bool = True,
) -> QParallelAnimationGroup:
    """Slide a widget up by *distance* px while optionally fading in."""
    group = QParallelAnimationGroup(widget)

    geo_anim = QPropertyAnimation(widget, b"pos")
    geo_anim.setDuration(duration)
    geo_anim.setStartValue(widget.pos() + QPoint(0, distance))
    geo_anim.setEndValue(widget.pos())
    geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    group.addAnimation(geo_anim)

    if fade:
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        op_anim = QPropertyAnimation(effect, b"opacity")
        op_anim.setDuration(duration)
        op_anim.setStartValue(0.0)
        op_anim.setEndValue(1.0)
        op_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(op_anim)

    group.start()
    return group


def pulse_opacity(widget: QWidget, min_opacity: float = 0.4, max_opacity: float = 1.0, duration: int = 1200) -> QPropertyAnimation:
    """Create an infinite looping pulse (e.g. for loading shimmer)."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(max_opacity)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(max_opacity)
    anim.setEndValue(min_opacity)
    anim.setEasingCurve(QEasingCurve.Type.InOutSine)
    anim.setLoopCount(-1)  # infinite
    anim.start()
    return anim


# ---------------------------------------------------------------------------
# Toast notification
# ---------------------------------------------------------------------------

class Toast(QFrame):
    """A temporary floating toast notification.

    Usage:
        toast = Toast(parent_widget, "Vault saved", kind="success")
        toast.show_at_bottom_right()
    """

    KINDS = {
        "info":    ("\u2139", "#58a6ff", "#1f6feb"),
        "success": ("\u2713", "#3fb950", "#238636"),
        "warning": ("\u26a0", "#d29922", "#9e6a03"),
        "error":   ("\u2715", "#f85149", "#da3633"),
    }

    def __init__(
        self,
        parent: QWidget,
        message: str,
        kind: str = "info",
        duration_ms: int = 3000,
    ) -> None:
        super().__init__(parent)
        self._duration = duration_ms
        self._parent = parent
        self.setObjectName("Toast")
        self.setFrameShape(QFrame.Shape.NoFrame)

        icon, text_color, border_color = self.KINDS.get(kind, self.KINDS["info"])
        tm = get_theme_manager()
        p = tm.palette()

        self.setStyleSheet(f"""
            QFrame#Toast {{
                background: {p["surface"]};
                border: 1px solid {border_color};
                border-radius: 10px;
                padding: 12px 16px;
            }}
            QLabel {{
                color: {text_color};
                font-size: 13px;
                font-weight: 500;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 16, 8)
        layout.setSpacing(10)

        self._icon = QLabel(icon)
        self._icon.setStyleSheet(f"font-size: 16px; color: {text_color};")
        layout.addWidget(self._icon)

        self._label = QLabel(message)
        layout.addWidget(self._label, 1)

        # Close button
        self._close_btn = QPushButton("\u2715")
        self._close_btn.setFlat(True)
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                color: {p["muted"]};
                font-size: 14px;
                padding: 2px 6px;
            }}
            QPushButton:hover {{
                color: {text_color};
            }}
        """)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self._dismiss)
        layout.addWidget(self._close_btn)

        self.setFixedHeight(48)
        self.adjustSize()
        self.hide()

        # Auto-dismiss timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)

    def show_at_bottom_right(self, margin: int = 20) -> None:
        """Position at bottom-right of parent and animate in."""
        parent = self._parent
        if not parent:
            return
        self.adjustSize()
        x = parent.width() - self.width() - margin
        y = parent.height() - self.height() - margin
        self.move(x, y)
        self.show()
        self.raise_()
        slide_up(self, distance=16, duration=350)
        self._timer.start(self._duration)

    def show_at(self, x: int, y: int) -> None:
        self.move(x, y)
        self.show()
        self.raise_()
        slide_up(self, distance=12, duration=300)
        self._timer.start(self._duration)

    def _dismiss(self) -> None:
        fade_out(self, duration=250, on_finished=self.deleteLater)


# ---------------------------------------------------------------------------
# Empty state widget
# ---------------------------------------------------------------------------

class EmptyState(QWidget):
    """A styled empty-state overlay for tables / lists.

    Usage inside a QStackedWidget or as a placeholder:
        state = EmptyState(table, icon="\U0001f50d", title="No matches", subtitle="Try a different search.")
    """

    def __init__(
        self,
        parent: QWidget,
        icon: str = "\U0001f4ec",
        title: str = "Nothing here",
        subtitle: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")
        tm = get_theme_manager()
        p = tm.palette()

        self.setStyleSheet(f"""
            QWidget#EmptyState {{
                background: transparent;
            }}
            QLabel#EmptyIcon {{
                font-size: 40px;
                color: {p["muted"]};
                padding: 12px;
            }}
            QLabel#EmptyTitle {{
                font-size: 15px;
                font-weight: 600;
                color: {p["fg"]};
                padding: 4px;
            }}
            QLabel#EmptySubtitle {{
                font-size: 13px;
                color: {p["muted"]};
                padding: 4px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self._icon = QLabel(icon)
        self._icon.setObjectName("EmptyIcon")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon)

        self._title = QLabel(title)
        self._title.setObjectName("EmptyTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        self._subtitle: Optional[QLabel] = None
        if subtitle:
            self._subtitle = QLabel(subtitle)
            self._subtitle.setObjectName("EmptySubtitle")
            self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._subtitle.setWordWrap(True)
            layout.addWidget(self._subtitle)

        self.hide()

    def set_text(self, title: str, subtitle: str = "", icon: str = "") -> None:
        self._title.setText(title)
        if self._subtitle:
            self._subtitle.setText(subtitle)
        if icon:
            self._icon.setText(icon)


# ---------------------------------------------------------------------------
# Table wrapper with fade-in
# ---------------------------------------------------------------------------

class AnimatedTable:
    """Mixin-style helper that adds a fade-in animation when a table is populated.

    Usage:
        class MyTable(QTableWidget, AnimatedTable):
            def set_items(self, items):
                super().set_items(items)
                self.animate_populate()
    """

    def animate_populate(self, duration: int = 350) -> None:
        """Call after populating the table to get a smooth fade-in."""
        if not isinstance(self, QWidget):
            return
        fade_in(self, duration)


# ---------------------------------------------------------------------------
# Premium button with hover scale
# ---------------------------------------------------------------------------

class PremiumButton(QPushButton):
    """A button that subtly scales on hover (1.0 -> 1.02) for tactile feel.

    Uses a container-based approach so the shadow effect is not clobbered.
    """

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._shadow: Optional[QGraphicsDropShadowEffect] = None
        self._apply_shadow()

    def _apply_shadow(self) -> None:
        self._shadow = add_shadow(self, blur=12, x_offset=0, y_offset=2, opacity=0.08)

    def enterEvent(self, event: Any) -> None:
        super().enterEvent(event)
        if self._shadow:
            self._shadow.setBlurRadius(20)
            self._shadow.setOffset(0, 6)
            c = self._shadow.color()
            c.setAlpha(int(255 * 0.15))
            self._shadow.setColor(c)

    def leaveEvent(self, event: Any) -> None:
        super().leaveEvent(event)
        if self._shadow:
            self._shadow.setBlurRadius(12)
            self._shadow.setOffset(0, 2)
            c = self._shadow.color()
            c.setAlpha(int(255 * 0.08))
            self._shadow.setColor(c)


# ---------------------------------------------------------------------------
# Header card widget
# ---------------------------------------------------------------------------

class HeaderCard(QFrame):
    """A premium header bar with gradient background and subtle shadow.

    Replaces a plain QLabel header.
    """

    def __init__(self, title: str, subtitle: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderCard")
        tm = get_theme_manager()
        p = tm.palette()
        dark = tm.is_dark()

        # Use a gradient background
        grad_start = p["bg"]
        grad_end = p["surface"]
        self.setStyleSheet(f"""
            QFrame#HeaderCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {grad_start}, stop:1 {grad_end});
                border: 1px solid {p["border"]};
                border-radius: 12px;
                padding: 14px 18px;
            }}
            QLabel#HeaderTitle {{
                font-size: 18px;
                font-weight: 700;
                color: {p["fg"]};
            }}
            QLabel#HeaderSubtitle {{
                font-size: 12px;
                color: {p["muted"]};
                margin-top: 2px;
            }}
        """)

        add_soft_shadow(self, dark=dark)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._title = QLabel(title)
        self._title.setObjectName("HeaderTitle")
        layout.addWidget(self._title)

        self._subtitle: Optional[QLabel] = None
        if subtitle:
            self._subtitle = QLabel(subtitle)
            self._subtitle.setObjectName("HeaderSubtitle")
            layout.addWidget(self._subtitle)

        self.setMaximumHeight(80)


# ---------------------------------------------------------------------------
# Loading shimmer placeholder
# ---------------------------------------------------------------------------

class ShimmerRow(QFrame):
    """A single shimmer row for loading placeholders.

    Use a few of these inside a container while data is loading.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        tm = get_theme_manager()
        p = tm.palette()
        self.setStyleSheet(f"""
            QFrame {{
                background: {p["surface"]};
                border-radius: 6px;
                min-height: 32px;
                max-height: 32px;
            }}
        """)
        self.setMinimumHeight(32)
        self._anim = pulse_opacity(self, min_opacity=0.35, max_opacity=0.65, duration=1400)


class ShimmerBlock(QFrame):
    """A block of shimmer rows."""

    def __init__(self, rows: int = 6, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)
        for _ in range(rows):
            layout.addWidget(ShimmerRow(self))
        self.setStyleSheet("background: transparent; border: none;")


# ---------------------------------------------------------------------------
# Smooth-scroll helper
# ---------------------------------------------------------------------------

def enable_smooth_scroll(scroll_area: QWidget) -> None:
    """Enable smooth scrolling on a QScrollArea or QAbstractScrollArea.

    This is a best-effort setting — Qt may still snap depending on platform.
    """
    from PySide6.QtWidgets import QAbstractScrollArea
    if isinstance(scroll_area, QAbstractScrollArea):
        # QAbstractScrollArea does not have setVerticalScrollMode in PySide6;
        # it lives on QAbstractItemView.  Try both.
        try:
            scroll_area.setVerticalScrollMode(QAbstractScrollArea.ScrollMode.ScrollPerPixel)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            scroll_area.setHorizontalScrollMode(QAbstractScrollArea.ScrollMode.ScrollPerPixel)  # type: ignore[attr-defined]
        except Exception:
            pass
        scroll_area.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
