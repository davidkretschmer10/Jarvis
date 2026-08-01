from __future__ import annotations

import math
from PySide6.QtCore import QTimer, Qt, Slot
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import QWidget


class JarvisLogoWidget(QWidget):
    """Small static Jarvis logo widget for the sidebar title."""
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(32, 32)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw outer blue ring
        pen = QPen(QColor("#0ea5e9"), 1.8)
        painter.setPen(pen)
        painter.setBrush(QColor("#041026"))
        painter.drawEllipse(2, 2, 28, 28)

        # Draw two glowing eyes
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(9, 12, 4.5, 4.5)
        painter.drawEllipse(18, 12, 4.5, 4.5)


class JarvisAvatar(QWidget):
    """State-aware and animated Jarvis avatar widget used beside messages and in Voice modes."""
    
    def __init__(self, size: int = 42, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.state = "ready"  # ready, listening, thinking, speaking
        self.volume = 0
        self.phase = 0.0
        self.rotation = 0.0

        # Animation timer (30 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(33)

    @Slot(str)
    def set_state(self, state: str) -> None:
        self.state = state.lower()
        self.update()

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        self.update()

    def animate(self) -> None:
        if self.state == "listening":
            self.phase += 0.15
            self.update()
        elif self.state == "thinking":
            self.rotation = (self.rotation + 6.0) % 360
            self.update()
        elif self.state == "speaking":
            self.phase += 0.2
            self.update()
        else:
            # Idle/ready breathing micro-animation
            self.phase += 0.05
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        r = min(w, h) / 2 - 2

        # Pulse calculations
        pulse = (math.sin(self.phase) + 1.0) / 2.0  # 0.0 to 1.0

        if self.state == "thinking":
            # Orange theme
            bg_color = QColor("#1e1107")
            ring_color = QColor("#f97316")
            eye_color = QColor("#ffedd5")
        elif self.state == "listening":
            # Bright cyan/sky pulsing theme
            bg_color = QColor("#041220")
            ring_color = QColor("#38bdf8")
            eye_color = QColor("#ffffff")
        elif self.state == "speaking":
            # Speaking blue pulsing theme
            bg_color = QColor("#041026")
            ring_color = QColor("#0ea5e9")
            eye_color = QColor("#ffffff")
        else:
            # Ready state (default blue)
            bg_color = QColor("#041026")
            ring_color = QColor("#0ea5e9")
            eye_color = QColor("#ffffff")

        # 1. Pulsing Outer Glow (for listening, speaking, or ready micro-breath)
        if self.state == "listening":
            glow_r = r + 2.0 + pulse * 4.0
            glow_color = QColor(ring_color.red(), ring_color.green(), ring_color.blue(), int(60 - pulse * 40))
            painter.setBrush(glow_color)
            painter.drawEllipse(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2)
        elif self.state == "speaking":
            vol_factor = self.volume / 100.0
            glow_r = r + 1.0 + (vol_factor * 5.0) + (pulse * 2.0)
            glow_color = QColor(ring_color.red(), ring_color.green(), ring_color.blue(), int(80 - pulse * 30))
            painter.setBrush(glow_color)
            painter.drawEllipse(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2)
        else:
            # Idle gentle breath glow
            glow_r = r + pulse * 1.5
            glow_color = QColor(ring_color.red(), ring_color.green(), ring_color.blue(), int(30 - pulse * 15))
            painter.setBrush(glow_color)
            painter.drawEllipse(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2)

        # 2. Main Circle background
        painter.setBrush(bg_color)
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # 3. Outer Ring
        if self.state == "thinking":
            # Rotating segmented ring for thinking
            pen = QPen(ring_color, 1.8)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(self.rotation)
            # Draw arcs for segment spinner look
            painter.drawArc(-r, -r, r * 2, r * 2, 0 * 16, 90 * 16)
            painter.drawArc(-r, -r, r * 2, r * 2, 180 * 16, 90 * 16)
            painter.restore()
        else:
            # Solid outer ring
            pen = QPen(ring_color, 1.6)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # 4. Glowing eyes inside
        painter.setPen(Qt.NoPen)
        painter.setBrush(eye_color)
        
        # Eye width scale based on pulse for listening (eyes can widen slightly)
        eye_scale = 1.0
        if self.state == "listening":
            eye_scale = 1.0 + pulse * 0.15

        eye_w = 4.2 * eye_scale
        eye_h = 4.2 * eye_scale
        
        # Calculate coordinates dynamically to scale with widget width/height
        scale_x = w / 42.0
        scale_y = h / 42.0
        
        lx = cx - 9.0 * scale_x - eye_w / 2
        rx = cx + 9.0 * scale_x - eye_w / 2
        ey = cy - 2.0 * scale_y - eye_h / 2
        
        painter.drawEllipse(lx, ey, eye_w, eye_h)
        painter.drawEllipse(rx, ey, eye_w, eye_h)
