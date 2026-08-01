from __future__ import annotations

from typing import TYPE_CHECKING, Any


__all__ = [
    "DebugVisualizer",
    "OverlayRenderer",
    "ScreenshotManager",
    "ScreenshotResult",
    "UIDetector",
    "UIElement",
    "UIResponse",
    "VisionAnalysis",
    "VisionConfig",
    "VisionEngine",
    "VisionError",
]


if TYPE_CHECKING:
    from vision.debug_visualizer import DebugVisualizer
    from vision.overlay_renderer import OverlayRenderer
    from vision.screenshot_manager import ScreenshotManager, ScreenshotResult
    from vision.schemas.ui_element import UIElement
    from vision.schemas.ui_response import UIResponse
    from vision.ui_detector import UIDetector
    from vision.vision_engine import VisionAnalysis, VisionConfig, VisionEngine, VisionError


def __getattr__(name: str) -> Any:
    if name == "DebugVisualizer":
        from vision.debug_visualizer import DebugVisualizer

        return DebugVisualizer
    if name == "OverlayRenderer":
        from vision.overlay_renderer import OverlayRenderer

        return OverlayRenderer
    if name in {"ScreenshotManager", "ScreenshotResult"}:
        from vision.screenshot_manager import ScreenshotManager, ScreenshotResult

        return {"ScreenshotManager": ScreenshotManager, "ScreenshotResult": ScreenshotResult}[name]
    if name in {"UIElement", "UIResponse"}:
        from vision.schemas.ui_element import UIElement
        from vision.schemas.ui_response import UIResponse

        return {"UIElement": UIElement, "UIResponse": UIResponse}[name]
    if name == "UIDetector":
        from vision.ui_detector import UIDetector

        return UIDetector
    if name in {"VisionAnalysis", "VisionConfig", "VisionEngine", "VisionError"}:
        from vision.vision_engine import VisionAnalysis, VisionConfig, VisionEngine, VisionError

        return {
            "VisionAnalysis": VisionAnalysis,
            "VisionConfig": VisionConfig,
            "VisionEngine": VisionEngine,
            "VisionError": VisionError,
        }[name]
    raise AttributeError(f"module 'vision' has no attribute {name!r}")
