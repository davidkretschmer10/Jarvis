from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vision.schemas.ui_element import UIElement


@dataclass(frozen=True)
class UIResponse:
    screen_type: str
    elements: list[UIElement]
    image_path: Path | None = None
    image_width: int | None = None
    image_height: int | None = None
    raw_response: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_type": self.screen_type,
            "elements": [element.to_dict() for element in self.elements],
        }

    def by_type(self, element_type: str) -> list[UIElement]:
        return [element for element in self.elements if element.type == element_type]

    def high_confidence(self, threshold: float = 0.75) -> list[UIElement]:
        return [element for element in self.elements if element.confidence >= threshold]
