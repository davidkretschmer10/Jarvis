from __future__ import annotations

import math

from PySide6.QtCore import QTimer, Qt, Slot
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget


class NeonWaveform(QWidget):
    def __init__(self, parent: QWidget | None = None, bars: int = 48):
        super().__init__(parent)
        self.setMinimumHeight(78)
        self.bars = bars
        self.volumes = [0.0] * bars
        self.phase = 0.0
        self.mode = "idle"

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(33)

    @Slot(str)
    def set_state(self, state: str) -> None:
        self.mode = state
        self.update()

    @Slot(int)
    def setVolume(self, volume: int) -> None:
        self.volumes.append(max(0, min(100, int(volume))) / 100.0)
        if len(self.volumes) > self.bars:
            self.volumes.pop(0)
        self.update()

    @Slot()
    def setVolumesZero(self) -> None:
        self.volumes = [0.0] * self.bars
        self.update()

    def animate(self) -> None:
        self.phase += 0.075
        if self.mode in ("idle", "thinking", "action"):
            self.volumes = self.volumes[1:] + [0.06 + (math.sin(self.phase * 1.7) + 1) * 0.025]
        else:
            self.volumes = [v * 0.86 for v in self.volumes]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        width = max(1, self.width())
        height = max(1, self.height())
        center_y = height / 2
        gap = 4
        bar_width = max(3, (width - gap * (self.bars - 1)) / self.bars)

        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        painter.drawLine(0, center_y, width, center_y)

        for i, raw in enumerate(self.volumes[-self.bars :]):
            ambient = 0.04 + (math.sin(self.phase + i * 0.35) + 1) * 0.025
            value = max(raw, ambient if self.mode != "idle" else ambient * 0.8)
            bar_height = max(4, value * height * 0.82)
            x = i * (bar_width + gap)
            y = center_y - bar_height / 2

            gradient = QLinearGradient(0, y, 0, y + bar_height)
            gradient.setColorAt(0.0, QColor(210, 238, 255, 18))
            gradient.setColorAt(0.2, QColor(108, 190, 238, 130))
            gradient.setColorAt(0.5, QColor(74, 166, 232, 190))
            gradient.setColorAt(0.8, QColor(108, 190, 238, 130))
            gradient.setColorAt(1.0, QColor(210, 238, 255, 18))

            painter.setBrush(gradient)
            painter.drawRoundedRect(x, y, bar_width, bar_height, bar_width / 2, bar_width / 2)
