"""
Bitmerger fluidity — subtle motion and responsive feedback for the GUI.

All animations are short (<200 ms), non-blocking, and use Qt native
QPropertyAnimation + QGraphicsOpacityEffect.  No CSS transitions (Qt
ignores them in stylesheets).

Key invariant: a widget never has more than one QGraphicsEffect attached
at a time.  ``_ensure_opacity_effect()`` always replaces the previous
effect to prevent the stacking bug that caused the premium.py regressions.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QTimer,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QGraphicsOpacityEffect,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QWidget,
)

# ---------------------------------------------------------------------------
# Duration constants — snappy, not theatrical
# ---------------------------------------------------------------------------

FADE_IN_DURATION: int = 150        # ms
FADE_OUT_DURATION: int = 100       # ms
HOVER_LIFT_DURATION: int = 80      # ms
PULSE_DURATION: int = 120          # ms
STAGGER_DELAY: int = 8             # ms per row for table population
TABLE_ROW_FADE: int = 100          # ms per row


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _ensure_opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    """Get or create a QGraphicsOpacityEffect on *widget*.

    If the widget already has a different effect (e.g. a shadow) it is
    replaced — we never stack effects because that caused the premium.py
    regressions.
    """
    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsOpacityEffect):
        return effect
    # Clear any existing effect to prevent stacking.
    if effect is not None:
        widget.setGraphicsEffect(None)  # type: ignore[arg-type]
    opacity: QGraphicsOpacityEffect = QGraphicsOpacityEffect(widget)
    opacity.setOpacity(1.0)
    widget.setGraphicsEffect(opacity)
    return opacity


def _stop_if_running(anim: Optional[QPropertyAnimation]) -> None:
    if anim is not None and anim.state() == QPropertyAnimation.State.Running:
        anim.stop()


def fade_in(
    widget: QWidget, duration: int = FADE_IN_DURATION
) -> QPropertyAnimation:
    """Fade *widget* from invisible to visible."""
    widget.setVisible(True)
    effect = _ensure_opacity_effect(widget)
    effect.setOpacity(0.0)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    return anim


def fade_out(
    widget: QWidget,
    duration: int = FADE_OUT_DURATION,
    on_finished: Optional[Callable[[], None]] = None,
) -> QPropertyAnimation:
    """Fade *widget* to invisible, then hide it."""
    effect = _ensure_opacity_effect(widget)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(effect.opacity())
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)
    if on_finished is not None:
        anim.finished.connect(on_finished)
    else:
        anim.finished.connect(widget.hide)
    return anim


# ---------------------------------------------------------------------------
# SmoothVisibility — fade widgets in/out
# ---------------------------------------------------------------------------


class SmoothVisibility:
    """Wrap a widget so that ``show()`` / ``hide()`` fade instead of
    hard-toggling ``setVisible``."""

    def __init__(self, widget: QWidget) -> None:
        self._widget = widget
        self._anim: Optional[QPropertyAnimation] = None

    def show(self) -> None:
        if self._widget.isVisible():
            return
        self._widget.setVisible(True)
        self._anim = fade_in(self._widget)
        self._anim.start()

    def hide(self) -> None:
        if not self._widget.isVisible():
            return
        _stop_if_running(self._anim)
        self._anim = fade_out(self._widget)
        self._anim.start()


# ---------------------------------------------------------------------------
# FadeTabWidget — tab content fades in on switch
# ---------------------------------------------------------------------------


class FadeTabWidget(QTabWidget):
    """QTabWidget that fades in new tab content on switch."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_index: int = -1
        self._anim: Optional[QPropertyAnimation] = None
        self.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        if index == self._current_index:
            return
        self._current_index = index
        widget = self.widget(index)
        if widget is None:
            return
        _stop_if_running(self._anim)
        self._anim = fade_in(widget, duration=FADE_IN_DURATION)
        self._anim.start()


# ---------------------------------------------------------------------------
# Table refresh — fade out, repopulate, fade in
# ---------------------------------------------------------------------------


def animate_table_refresh(
    table: QTableWidget,
    populate_fn: Callable[[], None],
) -> None:
    """Fade *table* out, call *populate_fn*, then fade back in.

    Only makes sense for tables with a decent number of rows so the
    fade is noticeable.  For tiny tables call *populate_fn* directly.
    """
    effect = _ensure_opacity_effect(table)

    fade_out_anim = QPropertyAnimation(effect, b"opacity")
    fade_out_anim.setDuration(80)
    fade_out_anim.setStartValue(1.0)
    fade_out_anim.setEndValue(0.3)
    fade_out_anim.setEasingCurve(QEasingCurve.Type.InCubic)

    def _on_fade_out_done() -> None:
        populate_fn()
        fade_in_anim = QPropertyAnimation(effect, b"opacity")
        fade_in_anim.setDuration(150)
        fade_in_anim.setStartValue(0.3)
        fade_in_anim.setEndValue(1.0)
        fade_in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade_in_anim.start()

    fade_out_anim.finished.connect(_on_fade_out_done)
    fade_out_anim.start()


# ---------------------------------------------------------------------------
# ButtonPulse — subtle opacity dip on press / release
# ---------------------------------------------------------------------------


