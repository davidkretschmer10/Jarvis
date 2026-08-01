from __future__ import annotations

import math
from PySide6.QtCore import QRectF, QTimer, Qt, Slot
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget


class JarvisFaceWidget(QWidget):
    """Living Jarvis entity: eyes suspended inside rotating orbital energy rings."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = "ready"
        self.volume = 0
        self.phase = 0.0
        self.rotation = 0.0
        self.setMinimumSize(420, 420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    @Slot(str)
    def set_state(self, state: str) -> None:
        self.state = state.lower()
        self.update()

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        self.update()

    def reset_volume(self) -> None:
        self.volume = 0
        self.update()

    def animate(self) -> None:
        speed = {
            "ready": 0.028,
            "listening": 0.075,
            "thinking": 0.06,
            "speaking": 0.09,
        }.get(self.state, 0.028)
        self.phase += speed

        rot_speed = {
            "ready": 0.45,
            "listening": 0.75,
            "thinking": 3.2,
            "speaking": 1.1,
        }.get(self.state, 0.45)
        self.rotation = (self.rotation + rot_speed) % 360
        self.update()

    def state_colors(self) -> tuple[QColor, QColor, QColor]:
        if self.state == "listening":
            return QColor("#c084fc"), QColor("#7c3aed"), QColor("#ffffff")
        if self.state in ("thinking", "speaking"):
            return QColor("#fb923c"), QColor("#f97316"), QColor("#fff7ed")
        return QColor("#38bdf8"), QColor("#0ea5e9"), QColor("#f8fbff")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        w = self.width()
        h = self.height()
        side = min(w, h)
        cx = w / 2
        cy = h / 2
        volume_boost = self.volume / 100.0
        pulse = (math.sin(self.phase) + 1.0) / 2.0
        primary, glow, eye = self.state_colors()

        aura_r = side * (0.28 + pulse * 0.035 + volume_boost * 0.06)
        aura = QRadialGradient(cx, cy, aura_r)
        aura.setColorAt(0.0, QColor(glow.red(), glow.green(), glow.blue(), 95))
        aura.setColorAt(0.55, QColor(primary.red(), primary.green(), primary.blue(), 34))
        aura.setColorAt(1.0, QColor(primary.red(), primary.green(), primary.blue(), 0))
        painter.setBrush(aura)
        painter.drawEllipse(cx - aura_r, cy - aura_r, aura_r * 2, aura_r * 2)

        base_r = side * (0.19 + pulse * 0.012 + volume_boost * 0.035)
        orbit_specs = (
            (1.00, 1.00, 0, 190, 1.7),
            (1.22, 0.86, 42, 95, 1.2),
            (0.88, 1.30, -38, 80, 1.1),
            (1.50, 1.50, 0, 48, 0.9),
        )

        painter.setBrush(Qt.NoBrush)
        for idx, (sx, sy, angle, alpha, width) in enumerate(orbit_specs):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle + self.rotation * (1 if idx % 2 == 0 else -0.7))
            pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), alpha), width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            rect = QRectF(-base_r * sx, -base_r * sy, base_r * sx * 2, base_r * sy * 2)
            if idx == 0:
                painter.drawEllipse(rect)
            else:
                painter.drawArc(rect, 15 * 16, 115 * 16)
                painter.drawArc(rect, 190 * 16, 80 * 16)
            painter.restore()

        for i in range(24):
            angle = self.phase * (0.7 + i % 3 * 0.15) + i * math.tau / 24
            radius = base_r * (1.45 + (i % 5) * 0.09 + volume_boost * 0.18)
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle * 1.13) * radius * 0.74
            alpha = 75 + (i % 4) * 32
            painter.setBrush(QColor(primary.red(), primary.green(), primary.blue(), alpha))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(x - 1.8, y - 1.8, 3.6, 3.6))

        eye_glow_r = base_r * (0.34 + pulse * 0.03 + volume_boost * 0.06)
        for offset in (-base_r * 0.42, base_r * 0.42):
            grad = QRadialGradient(cx + offset, cy - base_r * 0.03, eye_glow_r)
            grad.setColorAt(0.0, QColor(eye.red(), eye.green(), eye.blue(), 255))
            grad.setColorAt(0.35, QColor(primary.red(), primary.green(), primary.blue(), 180))
            grad.setColorAt(1.0, QColor(primary.red(), primary.green(), primary.blue(), 0))
            painter.setBrush(grad)
            painter.drawEllipse(QRectF(
                cx + offset - eye_glow_r,
                cy - base_r * 0.03 - eye_glow_r,
                eye_glow_r * 2,
                eye_glow_r * 2,
            ))

        eye_w = base_r * (0.22 + volume_boost * 0.04)
        eye_h = eye_w
        painter.setBrush(eye)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - base_r * 0.42 - eye_w / 2, cy - base_r * 0.03 - eye_h / 2, eye_w, eye_h))
        painter.drawEllipse(QRectF(cx + base_r * 0.42 - eye_w / 2, cy - base_r * 0.03 - eye_h / 2, eye_w, eye_h))
