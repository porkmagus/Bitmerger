"""
Undo / Redo manager for Bitmerger GUI.

Supports memento-based undo for item list mutations, field edits, and merges.
"""

from copy import deepcopy
from typing import Callable, List, Any, Tuple, Union
from PySide6.QtCore import QObject, Signal


class Memento:
    """A snapshot of the vault state."""
    def __init__(self, items: List[Any], raw_data: dict[str, Any], description: str) -> None:
        self.items = deepcopy(items)
        self.raw_data = deepcopy(raw_data)
        self.description = description


class UndoManager(QObject):
    state_changed = Signal()

    def __init__(self, max_history: int = 50) -> None:
        super().__init__()
        self._stack: List[Memento] = []
        self._index: int = -1
        self._max_history = max_history

    def _adaptive_limit(self, item_count: int) -> int:
        """Reduce history size for large vaults to prevent memory bloat."""
        if item_count > 5000:
            return min(self._max_history, 10)
        if item_count > 1000:
            return min(self._max_history, 25)
        return self._max_history

    def can_undo(self) -> bool:
        return self._index >= 0

    def can_redo(self) -> bool:
        return self._index < len(self._stack) - 1

    def undo_description(self) -> str:
        if self.can_undo():
            return self._stack[self._index].description
        return ""

    def redo_description(self) -> str:
        if self.can_redo():
            return self._stack[self._index + 1].description
        return ""

    def push(self, items: List[Any], raw_data: dict[str, Any], description: str) -> None:
        """Save a new state snapshot."""
        # Truncate redo stack
        if self._index < len(self._stack) - 1:
            self._stack = self._stack[: self._index + 1]
        self._stack.append(Memento(items, raw_data, description))
        limit = self._adaptive_limit(len(items))
        while len(self._stack) > limit:
            self._stack.pop(0)
            self._index -= 1
            if self._index < -1:
                self._index = -1
        self._index = len(self._stack) - 1
        self.state_changed.emit()

    def undo(self) -> Union[Tuple[List[Any], dict[str, Any]], None]:
        if not self.can_undo():
            return None
        mem = self._stack[self._index]
        self._index -= 1
        self.state_changed.emit()
        return (deepcopy(mem.items), deepcopy(mem.raw_data))

    def redo(self) -> Union[Tuple[List[Any], dict[str, Any]], None]:
        if not self.can_redo():
            return None
        self._index += 1
        mem = self._stack[self._index]
        self.state_changed.emit()
        return (deepcopy(mem.items), deepcopy(mem.raw_data))

    def clear(self) -> None:
        self._stack = []
        self._index = -1
        self.state_changed.emit()
