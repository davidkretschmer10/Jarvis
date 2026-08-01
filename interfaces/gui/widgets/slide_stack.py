from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QRect
from PySide6.QtWidgets import QStackedWidget, QWidget


class SlideStack(QStackedWidget):
    """QStackedWidget with Arc/Raycast-style horizontal slide transitions."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.pages: dict[str, QWidget] = {}
        self.keys: list[str] = []
        self.current_key = ""
        self._animation: QParallelAnimationGroup | None = None
        self.setContentsMargins(0, 0, 0, 0)

    def add_page(self, key: str, widget: QWidget) -> None:
        self.pages[key] = widget
        self.keys.append(key)
        self.addWidget(widget)
        if not self.current_key:
            self.current_key = key
            self.setCurrentWidget(widget)

    def replace_page(self, key: str, widget: QWidget) -> None:
        old = self.pages.get(key)
        old_index = self.indexOf(old) if old else -1
        if old:
            self.removeWidget(old)
            old.deleteLater()
        self.pages[key] = widget
        if old_index >= 0:
            self.insertWidget(old_index, widget)
        else:
            self.addWidget(widget)
            self.keys.append(key)
        if self.current_key == key:
            self.setCurrentWidget(widget)

    def direction_between(self, previous_key: str, next_key: str) -> int:
        try:
            return 1 if self.keys.index(next_key) > self.keys.index(previous_key) else -1
        except ValueError:
            return 1

    def set_current(self, key: str, direction: int | None = None, animated: bool = True) -> None:
        if key not in self.pages or key == self.current_key:
            return

        old_key = self.current_key
        old_widget = self.currentWidget()
        new_widget = self.pages[key]
        self.current_key = key

        if direction is None:
            direction = self.direction_between(old_key, key)
        direction = 1 if direction >= 0 else -1

        if not animated or old_widget is None:
            self.setCurrentWidget(new_widget)
            return

        w = max(1, self.width())
        h = max(1, self.height())
        old_rect = QRect(0, 0, w, h)
        old_end = QRect(-direction * w, 0, w, h)
        new_start = QRect(direction * w, 0, w, h)
        new_end = QRect(0, 0, w, h)

        self.setCurrentWidget(new_widget)
        old_widget.setGeometry(old_rect)
        new_widget.setGeometry(new_start)
        old_widget.show()
        new_widget.show()
        new_widget.raise_()

        group = QParallelAnimationGroup(self)
        for widget, start, end in ((old_widget, old_rect, old_end), (new_widget, new_start, new_end)):
            animation = QPropertyAnimation(widget, b"geometry", group)
            animation.setDuration(350)
            animation.setStartValue(start)
            animation.setEndValue(end)
            animation.setEasingCurve(QEasingCurve.InOutCubic)
            group.addAnimation(animation)

        def finish() -> None:
            self.setCurrentWidget(new_widget)
            new_widget.setGeometry(self.rect())
            old_widget.hide()

        group.finished.connect(finish)
        self._animation = group
        group.start()
