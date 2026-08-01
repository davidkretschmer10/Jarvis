from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget


class Panel(QFrame):
    def __init__(self, parent: QWidget | None = None, margins: tuple[int, int, int, int] = (24, 24, 24, 24)):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(*margins)
        self.layout.setSpacing(18)
