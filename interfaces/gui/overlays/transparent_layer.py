from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class TransparentLayer(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._debug_tint = False

    def set_debug_tint(self, enabled: bool) -> None:
        self._debug_tint = enabled
        self.update()

    def paintEvent(self, event):
        if not self._debug_tint:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(14, 165, 233, 18))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 18, 18)
