# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, Optional


class ObservationType(str, Enum):
    PROCESS = "PROCESS"
    WINDOW = "WINDOW"
    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    SCREEN = "SCREEN"
    OCR = "OCR"
    VISION = "VISION"
    BROWSER = "BROWSER"
    TOOL_RESULT = "TOOL_RESULT"
    SYSTEM = "SYSTEM"


@dataclass
class BoundingBox:
    """Represents a 2D bounding box on screen [x, y, width, height]."""
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def is_inside(self, screen_width: int, screen_height: int) -> bool:
        if self.width <= 0 or self.height <= 0:
            return False
        return (
            0 <= self.x < screen_width
            and 0 <= self.y < screen_height
            and self.right <= screen_width
            and self.bottom <= screen_height
        )

    def contains_point(self, px: int, py: int) -> bool:
        return self.x <= px <= self.right and self.y <= py <= self.bottom

    def to_list(self) -> list[int]:
        return [self.x, self.y, self.width, self.height]

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_data(cls, data: Any) -> BoundingBox:
        if isinstance(data, BoundingBox):
            return data
        if isinstance(data, (list, tuple)) and len(data) >= 4:
            return cls(int(data[0]), int(data[1]), int(data[2]), int(data[3]))
        if isinstance(data, dict):
            return cls(
                int(data.get("x", 0)),
                int(data.get("y", 0)),
                int(data.get("width", data.get("w", 0))),
                int(data.get("height", data.get("h", 0))),
            )
        return cls(0, 0, 0, 0)


@dataclass
class VisionElement:
    """Represents a recognized GUI element on screen."""
    text: str
    bbox: BoundingBox
    confidence: float = 1.0
    element_type: str = "text"  # text, button, input, checkbox, tab, menu_item, icon
    id: Optional[str] = None
    source: str = "ocr"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "bbox": self.bbox.to_list(),
            "confidence": self.confidence,
            "type": self.element_type,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VisionElement:
        bbox_data = data.get("bbox") or [
            data.get("x", 0),
            data.get("y", 0),
            data.get("width", data.get("w", 0)),
            data.get("height", data.get("h", 0)),
        ]
        return cls(
            text=str(data.get("text", "")),
            bbox=BoundingBox.from_data(bbox_data),
            confidence=float(data.get("confidence", 1.0)),
            element_type=str(data.get("type", data.get("element_type", "text"))),
            id=data.get("id"),
            source=str(data.get("source", "ocr")),
        )


@dataclass
class VisionObservation:
    """Structured observation snapshot of a screen/GUI state."""
    screen_width: int
    screen_height: int
    window_title: str
    elements: list[VisionElement] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    source: str = "vision"
    image_hash: Optional[str] = None

    def is_stale(self, max_age_seconds: float = 5.0) -> bool:
        return (time.time() - self.timestamp) > max_age_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "window_title": self.window_title,
            "elements": [el.to_dict() for el in self.elements],
            "screenshot_path": self.screenshot_path,
            "timestamp": self.timestamp,
            "source": self.source,
            "image_hash": self.image_hash,
        }


import uuid


@dataclass
class Observation:
    """
    Represents an objective, factual observation of the physical system/environment state.
    Distinct from a tool's internal execution report.
    """

    source: str
    type: ObservationType
    data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    request_id: Optional[str] = None
    step_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "type": self.type.value if isinstance(self.type, ObservationType) else str(self.type),
            "data": self.data,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "step_id": self.step_id,
        }

