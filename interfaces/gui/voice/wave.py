from __future__ import annotations

import math
from PySide6.QtCore import QTimer, Qt, Slot
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget


class VoiceWaveWidget(QWidget):
    """Symmetrical vertical neon waveform indicating real-time audio input/output."""
    
    def __init__(self, parent: QWidget | None = None, bars: int = 40):
        super().__init__(parent)
        self.setMinimumHeight(64)
        self.bars = bars
        self.volumes = [0.0] * bars
        self.phase = 0.0
        self.state = "ready"
        
        # 60 FPS animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    @Slot(str)
    def set_state(self, state: str) -> None:
        self.state = state.lower()
        self.update()

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        vol_normalized = max(0, min(100, int(volume))) / 100.0
        # Smooth the incoming volume peak into the middle bars
        self.volumes.append(vol_normalized)
        if len(self.volumes) > self.bars:
            self.volumes.pop(0)
        self.update()

    @Slot()
    def reset_volume(self) -> None:
        self.volumes = [0.0] * self.bars
        self.update()

    def animate(self) -> None:
        self.phase += 0.08
        
        # Slower decay factor when active, faster decay when quiet
        decay = 0.95 if self.state in ("listening", "speaking") else 0.88
        self.volumes = [v * decay for v in self.volumes]
        
        # Inject ambient ripples when idle/thinking to make the waves feel 'alive'
        if self.state in ("ready", "thinking"):
            ambient = 0.05 + (math.sin(self.phase * 2.0) + 1.0) * 0.02
            self.volumes.append(ambient)
            if len(self.volumes) > self.bars:
                self.volumes.pop(0)
        
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        width = self.width()
        height = self.height()
        center_y = height / 2

        # Symmetrical Layout
        # We draw from center outward or distribute bars evenly
        bar_gap = 5
        bar_w = 4
        total_w = self.bars * (bar_w + bar_gap) - bar_gap
        start_x = (width - total_w) / 2

        # Drawing base horizontal line
        line_color = QColor(255, 255, 255, 12)
        if self.state == "listening":
            line_color = QColor(168, 85, 247, 24)
        elif self.state in ("thinking", "speaking"):
            line_color = QColor(249, 115, 22, 24)
        painter.setPen(QPen(line_color, 1))
        painter.drawLine(start_x, center_y, start_x + total_w, center_y)

        # Bar gradients based on state
        if self.state == "listening":
            # Purple / violet theme
            color_top = QColor(216, 180, 254, 15)  # purple-300
            color_mid = QColor(168, 85, 247, 210)  # purple-500
            color_bot = QColor(216, 180, 254, 15)
        elif self.state in ("thinking", "speaking"):
            # Orange theme
            color_top = QColor(253, 186, 116, 15)  # orange-300
            color_mid = QColor(249, 115, 22, 210)  # orange-500
            color_bot = QColor(253, 186, 116, 15)
        else:
            # Blue theme
            color_top = QColor(186, 230, 253, 15)  # sky-200
            color_mid = QColor(14, 165, 233, 190)  # sky-500
            color_bot = QColor(186, 230, 253, 15)

        for i in range(self.bars):
            val = self.volumes[i]
            
            # Symmetrical envelope: waves are taller in the center, tapering to sides
            dist_from_mid = abs(i - self.bars / 2) / (self.bars / 2)
            envelope = math.cos(dist_from_mid * math.pi / 2.0)
            
            # Add micro oscillation for realism
            micro_ripple = (math.sin(self.phase + i * 0.4) + 1.0) * 0.04
            h_scale = (val + micro_ripple) * envelope
            
            bar_h = max(3.0, h_scale * height * 0.9)
            x = start_x + i * (bar_w + bar_gap)
            y = center_y - bar_h / 2

            # Neon vertical gradient
            grad = QLinearGradient(x, y, x, y + bar_h)
            grad.setColorAt(0.0, color_top)
            grad.setColorAt(0.5, color_mid)
            grad.setColorAt(1.0, color_bot)

            painter.setBrush(grad)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, y, bar_w, bar_h, bar_w / 2, bar_w / 2)
