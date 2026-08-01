from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


def apply_glow(widget: QWidget, color: str = "#0ea5e9", blur: int = 24, strength: int = 140) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, 0)
    glow_color = QColor(color)
    glow_color.setAlpha(strength)
    effect.setColor(glow_color)
    widget.setGraphicsEffect(effect)


def apply_soft_shadow(widget: QWidget, blur: int = 34, y_offset: int = 14, strength: int = 90) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    shadow_color = QColor("#000000")
    shadow_color.setAlpha(strength)
    effect.setColor(shadow_color)
    widget.setGraphicsEffect(effect)