class _ButtonPressFilter(QObject):
    """Event filter that drives ButtonPulse animations."""

    def __init__(self, pulse: "ButtonPulse") -> None:
        super().__init__()
        self._pulse = pulse

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            self._press()
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._release()
        return False  # do not eat the event

    def _press(self) -> None:
        btn = self._pulse._button
        _stop_if_running(self._pulse._anim)
        self._pulse._anim = QPropertyAnimation(btn, b"windowOpacity")
        self._pulse._anim.setDuration(HOVER_LIFT_DURATION)
        self._pulse._anim.setStartValue(1.0)
        self._pulse._anim.setEndValue(0.85)
        self._pulse._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._pulse._anim.start()

    def _release(self) -> None:
        btn = self._pulse._button
        _stop_if_running(self._pulse._anim)
        self._pulse._anim = QPropertyAnimation(btn, b"windowOpacity")
        self._pulse._anim.setDuration(PULSE_DURATION)
        self._pulse._anim.setStartValue(0.85)
        self._pulse._anim.setEndValue(1.0)
        self._pulse._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pulse._anim.start()


class ButtonPulse:
    """Add a subtle opacity pulse to a QPushButton on press / release."""

    def __init__(self, button: QPushButton) -> None:
        self._button = button
        self._anim: Optional[QPropertyAnimation] = None
        self._filter = _ButtonPressFilter(self)
        self._button.installEventFilter(self._filter)


# ---------------------------------------------------------------------------
# StatusPulse — flash accent colour when status text changes
# ---------------------------------------------------------------------------


class StatusPulse:
    """Flash the status label colour when text changes."""

    def __init__(self, label: QLabel) -> None:
        self._label = label
        self._timer: Optional[QTimer] = None
        self._original_style: str = label.styleSheet()
        self._original_set_text = label.setText
        # Monkey-patch setText on this instance so every call triggers a flash.
        label.setText = self._wrapped_set_text  # type: ignore[method-assign]

    # The wrapped method impersonates QLabel.setText so it can be
    # assigned to label.setText at __init__ time.  The real `self` is
    # QLabel, not StatusPulse — mypy complains about the mismatch.
    def _wrapped_set_text(self, text: str) -> None:
        self._original_set_text(text)
        self._flash()

    def _flash(self) -> None:
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()
        try:
            from .theme import get_theme_manager
            accent = get_theme_manager().palette().get("accent", "#58a6ff")
        except Exception:
            accent = "#58a6ff"
        self._label.setStyleSheet(
            f"color: {accent}; font-weight: 600; padding: 4px;"
        )
        self._timer = QTimer(self._label)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._restore)
        self._timer.start(400)

    def _restore(self) -> None:
        self._label.setStyleSheet(self._original_style)


# ---------------------------------------------------------------------------
# CheckboxPulse — subtle opacity bounce on toggle
# ---------------------------------------------------------------------------


class CheckboxPulse:
    """Subtle opacity pulse on QCheckBox toggle for tactile feedback."""

    def __init__(self, checkbox: QCheckBox) -> None:
        self._checkbox = checkbox
        self._anim: Optional[QSequentialAnimationGroup] = None
        checkbox.toggled.connect(self._on_toggled)

    def _on_toggled(self, _checked: bool) -> None:
        if (
            self._anim is not None
            and self._anim.state() == QSequentialAnimationGroup.State.Running
        ):
            self._anim.stop()
        seq = QSequentialAnimationGroup(self._checkbox)
        down = QPropertyAnimation(self._checkbox, b"windowOpacity")
        down.setDuration(60)
        down.setStartValue(1.0)
        down.setEndValue(0.7)
        down.setEasingCurve(QEasingCurve.Type.InCubic)
        up = QPropertyAnimation(self._checkbox, b"windowOpacity")
        up.setDuration(100)
        up.setStartValue(0.7)
        up.setEndValue(1.0)
        up.setEasingCurve(QEasingCurve.Type.OutBack)
        seq.addAnimation(down)
        seq.addAnimation(up)
        seq.start()
        self._anim = seq


# ---------------------------------------------------------------------------
# FadeEnabledButton — fades in when enabled, fades out when disabled
# ---------------------------------------------------------------------------


class FadeEnabledButton(QPushButton):
    """QPushButton that fades in when enabled, fades out when disabled."""

    def setEnabled(self, enabled: bool) -> None:
        old = self.isEnabled()
        super().setEnabled(enabled)
        if enabled and not old:
            fade_in(self, duration=100).start()
        elif not enabled and old:
            fade_out(self, duration=80).start()


# ---------------------------------------------------------------------------
# HoverHighlight — accent border on hover for QGroupBox / QFrame
# ---------------------------------------------------------------------------


class _HoverFilter(QObject):
    """Event filter that drives HoverHighlight."""

    def __init__(self, highlight: "HoverHighlight") -> None:
        super().__init__()
        self._highlight = highlight

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Enter:
            self._enter()
        elif event.type() == QEvent.Type.Leave:
            self._leave()
        return False

    def _enter(self) -> None:
        w = self._highlight._widget
        try:
            from .theme import get_theme_manager
            accent = get_theme_manager().palette().get("accent", "#58a6ff")
        except Exception:
            accent = "#58a6ff"
        original = self._highlight._original_style or ""
        w.setStyleSheet(
            original + f" {w.__class__.__name__} {{ border-color: {accent}; }}"
        )

    def _leave(self) -> None:
        w = self._highlight._widget
        w.setStyleSheet(self._highlight._original_style)


class HoverHighlight:
    """Add hover border highlight to a QGroupBox or QFrame."""

    def __init__(self, widget: QWidget) -> None:
        self._widget = widget
        self._original_style: str = widget.styleSheet()
        self._filter = _HoverFilter(self)
        self._widget.installEventFilter(self._filter)
