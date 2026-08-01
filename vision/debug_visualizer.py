from __future__ import annotations

from pathlib import Path

from vision.overlay_renderer import OverlayRenderer
from vision.schemas.ui_response import UIResponse
from vision.ui_detector import UIDetector


class DebugVisualizer:
    def __init__(
        self,
        detector: UIDetector | None = None,
        renderer: OverlayRenderer | None = None,
    ) -> None:
        self.detector = detector or UIDetector()
        self.renderer = renderer or OverlayRenderer()

    def detect_and_render_screen(self, extra_instruction: str | None = None) -> tuple[UIResponse, Path]:
        response = self.detector.detect_screen(extra_instruction=extra_instruction)
        if response.image_path is None:
            raise ValueError("UI response does not include an image path")
        debug_path = self.renderer.render(response.image_path, response)
        return response, debug_path

    def render_existing(self, image_path: str | Path, response: UIResponse) -> Path:
        return self.renderer.render(image_path, response)
