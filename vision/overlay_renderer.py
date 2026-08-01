from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vision.schemas.ui_element import UIElement
from vision.schemas.ui_response import UIResponse


TYPE_COLORS = {
    "button": "#22c55e",
    "input": "#3b82f6",
    "dropdown": "#eab308",
    "menu_item": "#a855f7",
    "checkbox": "#14b8a6",
    "tab": "#f97316",
    "popup": "#ef4444",
}


class OverlayRenderer:
    def __init__(self, output_dir: str | Path = "screenshots/vision/debug") -> None:
        self.output_dir = Path(output_dir)

    def render(
        self,
        image_path: str | Path,
        ui_response: UIResponse,
        output_path: str | Path | None = None,
    ) -> Path:
        source = Path(image_path)
        if not source.is_file():
            raise FileNotFoundError(f"Screenshot not found: {source}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = Path(output_path) if output_path else self.output_dir / f"{source.stem}_ui_debug{source.suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source) as image:
            canvas = image.convert("RGBA")
            overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            font = ImageFont.load_default()

            for element in ui_response.elements:
                self._draw_element(draw, element, font)

            combined = Image.alpha_composite(canvas, overlay).convert("RGB")
            combined.save(target)

        return target.resolve()

    def _draw_element(self, draw: ImageDraw.ImageDraw, element: UIElement, font: ImageFont.ImageFont) -> None:
        color = TYPE_COLORS.get(element.type, "#ffffff")
        x1, y1, x2, y2 = element.box
        draw.rectangle((x1, y1, x2, y2), outline=color, width=3)

        label = self._label(element)
        left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
        label_width = right - left + 8
        label_height = bottom - top + 6
        label_y = max(0, y1 - label_height)

        draw.rectangle((x1, label_y, x1 + label_width, label_y + label_height), fill=color)
        draw.text((x1 + 4, label_y + 3), label, fill="#000000", font=font)

    def _label(self, element: UIElement) -> str:
        text = element.text.strip()
        if len(text) > 24:
            text = text[:21] + "..."
        if text:
            return f"{element.id} {element.type} {text}"
        return f"{element.id} {element.type}"
