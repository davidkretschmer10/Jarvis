from __future__ import annotations

from datetime import datetime
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from interfaces.gui.widgets.avatar import JarvisAvatar


class MessageBubble(QFrame):
    content_changed = Signal()

    def __init__(
        self,
        role: str,
        text: str = "",
        parent: QWidget | None = None,
        animate: bool = True,
        time_str: str = "",
    ):
        super().__init__(parent)
        self.role = role
        self._base_text = text
        self._pending_text = ""
        self._thinking = False
        self._dot_count = 0
        
        # Timing setup
        self._thinking_timer = QTimer(self)
        self._thinking_timer.timeout.connect(self._tick_thinking)
        self._typing_timer = QTimer(self)
        self._typing_timer.timeout.connect(self._flush_typing)

        if not time_str:
            time_str = datetime.now().strftime("%H:%M")
        self.time_str = time_str

        self.setObjectName("MessageBubble")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(12)

        self.card = QFrame()
        self.card.setObjectName("BubbleCard")
        # Align bubble widths
        self.card.setMaximumWidth(620 if role != "user" else 520)
        
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        text_spacing = 6 if role != "system" else 0
        card_layout.setSpacing(text_spacing)

        # Bubble main text
        self.text_label = QLabel()
        self.text_label.setObjectName("BubbleText")
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(Qt.PlainText)
        card_layout.addWidget(self.text_label)

        # Time & status indicators inside the bubble
        if role != "system":
            self.status_row = QHBoxLayout()
            self.status_row.setContentsMargins(0, 2, 0, 0)
            self.status_row.setSpacing(4)

            self.time_label = QLabel(self.time_str)
            self.time_label.setObjectName("BubbleTime")

            self.status_row.addStretch(1)
            self.status_row.addWidget(self.time_label)

            if role == "user":
                self.ticks_label = QLabel("✓✓")
                self.ticks_label.setObjectName("BubbleTicks")
                self.status_row.addWidget(self.ticks_label)

            card_layout.addLayout(self.status_row)

        self.avatar: JarvisAvatar | None = None

        # Alignments based on ChatGPT style
        if role == "user":
            row.addStretch(1)
            row.addWidget(self.card, 0)
        elif role == "system":
            row.addStretch(1)
            row.addWidget(self.card, 0)
            row.addStretch(1)
        else:  # jarvis
            self.avatar = JarvisAvatar(size=36)
            row.addWidget(self.avatar, 0, Qt.AlignTop)
            row.addWidget(self.card, 0)
            row.addStretch(1)

        self.apply_role_style()
        self.set_text(text)

        if animate:
            self.fade_in()

    def apply_role_style(self) -> None:
        if self.role == "user":
            card = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d4ed8, stop:1 #1e40af)"  # Rich blue gradient
            text = "#ffffff"
            time_color = "rgba(255, 255, 255, 0.6)"
            ticks_color = "#38bdf8"  # bright blue checkmarks
            radius = "16px 16px 4px 16px"  # WhatsApp-style user corner
            border = "1px solid rgba(96, 165, 250, 0.18)"
        elif self.role == "system":
            card = "rgba(255, 255, 255, 0.03)"
            text = "#64748b"
            time_color = "transparent"
            ticks_color = "transparent"
            radius = "8px"
            border = "1px solid rgba(255, 255, 255, 0.04)"
        else:  # jarvis
            card = "rgba(17, 27, 43, 0.86)"  # Dark gray-blue
            text = "#e2e8f0"
            time_color = "#475569"
            ticks_color = "transparent"
            radius = "16px 16px 16px 4px"  # Jarvis corner
            border = "1px solid rgba(148, 163, 184, 0.14)"

        self.card.setStyleSheet(
            f"""
            QFrame#BubbleCard {{
                background: {card};
                border: {border};
                border-radius: {radius};
            }}
            QLabel#BubbleText {{
                color: {text};
                font-size: 14px;
                line-height: 1.4;
            }}
            QLabel#BubbleTime {{
                color: {time_color};
                font-size: 10px;
                font-weight: 500;
            }}
            QLabel#BubbleTicks {{
                color: {ticks_color};
                font-size: 11px;
                font-weight: bold;
            }}
            """
        )

    def fade_in(self) -> None:
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(150)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start(QPropertyAnimation.DeleteWhenStopped)

    def set_text(self, text: str) -> None:
        self._base_text = text
        self._pending_text = ""
        if not self._thinking:
            self.text_label.setText(text)

    def append_text(self, chunk: str) -> None:
        if self._thinking:
            self.stop_thinking()
            self._base_text = ""
        self._pending_text += chunk
        if not self._typing_timer.isActive():
            self._typing_timer.start(12)

    def finish_typing(self) -> None:
        if self._pending_text:
            self._base_text += self._pending_text
            self._pending_text = ""
            self.text_label.setText(self._base_text)
        self._typing_timer.stop()

    def _flush_typing(self) -> None:
        if not self._pending_text:
            self._typing_timer.stop()
            return
        chunk_size = 3 if len(self._pending_text) > 16 else 1
        self._base_text += self._pending_text[:chunk_size]
        self._pending_text = self._pending_text[chunk_size:]
        self.text_label.setText(self._base_text)
        self.content_changed.emit()

    def start_thinking(self) -> None:
        self._thinking = True
        self._dot_count = 0
        self._base_text = ""
        if self.avatar:
            self.avatar.set_state("thinking")
        self._tick_thinking()
        self._thinking_timer.start(360)

    def stop_thinking(self) -> None:
        self._thinking = False
        self._thinking_timer.stop()
        if self.avatar:
            self.avatar.set_state("ready")
        self.text_label.setText(self._base_text)

    def start_speaking(self) -> None:
        if self.avatar:
            self.avatar.set_state("speaking")

    def stop_speaking(self) -> None:
        if self.avatar:
            self.avatar.set_state("ready")

    def _tick_thinking(self) -> None:
        self._dot_count = (self._dot_count + 1) % 4
        self.text_label.setText("Jarvis přemýšlí" + "." * self._dot_count)
