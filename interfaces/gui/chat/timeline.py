from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from interfaces.gui.chat.message_bubble import MessageBubble


class ChatTimeline(QScrollArea):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName("ChatTimeline")

        self.container = QWidget()
        self.container.setObjectName("ChatTimelineContainer")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(18, 18, 18, 14)
        self.layout.setSpacing(24)
        self.layout.addStretch(1)
        self.setWidget(self.container)
        self._scroll_animation: QPropertyAnimation | None = None

    def add_message(self, role: str, text: str = "", animate: bool = True, time_str: str = "") -> MessageBubble:
        bubble = MessageBubble(role, text, animate=animate, time_str=time_str)
        self.layout.insertWidget(self.layout.count() - 1, bubble)
        self.scroll_to_bottom()
        return bubble

    def clear_messages(self) -> None:
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.scroll_to_bottom(animated=False)

    def scroll_to_bottom(self, animated: bool = True) -> None:
        QTimer.singleShot(0, lambda: self._scroll_to_bottom_now(animated))

    def _scroll_to_bottom_now(self, animated: bool) -> None:
        bar = self.verticalScrollBar()
        end = bar.maximum()
        if not animated:
            bar.setValue(end)
            return

        self._scroll_animation = QPropertyAnimation(bar, b"value", self)
        self._scroll_animation.setDuration(160)
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(end)
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_animation.start(QPropertyAnimation.DeleteWhenStopped)
