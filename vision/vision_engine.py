from __future__ import annotations

import base64
from dataclasses import dataclass
import logging
from pathlib import Path
import time
from typing import Any

import requests

from vision.prompt_builder import build_screen_description_prompt
from vision.screenshot_manager import ScreenshotManager, ScreenshotResult


LOGGER = logging.getLogger(__name__)


class VisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class VisionConfig:
    model: str = "qwen2.5-vl:7b"
    ollama_url: str = "http://localhost:11434"
    timeout_seconds: float = 120.0
    keep_alive: str | None = "5m"
    default_max_image_size: tuple[int, int] | None = (1600, 1600)


@dataclass(frozen=True)
class VisionAnalysis:
    description: str
    model: str
    image_path: Path
    elapsed_seconds: float


class VisionEngine:
    def __init__(
        self,
        config: VisionConfig | None = None,
        screenshot_manager: ScreenshotManager | None = None,
    ) -> None:
        self.config = config or VisionConfig()
        self.screenshot_manager = screenshot_manager or ScreenshotManager()

    def describe_screen(self, extra_instruction: str | None = None) -> VisionAnalysis:
        screenshot = self.screenshot_manager.capture(max_size=self.config.default_max_image_size)
        return self.analyze_screenshot(screenshot.path, extra_instruction=extra_instruction)

    def analyze_screenshot(
        self,
        image_path: str | Path,
        prompt: str | None = None,
        extra_instruction: str | None = None,
    ) -> VisionAnalysis:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Screenshot not found: {path}")

        final_prompt = prompt or build_screen_description_prompt(extra_instruction)
        payload = self._build_payload(path, final_prompt)
        started = time.perf_counter()

        try:
            response = requests.post(
                f"{self.config.ollama_url.rstrip('/')}/api/generate",
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            LOGGER.error("Vision request timed out after %.1fs", self.config.timeout_seconds)
            raise VisionError(f"Ollama vision request timed out after {self.config.timeout_seconds:.1f}s") from exc
        except requests.RequestException as exc:
            LOGGER.error("Vision request failed: %s", exc)
            raise VisionError(f"Ollama vision request failed: {exc}") from exc

        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            LOGGER.error("Ollama returned non-JSON response: %s", response.text[:300])
            raise VisionError("Ollama returned a non-JSON vision response") from exc

        description = str(data.get("response", "")).strip()
        if not description:
            LOGGER.error("Ollama vision response did not contain text: %s", data)
            raise VisionError("Ollama vision response did not contain a description")

        elapsed = time.perf_counter() - started
        LOGGER.info("Vision analysis finished with %s in %.2fs", self.config.model, elapsed)
        return VisionAnalysis(
            description=description,
            model=self.config.model,
            image_path=path.resolve(),
            elapsed_seconds=elapsed,
        )

    def describe_screenshot(self, image_path: str | Path, extra_instruction: str | None = None) -> str:
        return self.analyze_screenshot(image_path, extra_instruction=extra_instruction).description

    def _build_payload(self, image_path: Path, prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "prompt": prompt,
            "images": [self._encode_image(image_path)],
            "stream": False,
        }
        if self.config.keep_alive is not None:
            payload["keep_alive"] = self.config.keep_alive
        return payload

    def _encode_image(self, image_path: Path) -> str:
        try:
            return base64.b64encode(image_path.read_bytes()).decode("ascii")
        except OSError as exc:
            LOGGER.error("Could not read image for vision analysis: %s", image_path)
            raise VisionError(f"Could not read image: {image_path}") from exc
