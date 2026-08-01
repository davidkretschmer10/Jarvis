from __future__ import annotations

import math
from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QTimer, Qt, Slot, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget


def blend_color(c1: QColor, c2: QColor, factor: float) -> QColor:
    r = int(c1.red() + (c2.red() - c1.red()) * factor)
    g = int(c1.green() + (c2.green() - c1.green()) * factor)
    b = int(c1.blue() + (c2.blue() - c1.blue()) * factor)
    a = int(c1.alpha() + (c2.alpha() - c1.alpha()) * factor)
    return QColor(r, g, b, a)


class ComposerIconButton(QPushButton):
    def __init__(self, icon_type: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.icon_type = icon_type  # 'send', 'mic', or 'attach'
        self.setFixedSize(36, 36)
        self.setCursor(Qt.PointingHandCursor)
        self.hovered = False
        self.listening = False
        self.volume = 0

        self.pulse_phase = 0.0
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.update_pulse)

        # Hover animation property
        self._hover_alpha = 0.0
        self.hover_anim = QPropertyAnimation(self, b"hover_alpha")
        self.hover_anim.setDuration(150)
        self.hover_anim.setEasingCurve(QEasingCurve.OutCubic)

    @Property(float)
    def hover_alpha(self) -> float:
        return self._hover_alpha

    @hover_alpha.setter
    def hover_alpha(self, val: float) -> None:
        self._hover_alpha = val
        self.update()

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        if self.icon_type == 'mic':
            self.volume = volume
            self.update()

    @Slot()
    def reset_volume(self) -> None:
        if self.icon_type == 'mic':
            self.volume = 0
            self.update()

    def enterEvent(self, event):
        self.hovered = True
        self.hover_anim.stop()
        self.hover_anim.setStartValue(self._hover_alpha)
        self.hover_anim.setEndValue(1.0)
        self.hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.hover_anim.stop()
        self.hover_anim.setStartValue(self._hover_alpha)
        self.hover_anim.setEndValue(0.0)
        self.hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.icon_type == 'mic' and event.button() == Qt.LeftButton:
            self.listening = True
            self.pulse_timer.start(33)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.icon_type == 'mic' and event.button() == Qt.LeftButton:
            self.listening = False
            self.pulse_timer.stop()
            self.update()
        super().mouseReleaseEvent(event)

    def update_pulse(self):
        self.pulse_phase += 0.15
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2

        if self.icon_type == 'send':
            # Solid blue circle background (standard for send icon)
            base_blue = QColor("#1d4ed8")  # royal blue
            target_blue = QColor("#2563eb") # lighter blue
            bg_color = blend_color(base_blue, target_blue, self._hover_alpha)
            
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg_color)
            painter.drawEllipse(cx - 15, cy - 15, 30, 30)
            icon_color = QColor("#ffffff")
        elif self.icon_type == 'mic' and self.listening:
            # Active pulsing mic background
            volume_factor = self.volume / 100.0
            pulse_mult = (math.sin(self.pulse_phase) + 1.0) / 2.0
            glow_r = 15.0 + pulse_mult * 5.0 + volume_factor * 8.0
            
            glow = QRadialGradient(cx, cy, glow_r)
            glow.setColorAt(0.0, QColor(14, 165, 233, 140))
            glow.setColorAt(0.6, QColor(14, 165, 233, 40))
            glow.setColorAt(1.0, QColor(14, 165, 233, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))

            painter.setBrush(QColor(14, 165, 233, 220))
            painter.drawEllipse(cx - 14, cy - 14, 28, 28)
            icon_color = QColor("#ffffff")
        else:
            # Idle/Hover transparent background for attach & mic
            base_bg = QColor(255, 255, 255, 0)
            target_bg = QColor(255, 255, 255, 14)
            bg_color = blend_color(base_bg, target_bg, self._hover_alpha)

            base_stroke = QColor("#64748b")
            target_stroke = QColor("#e2e8f0")
            icon_color = blend_color(base_stroke, target_stroke, self._hover_alpha)

            painter.setPen(Qt.NoPen)
            painter.setBrush(bg_color)
            painter.drawEllipse(cx - 14, cy - 14, 28, 28)

        # Draw actual vector icon
        pen = QPen(icon_color, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.save()
        painter.translate(cx - 10, cy - 10)  # Center 20x20 canvas

        if self.icon_type == 'send':
            # Paper airplane vector
            path = QPainterPath()
            path.moveTo(17, 3)
            path.lineTo(3, 9)
            path.lineTo(8, 12)
            path.lineTo(17, 3)
            painter.drawPath(path)
            
            path2 = QPainterPath()
            path2.moveTo(8, 12)
            path2.lineTo(11, 17)
            path2.lineTo(17, 3)
            painter.drawPath(path2)
        elif self.icon_type == 'mic':
            # Mic shape
            pill_rect = QRectF(7, 2, 6, 9)
            painter.drawRoundedRect(pill_rect, 3, 3)

            stand_path = QPainterPath()
            stand_path.moveTo(4, 7)
            stand_path.quadTo(4, 13, 10, 13)
            stand_path.quadTo(16, 13, 16, 7)
            painter.drawPath(stand_path)

            painter.drawLine(10, 13, 10, 17)
            painter.drawLine(6, 17, 14, 17)
        elif self.icon_type == 'attach':
            # Paperclip shape
            path = QPainterPath()
            path.moveTo(14, 4)
            path.lineTo(7, 11)
            # Outer loop bottom
            path.arcTo(QRectF(5, 10, 4, 4), 180, 180)
            path.lineTo(15, 4)
            # Outer loop top
            path.arcTo(QRectF(11, 2, 4, 4), 0, 180)
            path.lineTo(8, 9)
            # Inner loop bottom
            path.arcTo(QRectF(7, 8, 3, 3), 180, 180)
            path.lineTo(12, 5)
            painter.drawPath(path)

        painter.restore()


class CustomLineEdit(QLineEdit):
    focus_in = Signal()
    focus_out = Signal()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focus_in.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focus_out.emit()


class ModernInputBar(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ModernInputBar")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 10)
        root.setSpacing(0)

        # The Capsule Composer Frame
        self.composer_frame = QFrame()
        self.composer_frame.setObjectName("ComposerFrame")
        
        composer_layout = QHBoxLayout(self.composer_frame)
        composer_layout.setContentsMargins(18, 8, 8, 8)
        composer_layout.setSpacing(8)

        self.input = CustomLineEdit()
        self.input.setObjectName("ComposerInput")
        self.input.setPlaceholderText("Napiš zprávu...")

        # Paperclip icon on right
        self.attach_button = ComposerIconButton("attach")
        self.attach_button.setObjectName("ComposerAttachButton")
        self.attach_button.setToolTip("Připnout soubor")
        
        # Mic icon on right
        self.voice_button = ComposerIconButton("mic")
        self.voice_button.setObjectName("ComposerMicButton")
        self.voice_button.setToolTip("Podrž pro mluvení")

        # Send icon (paper airplane) on right
        self.send_button = ComposerIconButton("send")
        self.send_button.setObjectName("ComposerSendButton")
        self.send_button.setToolTip("Odeslat")

        composer_layout.addWidget(self.input, 1)
        composer_layout.addWidget(self.attach_button)
        composer_layout.addWidget(self.voice_button)
        composer_layout.addWidget(self.send_button)

        root.addWidget(self.composer_frame)

        # Off-screen controls to keep signals and state working without showing them in the UI
        self.send_voice_button = QPushButton()
        self.wake_checkbox = QCheckBox()
        self.voice_read_checkbox = QCheckBox()

        self.input.focus_in.connect(self.on_focus_in)
        self.input.focus_out.connect(self.on_focus_out)

        # Attach file handler mock hook
        self.attach_button.clicked.connect(self.handle_attach_file)

        # Apply soft shadow to the capsule
        from interfaces.gui.widgets.effects import apply_soft_shadow
        apply_soft_shadow(self.composer_frame, blur=24, y_offset=6, strength=65)

        self.refresh_composer_style(focused=False)

    def handle_attach_file(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        file_path, _ = QFileDialog.getOpenFileName(self, "Vybrat soubor pro nahrání", "", "All Files (*)")
        if file_path:
            import os
            filename = os.path.basename(file_path)
            # Mock attach file by placing filename in text box or showing popup
            self.input.setText(f"[Soubor: {filename}] " + self.input.text())
            self.input.setFocus()

    def on_focus_in(self):
        self.refresh_composer_style(focused=True)

    def on_focus_out(self):
        self.refresh_composer_style(focused=False)

    def refresh_composer_style(self, focused: bool):
        border = "1px solid rgba(14, 165, 233, 0.42)" if focused else "1px solid rgba(148, 163, 184, 0.15)"
        bg = "rgba(6, 13, 27, 0.86)" if focused else "rgba(6, 13, 27, 0.72)"
        
        self.setStyleSheet(
            f"""
            QFrame#ModernInputBar {{
                background: transparent;
                border: none;
            }}
            QFrame#ComposerFrame {{
                background: {bg};
                border: {border};
                border-radius: 16px;
            }}
            QLineEdit#ComposerInput {{
                background: transparent;
                border: none;
                color: #f8fafc;
                font-size: 14px;
                padding: 12px 4px;
                selection-background-color: #0ea5e9;
            }}
            QLineEdit#ComposerInput:focus {{
                background: transparent;
                border: none;
            }}
            """
        )
