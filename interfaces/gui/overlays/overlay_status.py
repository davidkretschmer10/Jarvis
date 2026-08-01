from __future__ import annotations

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QWidget


class OverlayStatus(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("OverlayStatus")
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(8)

        self.dot = QLabel("")
        self.dot.setObjectName("OverlayStatusDot")
        self.dot.setFixedSize(8, 8)

        self.label = QLabel("Připraven")
        self.label.setObjectName("OverlayStatusText")

        layout.addWidget(self.dot)
        layout.addWidget(self.label)

        self.setStyleSheet(
            """
            QFrame#OverlayStatus {
                background: rgba(3, 9, 20, 0.88);
                border: 1px solid rgba(125, 225, 255, 0.42);
                border-radius: 16px;
            }
            QLabel#OverlayStatusDot {
                background: #38bdf8;
                border-radius: 4px;
            }
            QLabel#OverlayStatusText {
                color: #e8f7ff;
                font-size: 13px;
                font-weight: 700;
            }
            """
        )

    @Slot(str)
    def set_message(self, text: str) -> None:
        self.label.setText(text)
        self.adjustSize()

    def show_message(self, text: str, timeout_ms: int = 2400) -> None:
        self.set_message(text)
        self.show()
        if timeout_ms > 0:
            self.hide_timer.start(timeout_ms)
