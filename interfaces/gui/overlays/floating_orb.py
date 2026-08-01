from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from interfaces.gui.overlays.overlay_animation_manager import OverlayVisualState, OVERLAY_STATES


class FloatingOrb(QWidget):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(112, 112)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.state = OVERLAY_STATES["IDLE"]
        self.volume = 0
        self.phase = 0.0
        self.rotation = 0.0
        self.hovered = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(33)

    @Slot(str)
    def set_state(self, state: str) -> None:
        self.state = OVERLAY_STATES.get(state, OVERLAY_STATES["IDLE"])
        self.update()

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        self.update()

    @Slot()
    def reset_volume(self) -> None:
        self.volume = 0
        self.update()

    def set_visual_state(self, state: OverlayVisualState) -> None:
        self.state = state
        self.update()

    def animate(self) -> None:
        self.phase += self.state.pulse_speed
        self.rotation = (self.rotation + self.state.orbit_speed) % 360
        self.update()

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        side = min(self.width(), self.height())
        center = side / 2
        volume_boost = self.volume / 100.0
        hover_boost = 0.16 if self.hovered else 0.0
        pulse = (math.sin(self.phase) + 1) / 2
        glow_radius = side * (0.45 + self.state.glow_strength * 0.20 + volume_boost * 0.10 + hover_boost * 0.10)

        glow = QRadialGradient(center, center, glow_radius)
        glow.setColorAt(0.0, QColor(125, 225, 255, 210))
        glow.setColorAt(0.28, QColor(56, 189, 248, 108))
        glow.setColorAt(0.72, QColor(14, 165, 233, 42))
        glow.setColorAt(1.0, QColor(5, 9, 20, 0))
        painter.setBrush(glow)
        painter.drawEllipse(center - glow_radius, center - glow_radius, glow_radius * 2, glow_radius * 2)

        core_radius = side * (0.24 + pulse * 0.018 + volume_boost * 0.045 + hover_boost * 0.02)
        core = QRadialGradient(center - core_radius * 0.2, center - core_radius * 0.25, core_radius * 1.2)
        core.setColorAt(0.0, QColor(240, 253, 255, 245))
        core.setColorAt(0.22, QColor(125, 225, 255, 235))
        core.setColorAt(0.62, QColor(14, 165, 233, 225))
        core.setColorAt(1.0, QColor(8, 47, 73, 245))
        painter.setBrush(core)
        painter.setPen(QPen(QColor(191, 247, 255, 210), 1.4))
        painter.drawEllipse(center - core_radius, center - core_radius, core_radius * 2, core_radius * 2)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(165, 243, 252, 160), 1.6))
        ring_radius = core_radius + side * 0.10
        painter.drawArc(
            QRectF(center - ring_radius, center - ring_radius, ring_radius * 2, ring_radius * 2),
            int(self.rotation * 16),
            int(105 * 16),
        )

        if self.state.name in ("LISTENING", "SPEAKING"):
            painter.setPen(QPen(QColor(224, 252, 255, 150), 1.0))
            for index in range(20):
                angle = math.pi * 2 * index / 20 + self.phase
                length = side * (0.035 + volume_boost * 0.085 + pulse * 0.018)
                start = core_radius + side * 0.17
                x1 = center + math.cos(angle) * start
                y1 = center + math.sin(angle) * start
                x2 = center + math.cos(angle) * (start + length)
                y2 = center + math.sin(angle) * (start + length)
                painter.drawLine(x1, y1, x2, y2)
