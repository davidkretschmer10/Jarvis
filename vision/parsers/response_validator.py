from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from vision.schemas.ui_element import ALLOWED_UI_ELEMENT_TYPES, UIElement
from vision.schemas.ui_response import UIResponse


LOGGER = logging.getLogger(__name__)


class ValidationError(ValueError):
    pass


class UIResponseValidator:
    REQUIRED_ELEMENT_FIELDS = {"id", "type", "text", "x", "y", "width", "height", "confidence"}

    def validate(
        self,
        data: dict[str, Any],
        screen_width: int,
        screen_height: int,
        image_path: str | Path | None = None,
        raw_response: str | None = None,
    ) -> UIResponse:
        if screen_width <= 0 or screen_height <= 0:
            raise ValidationError("Screen dimensions must be positive")

        screen_type = str(data.get("screen_type") or "unknown").strip() or "unknown"
        raw_elements = data.get("elements", [])
        if raw_elements is None:
            raw_elements = []
        if not isinstance(raw_elements, list):
            raise ValidationError("UI detection field 'elements' must be a list")

        elements: list[UIElement] = []
        for index, raw_element in enumerate(raw_elements):
            if not isinstance(raw_element, dict):
                LOGGER.warning("Skipping UI element %s: item is not an object", index)
                continue

            missing = self.REQUIRED_ELEMENT_FIELDS - raw_element.keys()
            if missing:
                LOGGER.warning("Skipping UI element %s: missing fields %s", index, sorted(missing))
                continue

            try:
                element = self._validate_element(raw_element, index, screen_width, screen_height)
            except ValidationError as exc:
                LOGGER.warning("Skipping UI element %s: %s", index, exc)
                continue
            elements.append(element)

        return UIResponse(
            screen_type=screen_type,
            elements=elements,
            image_path=Path(image_path).resolve() if image_path else None,
            image_width=screen_width,
            image_height=screen_height,
            raw_response=raw_response,
        )

    def _validate_element(
        self,
        raw: dict[str, Any],
        index: int,
        screen_width: int,
        screen_height: int,
    ) -> UIElement:
        element_id = str(raw["id"]).strip()
        if not element_id:
            element_id = f"element_{index}"

        element_type = str(raw["type"]).strip().lower()
        if element_type not in ALLOWED_UI_ELEMENT_TYPES:
            raise ValidationError(f"unsupported element type: {element_type}")

        try:
            x = int(round(float(raw["x"])))
            y = int(round(float(raw["y"])))
            width = int(round(float(raw["width"])))
            height = int(round(float(raw["height"])))
            confidence = float(raw["confidence"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("coordinates and confidence must be numeric") from exc

        if width <= 0 or height <= 0:
            raise ValidationError("width and height must be positive")
        if confidence < 0.0 or confidence > 1.0:
            confidence = max(0.0, min(1.0, confidence))

        x2 = x + width
        y2 = y + height
        if x2 <= 0 or y2 <= 0 or x >= screen_width or y >= screen_height:
            raise ValidationError("bounding box is outside the screenshot")

        clipped_x = max(0, x)
        clipped_y = max(0, y)
        clipped_x2 = min(screen_width, x2)
        clipped_y2 = min(screen_height, y2)

        return UIElement(
            id=element_id,
            type=element_type,
            text=str(raw["text"]).strip(),
            x=clipped_x,
            y=clipped_y,
            width=clipped_x2 - clipped_x,
            height=clipped_y2 - clipped_y,
            confidence=round(confidence, 4),
        )
