from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Slot
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QLinearGradient
from PySide6.QtWidgets import QSizePolicy, QWidget


class JarvisVoiceOrb(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = "idle"
        self.volume = 0
        self.phase = 0.0
        self.rotation = 0.0
        self.setMinimumSize(380, 380)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(33)

    @Slot(str)
    def set_state(self, state: str) -> None:
        self.state = state
        self.update()

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        self.update()

    @Slot()
    def reset_volume(self) -> None:
        self.volume = 0
        self.update()

    def animate(self) -> None:
        speed = {
            "idle": 0.02,
            "listening": 0.05,
            "thinking": 0.04,
            "speaking": 0.06,
            "action": 0.045,
        }.get(self.state, 0.02)
        
        self.phase += speed
        
        rot_speed = {
            "idle": 0.3,
            "listening": 0.5,
            "thinking": 1.8,
            "speaking": 0.6,
            "action": 1.2,
        }.get(self.state, 0.3)
        
        self.rotation = (self.rotation + rot_speed) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        side = min(self.width(), self.height())
        center_x = self.width() / 2
        center_y = self.height() / 2
        
        volume_boost = self.volume / 100.0
        pulse = (math.sin(self.phase) + 1.0) / 2.0  # value between 0.0 and 1.0

        # Base radius scale of the core sphere
        r_scale = {
            "idle": 0.22,
            "listening": 0.24,
            "thinking": 0.23,
            "speaking": 0.24 + volume_boost * 0.03,
            "action": 0.25,
        }.get(self.state, 0.22)

        radius = side * r_scale

        # Color schemes based on assistant state
        c_cyan = QColor(14, 165, 233)     # #0ea5e9
        c_indigo = QColor(79, 70, 229)    # #4f46e5
        c_purple = QColor(147, 51, 234)   # #9333ea
        c_teal = QColor(20, 184, 166)     # #14b8a6

        if self.state == "thinking":
            glow_color_1 = c_purple
            glow_color_2 = c_indigo
        elif self.state == "action":
            glow_color_1 = c_teal
            glow_color_2 = c_cyan
        elif self.state == "listening":
            glow_color_1 = QColor(56, 189, 248) # bright cyan-sky
            glow_color_2 = c_cyan
        else:
            glow_color_1 = c_cyan
            glow_color_2 = c_indigo

        # 1. LAYERED AMBIENT GLOW (Luxide Glassmorphic Aura)
        # Outer soft glow
        glow_radius_1 = side * (0.36 + pulse * 0.03 + volume_boost * 0.10)
        glow_1 = QRadialGradient(center_x, center_y, glow_radius_1, center_x - side * 0.02, center_y - side * 0.02)
        glow_1.setColorAt(0.0, QColor(glow_color_2.red(), glow_color_2.green(), glow_color_2.blue(), int(85 + pulse * 20)))
        glow_1.setColorAt(0.5, QColor(glow_color_1.red(), glow_color_1.green(), glow_color_1.blue(), int(35 + pulse * 10)))
        glow_1.setColorAt(1.0, QColor(7, 10, 18, 0))
        painter.setBrush(glow_1)
        painter.drawEllipse(center_x - glow_radius_1, center_y - glow_radius_1, glow_radius_1 * 2, glow_radius_1 * 2)

        # Inner secondary glow
        glow_radius_2 = side * (0.26 + volume_boost * 0.06)
        glow_2 = QRadialGradient(center_x, center_y, glow_radius_2, center_x - side * 0.03, center_y - side * 0.03)
        glow_2.setColorAt(0.0, QColor(glow_color_1.red(), glow_color_1.green(), glow_color_1.blue(), 130))
        glow_2.setColorAt(0.6, QColor(glow_color_2.red(), glow_color_2.green(), glow_color_2.blue(), 40))
        glow_2.setColorAt(1.0, QColor(7, 10, 18, 0))
        painter.setBrush(glow_2)
        painter.drawEllipse(center_x - glow_radius_2, center_y - glow_radius_2, glow_radius_2 * 2, glow_radius_2 * 2)

        # 2. DELICATE CONCENTRIC GLASS GEOMETRY (Extremely faint rings)
        # Outermost ring
        ring_r1 = radius * 1.30
        painter.setPen(QPen(QColor(255, 255, 255, 18), 0.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center_x - ring_r1, center_y - ring_r1, ring_r1 * 2, ring_r1 * 2)

        # Middle ring
        ring_r2 = radius * 1.14
        painter.setPen(QPen(QColor(255, 255, 255, 25), 0.8))
        painter.drawEllipse(center_x - ring_r2, center_y - ring_r2, ring_r2 * 2, ring_r2 * 2)

        # 3. 3D SPHERICAL CORE (AI Glass Core)
        core_radius = radius * 0.85
        core = QRadialGradient(
            center_x, 
            center_y, 
            core_radius, 
            center_x - core_radius * 0.28, 
            center_y - core_radius * 0.28
        )
        
        if self.state == "thinking":
            core.setColorAt(0.0, QColor(253, 244, 255, 250))
            core.setColorAt(0.20, QColor(232, 121, 249, 235))
            core.setColorAt(0.60, QColor(168, 85, 247, 210))
            core.setColorAt(1.0, QColor(88, 28, 135, 245))
        elif self.state == "action":
            core.setColorAt(0.0, QColor(240, 253, 250, 250))
            core.setColorAt(0.20, QColor(153, 246, 228, 235))
            core.setColorAt(0.60, QColor(20, 184, 166, 210))
            core.setColorAt(1.0, QColor(15, 118, 110, 245))
        else:
            core.setColorAt(0.0, QColor(240, 253, 250, 250))
            core.setColorAt(0.20, QColor(186, 230, 253, 235))
            core.setColorAt(0.60, QColor(14, 165, 233, 210))
            core.setColorAt(1.0, QColor(3, 105, 161, 245))
        
        painter.setBrush(core)
        painter.setPen(QPen(QColor(255, 255, 255, 140), 1.2))
        painter.drawEllipse(center_x - core_radius, center_y - core_radius, core_radius * 2, core_radius * 2)

        # 4. SYMMETRICAL INTERNAL CORE IDENTITY PATTERN (Futuristic Abstract "Face")
        # Central glowing horizontal capsule / visor
        visor_w = core_radius * (0.35 + pulse * 0.08)
        visor_h = core_radius * 0.08
        painter.setPen(Qt.NoPen)
        
        visor_grad = QLinearGradient(center_x - visor_w / 2, 0, center_x + visor_w / 2, 0)
        visor_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        visor_grad.setColorAt(0.2, QColor(224, 242, 254, 220))
        visor_grad.setColorAt(0.5, QColor(255, 255, 255, 255))
        visor_grad.setColorAt(0.8, QColor(224, 242, 254, 220))
        visor_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        
        painter.setBrush(visor_grad)
        painter.drawRoundedRect(
            QRectF(center_x - visor_w / 2, center_y - visor_h / 2, visor_w, visor_h), 
            visor_h / 2, 
            visor_h / 2
        )

        # Symmetrical flanking thin brackets (parentheses shapes representing consciousness)
        bracket_r = core_radius * (0.50 + pulse * 0.02)
        bracket_pen = QPen(QColor(255, 255, 255, int(110 + pulse * 60)), 1.2)
        bracket_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(bracket_pen)
        painter.setBrush(Qt.NoBrush)
        
        # Left bracket: draw arc from 145 to 215 degrees
        painter.drawArc(QRectF(center_x - bracket_r, center_y - bracket_r, bracket_r * 2, bracket_r * 2), 145 * 16, 70 * 16)
        # Right bracket: draw arc from -35 to 35 degrees
        painter.drawArc(QRectF(center_x - bracket_r, center_y - bracket_r, bracket_r * 2, bracket_r * 2), -35 * 16, 70 * 16)

        # 5. DYNAMIC FLUID VOICE WAVE (100% Mirrored Symmetrical wave loops)
        if self.state in ("listening", "speaking") or volume_boost > 0.01:
            wave_configs = [
                (2.8, 1.0, QColor(14, 165, 233, 140), 0.12),
                (-2.0, 0.7, QColor(139, 92, 246, 110), 0.18),
                (1.5, 0.5, QColor(236, 72, 153, 90), 0.24)
            ]
            
            painter.setBrush(Qt.NoBrush)
            
            for speed_factor, amp_mult, color, freq in wave_configs:
                wave_pen = QPen(color, 1.5)
                wave_pen.setCapStyle(Qt.RoundCap)
                painter.setPen(wave_pen)
                
                points_count = 50
                right_points = []
                base_amplitude = (4.0 + volume_boost * 26.0) * amp_mult
                
                # Compute right half points symmetrically
                for i in range(points_count + 1):
                    angle = -math.pi / 2 + math.pi * i / points_count
                    dist_from_center = abs(i - points_count / 2) / (points_count / 2)
                    envelope = math.cos(dist_from_center * math.pi / 2)
                    
                    wave_offset = math.sin(self.phase * speed_factor + i * freq) * envelope * base_amplitude
                    
                    r_current = core_radius + 6.0 + wave_offset
                    wx = center_x + math.cos(angle) * r_current
                    wy = center_y + math.sin(angle) * r_current
                    right_points.append(QPointF(wx, wy))
                
                # Construct path going down right side and back up left (mirrored)
                path = QPainterPath()
                path.moveTo(right_points[0])
                
                for pt in right_points[1:]:
                    path.lineTo(pt)
                    
                for pt in reversed(right_points[:-1]):
                    mirrored_x = center_x - (pt.x() - center_x)
                    path.lineTo(QPointF(mirrored_x, pt.y()))
                    
                path.closeSubpath()
                painter.drawPath(path)

