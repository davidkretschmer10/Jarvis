from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class EdgeHandle(QWidget):
    clicked = Signal()

    def __init__(self, side: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.side = side
        self.hovered = False
        self.opened = False
        self._rotation = 180.0 if side == "right" else 0.0
        self.setFixedSize(28, 78)
        self.setCursor(Qt.PointingHandCursor)

        self.rotation_anim = QPropertyAnimation(self, b"rotation")
        self.rotation_anim.setDuration(240)
        self.rotation_anim.setEasingCurve(QEasingCurve.InOutCubic)

    @Property(float)
    def rotation(self) -> float:
        return self._rotation

    @rotation.setter
    def rotation(self, value: float) -> None:
        self._rotation = value
        self.update()

    def set_open(self, opened: bool) -> None:
        self.opened = opened
        target = 180.0 if opened else 0.0
        if self.side == "right":
            target = 0.0 if opened else 180.0
        self.rotation_anim.stop()
        self.rotation_anim.setStartValue(self._rotation)
        self.rotation_anim.setEndValue(target)
        self.rotation_anim.start()

    def set_arrow(self, arrow: str) -> None:
        self.set_open(arrow in ("<", "◀"))

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
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._rotation)
        painter.translate(-self.width() / 2, -self.height() / 2)

        w = self.width()
        h = self.height()
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(w - 10, 0)
        path.lineTo(w, h / 2)
        path.lineTo(w - 10, h)
        path.lineTo(0, h)
        path.closeSubpath()

        fill = QColor(5, 16, 36, 235 if not self.hovered else 255)
        border = QColor(14, 165, 233, 170 if not self.hovered else 230)
        painter.setBrush(fill)
        painter.setPen(QPen(border, 1.2))
        painter.drawPath(path)

        painter.setPen(QPen(QColor("#7dd3fc"), 2.0))
        painter.drawText(self.rect(), Qt.AlignCenter, ">")
