from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_UI_ELEMENT_TYPES = {
    "button",
    "input",
    "dropdown",
    "menu_item",
    "checkbox",
    "tab",
    "popup",
}


@dataclass(frozen=True)
class UIElement:
    id: str
    type: str
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "confidence": self.confidence,
        }
