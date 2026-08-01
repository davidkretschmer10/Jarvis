from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, QObject
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


@dataclass(frozen=True)
class OverlayVisualState:
    name: str
    glow_strength: float
    pulse_speed: float
    orbit_speed: float
    status_text: str


OVERLAY_STATES = {
    "IDLE": OverlayVisualState("IDLE", 0.26, 0.025, 0.35, "Připraven"),
    "LISTENING": OverlayVisualState("LISTENING", 0.58, 0.075, 0.55, "Poslouchám..."),
    "THINKING": OverlayVisualState("THINKING", 0.42, 0.045, 1.80, "Přemýšlím..."),
    "SPEAKING": OverlayVisualState("SPEAKING", 0.64, 0.085, 0.85, "Mluvím..."),
    "ACTION_RUNNING": OverlayVisualState("ACTION_RUNNING", 0.52, 0.055, 1.15, "Provádím akci..."),
}


class OverlayAnimationManager(QObject):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._animations: list[QPropertyAnimation | QParallelAnimationGroup] = []

    def visual_state(self, state: str) -> OverlayVisualState:
        return OVERLAY_STATES.get(state, OVERLAY_STATES["IDLE"])

    def fade_in(self, widget: QWidget, duration: int = 180) -> None:
        effect = self._ensure_opacity_effect(widget)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(duration)
        animation.setStartValue(effect.opacity())
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self._run(animation)

    def fade_out(self, widget: QWidget, duration: int = 180) -> None:
        effect = self._ensure_opacity_effect(widget)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(duration)
        animation.setStartValue(effect.opacity())
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self._run(animation)

    def slide_to(self, widget: QWidget, target: QPoint, duration: int = 220) -> None:
        animation = QPropertyAnimation(widget, b"pos", self)
        animation.setDuration(duration)
        animation.setStartValue(widget.pos())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self._run(animation)

    def show_status(self, widget: QWidget, target: QPoint, duration: int = 180) -> None:
        effect = self._ensure_opacity_effect(widget)
        group = QParallelAnimationGroup(self)

        fade = QPropertyAnimation(effect, b"opacity", group)
        fade.setDuration(duration)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)

        slide = QPropertyAnimation(widget, b"pos", group)
        slide.setDuration(duration)
        slide.setStartValue(QPoint(target.x() + 10, target.y()))
        slide.setEndValue(target)
        slide.setEasingCurve(QEasingCurve.OutCubic)

        group.addAnimation(fade)
        group.addAnimation(slide)
        self._run(group)

    def _ensure_opacity_effect(self, widget: QWidget) -> QGraphicsOpacityEffect:
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(1.0)
            widget.setGraphicsEffect(effect)
        return effect

    def _run(self, animation: QPropertyAnimation | QParallelAnimationGroup) -> None:
        self._animations.append(animation)
        animation.finished.connect(lambda: self._forget(animation))
        animation.start()

    def _forget(self, animation: QPropertyAnimation | QParallelAnimationGroup) -> None:
        if animation in self._animations:
            self._animations.remove(animation)
        animation.deleteLater()
