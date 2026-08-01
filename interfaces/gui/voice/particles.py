from __future__ import annotations

import math
import random
from PySide6.QtCore import QPointF, QTimer, Qt, Slot
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Particle:
    """Represents a single digital particle orbiting the Jarvis core."""
    
    def __init__(self, screen_w: int, screen_h: int):
        self.angle = random.uniform(0, 2 * math.pi)
        self.base_radius = random.uniform(160, 280)
        self.current_radius = self.base_radius
        self.angular_speed = random.uniform(0.005, 0.02) * (1 if random.random() > 0.3 else -1)
        self.size = random.uniform(1.5, 3.5)
        self.noise_phase = random.uniform(0, 100)
        self.opacity = random.randint(80, 220)

    def update(self, state: str, volume: int, phase: float):
        # Base speed multipliers per state
        speed_mult = {
            "ready": 0.8,
            "listening": 1.6,
            "thinking": 3.0,  # Fast particle stream when thinking
            "speaking": 1.8,
        }.get(state, 0.8)

        # Increment angle
        self.angle += self.angular_speed * speed_mult
        
        # Slower floating wave modulation
        wave = math.sin(self.angle * 2.0 + self.noise_phase + phase * 0.5) * 12.0
        
        # Audio volume expands orbit
        vol_boost = (volume / 100.0) * 45.0 if state in ("listening", "speaking") else 0.0
        
        self.current_radius = self.base_radius + wave + vol_boost


class ParticleSystem(QWidget):
    """Overlay particle field that renders orbiting data streams around the face."""
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  # Click-through
        self.state = "ready"
        self.volume = 0
        self.phase = 0.0

        # Pre-generate 80 particles
        self.particles = [Particle(800, 600) for _ in range(85)]

        # 60 FPS animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_particles)
        self.timer.start(16)

    @Slot(str)
    def set_state(self, state: str) -> None:
        self.state = state.lower()

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        self.volume = volume

    def update_particles(self):
        self.phase += 0.05
        for p in self.particles:
            p.update(self.state, self.volume, self.phase)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        cx = self.width() / 2
        cy = self.height() / 2

        # Primary particle color theme
        if self.state == "thinking":
            base_color = QColor("#f97316")  # Orange particles
        elif self.state == "listening":
            base_color = QColor("#c084fc")  # Purple particles
        else:
            base_color = QColor("#38bdf8")  # Cyan particles

        for p in self.particles:
            # Symmetrical orbiting positions
            x = cx + math.cos(p.angle) * p.current_radius
            y = cy + math.sin(p.angle) * p.current_radius

            # Skip drawing if outside widget bounds
            if x < 0 or x > self.width() or y < 0 or y > self.height():
                continue

            # Draw particle with custom opacity
            color = QColor(base_color.red(), base_color.green(), base_color.blue(), p.opacity)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), p.size / 2, p.size / 2)
            
            # Subtle micro trails or connections for thinking state (digital web feel)
            if self.state == "thinking" and random.random() > 0.96:
                pen_color = QColor(base_color.red(), base_color.green(), base_color.blue(), 35)
                painter.setPen(QPen(pen_color, 0.8))
                painter.drawLine(cx, cy, x, y)
                painter.setPen(Qt.NoPen)
