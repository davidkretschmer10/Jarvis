from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from interfaces.gui.sidebar.chat_list import ChatListPanel


class SlidingChatPanel(QFrame):
    """The sliding drawer panel holding the Chat list search, items, and control buttons."""
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SlidingChatPanel")
        
        # Starts closed; the blue edge handle slides it in from the left.
        self.setFixedWidth(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(0)

        self.chat_list = ChatListPanel(self)
        layout.addWidget(self.chat_list)

        self.setStyleSheet(
            """
            QFrame#SlidingChatPanel {
                background: rgba(3, 8, 18, 0.94);
                border: 1px solid rgba(14, 165, 233, 0.26);
                border-radius: 8px;
            }
            """
        )
