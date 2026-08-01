from __future__ import annotations

import math
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from interfaces.gui.voice.face import JarvisFaceWidget
from interfaces.gui.voice.particles import ParticleSystem
from interfaces.gui.voice.wave import VoiceWaveWidget
from interfaces.gui.voice.state_manager import VoiceStateManager


class FaceContainer(QWidget):
    """Container packing JarvisFaceWidget and ParticleSystem into the same coordinates."""
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(560, 560)
        
        self.face = JarvisFaceWidget(self)
        self.particles = ParticleSystem(self)

    def resizeEvent(self, event):
        self.face.setGeometry(self.rect())
        self.particles.setGeometry(self.rect())


class VoiceScene(QWidget):
    """The main fullscreen Voice Scene containing all core visual elements, centered globally."""

    def __init__(self, controller, event_bus, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.event_bus = event_bus
        self.phase = 0.0
        self.parallax_x = 0.0

        self.bg_timer = QTimer(self)
        self.bg_timer.timeout.connect(self.animate_background)
        self.bg_timer.start(16)

        # Vertical layout spanning full screen
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 42)
        main_layout.setSpacing(6)

        # 1. Main Space (Face & Particles)
        main_layout.addStretch(1)
        
        center_row = QHBoxLayout()
        self.face_container = FaceContainer()
        center_row.addStretch()
        center_row.addWidget(self.face_container)
        center_row.addStretch()
        main_layout.addLayout(center_row)

        self.state_label = QLabel("")
        self.state_label.hide()

        # 3. Waveform row
        wave_row = QHBoxLayout()
        self.waveform = VoiceWaveWidget(bars=42)
        self.waveform.setFixedWidth(460)
        wave_row.addStretch()
        wave_row.addWidget(self.waveform)
        wave_row.addStretch()
        main_layout.addLayout(wave_row)
        
        main_layout.addStretch(1)

        # Initialize State Manager
        self.state_manager = VoiceStateManager(
            self.controller,
            self.face_container.face,
            self.face_container.particles,
            self.waveform,
            self.state_label,
            self
        )

    def animate_background(self):
        self.phase += 0.012
        self.parallax_x = math.sin(self.phase * 0.7) * 18.0
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        # Automatically launch backend voice mode loop
        self.controller.start_voice_chat()

    def hideEvent(self, event):
        super().hideEvent(event)
        # Terminate loop upon leaving tab
        self.controller.stop_voice_chat()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Render digital lab deep dark blue radial space
        center_x = self.width() / 2 + self.parallax_x
        center_y = self.height() / 2 + math.cos(self.phase * 0.5) * 10.0
        grad = QRadialGradient(center_x, center_y, max(self.width(), self.height()) / 1.35)
        grad.setColorAt(0.0, QColor("#0c162b"))
        grad.setColorAt(0.6, QColor("#040813"))
        grad.setColorAt(1.0, QColor("#010204"))

        painter.setBrush(grad)
        painter.drawRect(self.rect())

        w = self.width()
        h = self.height()
        painter.setPen(Qt.NoPen)

        for i in range(130):
            depth = 0.35 + (i % 9) / 9.0
            x = ((i * 97) + self.parallax_x * depth * 2.0) % max(1, w)
            y = ((i * 53) + math.sin(self.phase + i) * 12.0 * depth) % max(1, h)
            alpha = 30 + (i * 11) % 110
            painter.setBrush(QColor(14, 165, 233, alpha))
            size = 1 + (i % 3)
            painter.drawEllipse(x, y, size, size)

        wave_pen = QPen(QColor(14, 165, 233, 90), 1.0)
        wave_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(wave_pen)
        baseline = h * 0.66
        for lane in range(5):
            points = []
            offset = lane * 18
            amplitude = 12 + lane * 4
            for step in range(0, w + 20, 20):
                x = step
                y = baseline + offset + math.sin((step / 70.0) + lane + self.phase * 4.0) * amplitude
                points.append((x, y))
            for a, b in zip(points, points[1:]):
                painter.drawLine(a[0], a[1], b[0], b[1])
