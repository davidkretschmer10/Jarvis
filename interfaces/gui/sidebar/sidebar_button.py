from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class SidebarIcon(QWidget):
    def __init__(self, key: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self.stroke_color = QColor("#8e9bae")
        self.bg_color = QColor(255, 255, 255, 0)
        self.setFixedSize(28, 28)

    def set_colors(self, stroke: QColor, bg: QColor) -> None:
        self.stroke_color = stroke
        self.bg_color = bg
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw icon background if any
        if self.bg_color.alpha() > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.bg_color)
            painter.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)

        # Center inside 28x28 (canvas is 20x20, translate to (4,4))
        painter.save()
        painter.translate(4, 4)

        pen = QPen(self.stroke_color, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if self.key == "chat":
            path = QPainterPath()
            path.addRoundedRect(QRectF(2, 3, 16, 12), 3, 3)
            path.moveTo(5, 15)
            path.lineTo(2, 18)
            path.lineTo(2, 15)
            painter.drawPath(path)

        elif self.key == "voice":
            pill_rect = QRectF(7, 2, 6, 9)
            painter.drawRoundedRect(pill_rect, 3, 3)
            
            stand_path = QPainterPath()
            stand_path.moveTo(3, 7)
            stand_path.quadTo(3, 13, 10, 13)
            stand_path.quadTo(17, 13, 17, 7)
            painter.drawPath(stand_path)
            
            painter.drawLine(10, 13, 10, 17)
            painter.drawLine(6, 17, 14, 17)

        elif self.key == "settings":
            # Sliders (Settings Icon)
            painter.drawLine(2, 5, 18, 5)
            painter.drawLine(2, 10, 18, 10)
            painter.drawLine(2, 15, 18, 15)
            
            painter.save()
            painter.setBrush(self.stroke_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(5, 3.5, 3, 3))
            painter.drawEllipse(QRectF(13, 8.5, 3, 3))
            painter.drawEllipse(QRectF(8, 13.5, 3, 3))
            painter.restore()

        elif self.key == "models":
            # Sparkles / Modify Icon
            s1 = QPainterPath()
            s1.moveTo(10, 2)
            s1.quadTo(10, 10, 18, 10)
            s1.quadTo(10, 10, 10, 18)
            s1.quadTo(10, 10, 2, 10)
            s1.quadTo(10, 10, 10, 2)
            s1.closeSubpath()
            painter.drawPath(s1)
            
            s2 = QPainterPath()
            s2.moveTo(15, 3)
            s2.quadTo(15, 5, 17, 5)
            s2.quadTo(15, 5, 15, 7)
            s2.quadTo(15, 5, 13, 5)
            s2.quadTo(15, 5, 15, 3)
            s2.closeSubpath()
            painter.drawPath(s2)

        elif self.key == "memory":
            # Memory chip
            body_rect = QRectF(6, 6, 8, 8)
            painter.drawRoundedRect(body_rect, 2, 2)
            
            painter.drawLine(8, 3, 8, 6)
            painter.drawLine(12, 3, 12, 6)
            painter.drawLine(8, 14, 8, 17)
            painter.drawLine(12, 14, 12, 17)
            
            painter.drawLine(3, 8, 6, 8)
            painter.drawLine(3, 12, 6, 12)
            painter.drawLine(14, 8, 17, 8)
            painter.drawLine(14, 12, 17, 12)

        elif self.key == "tools":
            # Terminal prompt / tools shape
            path = QPainterPath()
            path.moveTo(4, 5)
            path.lineTo(9, 10)
            path.lineTo(4, 15)
            painter.drawPath(path)
            
            painter.drawLine(10, 15, 16, 15)

        else:
            painter.drawEllipse(8, 8, 4, 4)

        painter.restore()


def blend_color(c1: QColor, c2: QColor, factor: float) -> QColor:
    r = int(c1.red() + (c2.red() - c1.red()) * factor)
    g = int(c1.green() + (c2.green() - c1.green()) * factor)
    b = int(c1.blue() + (c2.blue() - c1.blue()) * factor)
    a = int(c1.alpha() + (c2.alpha() - c1.alpha()) * factor)
    return QColor(r, g, b, a)


class SidebarButton(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, icon: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self.active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("SidebarButton")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.icon_label = SidebarIcon(key)
        self.icon_label.setObjectName("SidebarIcon")

        self.text_label = QLabel(text)
        self.text_label.setObjectName("SidebarText")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label, 1)

        # Hover animation property
        self._hover_factor = 0.0
        self.hover_anim = QPropertyAnimation(self, b"hover_factor")
        self.hover_anim.setDuration(150)
        self.hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.refresh_style()

    @Property(float)
    def hover_factor(self) -> float:
        return self._hover_factor

    @hover_factor.setter
    def hover_factor(self, value: float) -> None:
        self._hover_factor = value
        self.refresh_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)

    def set_active(self, active: bool) -> None:
        self.active = active
        if active:
            self._hover_factor = 0.0
        self.refresh_style()

    def enterEvent(self, event):
        if not self.active:
            self.hover_anim.stop()
            self.hover_anim.setStartValue(self._hover_factor)
            self.hover_anim.setEndValue(1.0)
            self.hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.active:
            self.hover_anim.stop()
            self.hover_anim.setStartValue(self._hover_factor)
            self.hover_anim.setEndValue(0.0)
            self.hover_anim.start()
        super().leaveEvent(event)

    def refresh_style(self) -> None:
        c_text_idle = QColor("#8e9bae")       # slate-400
        c_text_hover = QColor("#f1f5f9")      # slate-100
        c_text_active = QColor("#38bdf8")     # cyan active

        c_bg_idle = QColor(255, 255, 255, 0)
        c_bg_hover = QColor(255, 255, 255, 10)  # ~4% opacity
        
        # When active: blue outline glow, transparent dark blue background
        if self.active:
            bg_css = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(14, 165, 233, 0.16), stop:1 rgba(14, 165, 233, 0.04))"
            border_css = "1px solid rgba(14, 165, 233, 0.35)"
            text_css = "#38bdf8"
            icon_stroke_color = QColor("#38bdf8")
            icon_bg_color = QColor(14, 165, 233, 20)
        else:
            bg_color = blend_color(c_bg_idle, c_bg_hover, self._hover_factor)
            bg_css = f"rgba({bg_color.red()}, {bg_color.green()}, {bg_color.blue()}, {bg_color.alpha() / 255.0})"
            border_css = "1px solid transparent"
            text_color = blend_color(c_text_idle, c_text_hover, self._hover_factor)
            text_css = f"rgba({text_color.red()}, {text_color.green()}, {text_color.blue()}, {text_color.alpha() / 255.0})"
            icon_stroke_color = text_color
            icon_bg_color = QColor(0, 0, 0, 0)

        if hasattr(self, "icon_label") and isinstance(self.icon_label, SidebarIcon):
            self.icon_label.set_colors(icon_stroke_color, icon_bg_color)

        self.setStyleSheet(
            f"""
            QFrame#SidebarButton {{
                background: {bg_css};
                border: {border_css};
                border-radius: 12px;
            }}
            QLabel#SidebarText {{
                color: {text_css};
                font-weight: 600;
                font-size: 14px;
            }}
            """
        )
