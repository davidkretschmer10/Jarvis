from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget, QFrame

from interfaces.gui.sidebar.sidebar_button import SidebarIcon
from interfaces.gui.widgets.avatar import JarvisAvatar


class TopPanelButton(QFrame):
    """Vertical navigation item for the TopNavigationBar (icon on top, text below)."""
    clicked = Signal(str)

    def __init__(self, key: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self.active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("TopPanelButton")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        # Reuse painted vector icon
        self.icon_widget = SidebarIcon(key)
        self.icon_widget.setObjectName("TopButtonIcon")
        self.icon_widget.setFixedSize(24, 24)

        self.text_label = QLabel(text)
        self.text_label.setObjectName("TopButtonText")
        self.text_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.icon_widget, 0, Qt.AlignCenter)
        layout.addWidget(self.text_label, 0, Qt.AlignCenter)

        self.refresh_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)

    def set_active(self, active: bool) -> None:
        self.active = active
        self.refresh_style()

    def enterEvent(self, event):
        self.setProperty("hovered", True)
        self.refresh_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setProperty("hovered", False)
        self.refresh_style()
        super().leaveEvent(event)

    def refresh_style(self):
        hovered = self.property("hovered")
        
        if self.active:
            stroke = QColor("#38bdf8")
            bg = QColor(14, 165, 233, 20)
            text_color = "#38bdf8"
        elif hovered:
            stroke = QColor("#f1f5f9")
            bg = QColor(255, 255, 255, 10)
            text_color = "#f1f5f9"
        else:
            stroke = QColor("#64748b")
            bg = QColor(0, 0, 0, 0)
            text_color = "#64748b"

        self.icon_widget.set_colors(stroke, bg)
        self.text_label.setStyleSheet(
            f"color: {text_color}; font-size: 11px; font-weight: 600;"
        )


class TopNavigationBar(QWidget):
    """The global top trapezoid panel hosting the navigation button icons."""
    section_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(690, 64)
        self.buttons: dict[str, TopPanelButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(46, 0, 46, 0)  # Safe bounds for angled sides
        layout.setSpacing(18)

        # Centered brand avatar indicator
        self.logo = JarvisAvatar(size=26, parent=self)
        self.logo.hide()

        nav_items = (
            ("chat", "Chat"),
            ("voice", "Voice"),
            ("settings", "Settings"),
            ("models", "Modifikace"),
            ("memory", "Paměť"),
            ("tools", "Nástroje"),
        )

        for key, text in nav_items:
            btn = TopPanelButton(key, text)
            btn.clicked.connect(self.section_changed.emit)
            self.buttons[key] = btn
            layout.addWidget(btn)

        self.set_active("chat")

    def set_active(self, key: str):
        for btn_key, btn in self.buttons.items():
            btn.set_active(btn_key == key)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(w, 0)
        path.lineTo(w - 35, h)
        path.lineTo(35, h)
        path.closeSubpath()

        # Dark core translucent body fill
        painter.setBrush(QColor(3, 8, 18, 230))
        # Neon blue border
        pen = QPen(QColor(14, 165, 233, 150), 1.2)
        painter.setPen(pen)
        painter.drawPath(path)


# Keep class alias for backward compatibility imports
from PySide6.QtWidgets import QFrame
class JarvisSidebar(TopNavigationBar):
    pass
