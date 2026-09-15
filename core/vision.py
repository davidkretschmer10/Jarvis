# -*- coding: utf-8 -*-
from __future__ import annotations

import ctypes
from enum import Enum
import hashlib
import io
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
import pyautogui

from core.observation import BoundingBox, Observation, ObservationType, VisionElement, VisionObservation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status Enums
# ---------------------------------------------------------------------------

class OCRStatus(str, Enum):
    OCR_AVAILABLE = "OCR_AVAILABLE"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    OCR_FAILED = "OCR_FAILED"


class VisionModelStatus(str, Enum):
    VISION_AVAILABLE = "VISION_AVAILABLE"
    VISION_UNAVAILABLE = "VISION_UNAVAILABLE"
    VISION_FAILED = "VISION_FAILED"


# ---------------------------------------------------------------------------
# Provider Interfaces
# ---------------------------------------------------------------------------

class BaseOCRProvider:
    """Abstract interface for local OCR providers."""

    def get_status(self) -> OCRStatus:
        raise NotImplementedError

    def extract_elements(self, image: Image.Image) -> Tuple[OCRStatus, List[VisionElement]]:
        raise NotImplementedError

    def read_text(self, image: Image.Image, lang: str = "ces+eng") -> Tuple[OCRStatus, str]:
        raise NotImplementedError


class BaseVisionModelProvider:
    """Abstract interface for local vision models (e.g. Ollama qwen2.5-vl)."""

    def get_status(self) -> VisionModelStatus:
        raise NotImplementedError

    def analyze(self, image_path: Path, prompt: str) -> Tuple[VisionModelStatus, str]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Tesseract OCR Provider
# ---------------------------------------------------------------------------

class TesseractOCRProvider(BaseOCRProvider):
    """
    Local OCR provider using Tesseract / pytesseract.
    Never throws unhandled exceptions; returns clean OCRStatus and empty data if unavailable.
    """

    def __init__(self) -> None:
        self._cached_status: Optional[OCRStatus] = None
        self._last_check_time: float = 0.0

    def get_status(self) -> OCRStatus:
        # Cache check result for 10 seconds
        now = time.time()
        if self._cached_status is not None and (now - self._last_check_time) < 10.0:
            return self._cached_status

        self._last_check_time = now
        try:
            from vision.tesseract_validator import check_tesseract
            ok, _ = check_tesseract()
            if ok:
                self._cached_status = OCRStatus.OCR_AVAILABLE
            else:
                self._cached_status = OCRStatus.OCR_UNAVAILABLE
        except Exception as exc:
            logger.debug("Tesseract check encountered error: %s", exc)
            self._cached_status = OCRStatus.OCR_UNAVAILABLE

        return self._cached_status

    def extract_elements(self, image: Image.Image) -> Tuple[OCRStatus, List[VisionElement]]:
        status = self.get_status()
        if status != OCRStatus.OCR_AVAILABLE:
            return status, []

        try:
            import pytesseract
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception as exc:
            logger.warning("pytesseract image_to_data failed: %s", exc)
            return OCRStatus.OCR_FAILED, []

        words = []
        n_boxes = len(data.get("text", []))
        for i in range(n_boxes):
            text = str(data["text"][i]).strip()
            conf_val = data["conf"][i]
            try:
                conf = float(conf_val)
            except (ValueError, TypeError):
                conf = -1.0

            if not text or conf < 20.0:
                continue

            words.append({
                "text": text,
                "x": int(data["left"][i]),
                "y": int(data["top"][i]),
                "w": int(data["width"][i]),
                "h": int(data["height"][i]),
                "conf": conf / 100.0,
                "line": int(data["line_num"][i]),
                "block": int(data["block_num"][i]),
            })

        if not words:
            return OCRStatus.OCR_AVAILABLE, []

        # Sort and group adjacent words on the same line
        words.sort(key=lambda w: (w["block"], w["line"], w["x"]))

        grouped = []
        current = words[0]
        for next_word in words[1:]:
            same_line = next_word["block"] == current["block"] and next_word["line"] == current["line"]
            near_x = next_word["x"] - (current["x"] + current["w"]) < 30  # px threshold

            if same_line and near_x:
                x_min = min(current["x"], next_word["x"])
                y_min = min(current["y"], next_word["y"])
                x_max = max(current["x"] + current["w"], next_word["x"] + next_word["w"])
                y_max = max(current["y"] + current["h"], next_word["y"] + next_word["h"])
                avg_conf = (current["conf"] + next_word["conf"]) / 2.0
                current = {
                    "text": current["text"] + " " + next_word["text"],
                    "x": x_min,
                    "y": y_min,
                    "w": x_max - x_min,
                    "h": y_max - y_min,
                    "conf": avg_conf,
                    "line": current["line"],
                    "block": current["block"],
                }
            else:
                grouped.append(current)
                current = next_word
        grouped.append(current)

        elements: List[VisionElement] = []
        for idx, item in enumerate(grouped):
            bbox = BoundingBox(x=item["x"], y=item["y"], width=item["w"], height=item["h"])
            elements.append(
                VisionElement(
                    id=f"el_{idx}",
                    text=item["text"],
                    bbox=bbox,
                    confidence=round(item["conf"], 3),
                    element_type="text",
                    source="ocr",
                )
            )

        return OCRStatus.OCR_AVAILABLE, elements

    def read_text(self, image: Image.Image, lang: str = "ces+eng") -> Tuple[OCRStatus, str]:
        status = self.get_status()
        if status != OCRStatus.OCR_AVAILABLE:
            return status, ""

        try:
            import pytesseract
            text = pytesseract.image_to_string(image, lang=lang).strip()
            return OCRStatus.OCR_AVAILABLE, text
        except Exception as exc:
            logger.warning("pytesseract image_to_string failed: %s", exc)
            return OCRStatus.OCR_FAILED, ""


# ---------------------------------------------------------------------------
# Ollama Vision Model Provider
# ---------------------------------------------------------------------------

class OllamaVisionProvider(BaseVisionModelProvider):
    """
    Local Vision Model provider leveraging Ollama (e.g. qwen2.5-vl).
    Uses the project's central Ollama session and checks local model availability.
    """

    def __init__(self, model_name: str = "qwen2.5-vl:7b", ollama_url: str = "http://localhost:11434") -> None:
        self.model_name = model_name
        self.ollama_url = ollama_url.rstrip("/")
        self._cached_status: Optional[VisionModelStatus] = None
        self._last_check_time: float = 0.0

    def get_status(self) -> VisionModelStatus:
        now = time.time()
        if self._cached_status is not None and (now - self._last_check_time) < 10.0:
            return self._cached_status

        self._last_check_time = now
        try:
            from ai.engine import get_ollama_session
            session = get_ollama_session()
        except Exception:
            import requests
            session = requests.Session()

        try:
            res = session.get(f"{self.ollama_url}/api/tags", timeout=3.0)
            if res.status_code != 200:
                self._cached_status = VisionModelStatus.VISION_UNAVAILABLE
                return self._cached_status

            models = res.json().get("models", [])
            installed = any(
                self.model_name in m.get("name", "") or self.model_name.split(":")[0] in m.get("name", "")
                for m in models
            )
            if installed:
                self._cached_status = VisionModelStatus.VISION_AVAILABLE
            else:
                self._cached_status = VisionModelStatus.VISION_UNAVAILABLE
        except Exception as exc:
            logger.debug("Ollama vision status check failed: %s", exc)
            self._cached_status = VisionModelStatus.VISION_UNAVAILABLE

        return self._cached_status

    def analyze(self, image_path: Path, prompt: str) -> Tuple[VisionModelStatus, str]:
        status = self.get_status()
        if status != VisionModelStatus.VISION_AVAILABLE:
            return status, ""

        import base64
        try:
            img_bytes = image_path.read_bytes()
            b64_img = base64.b64encode(img_bytes).decode("ascii")
        except Exception as exc:
            logger.error("Could not read image %s: %s", image_path, exc)
            return VisionModelStatus.VISION_FAILED, ""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "images": [b64_img],
            "stream": False,
        }

        try:
            from ai.engine import get_ollama_session
            session = get_ollama_session()
        except Exception:
            import requests
            session = requests.Session()

        try:
            res = session.post(f"{self.ollama_url}/api/generate", json=payload, timeout=60.0)
            if res.status_code == 200:
                out = res.json().get("response", "").strip()
                return VisionModelStatus.VISION_AVAILABLE, out
            return VisionModelStatus.VISION_FAILED, ""
        except Exception as exc:
            logger.error("Ollama vision generate failed: %s", exc)
            return VisionModelStatus.VISION_FAILED, ""


# ---------------------------------------------------------------------------
# Authoritative Vision Service
# ---------------------------------------------------------------------------

class VisionService:
    """
    Central Authoritative Vision & Screen Observation Service for Jarvis.
    Provides coordinated, cached screenshot capture, OCR parsing, window context,
    and image hashing for delta verification.
    """

    def __init__(
        self,
        ocr_provider: Optional[BaseOCRProvider] = None,
        vision_provider: Optional[BaseVisionModelProvider] = None,
        output_dir: Optional[Path] = None,
        default_max_age: float = 5.0,
    ) -> None:
        self.ocr = ocr_provider or TesseractOCRProvider()
        self.vision = vision_provider or OllamaVisionProvider()
        self.default_max_age = default_max_age

        if output_dir is not None:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("screenshots/vision")

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        self._cached_observation: Optional[VisionObservation] = None
        self._cached_image: Optional[Image.Image] = None

    def get_active_window_title(self) -> str:
        """Return title of currently focused Windows window using user32."""
        if os.name != "nt":
            return ""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    return buf.value.strip()
        except Exception:
            pass
        try:
            return pyautogui.getActiveWindowTitle() or ""
        except Exception:
            return ""

    @staticmethod
    def compute_image_hash(image: Image.Image) -> str:
        """Generate a fast SHA-256 hash of a thumbnail of the screen for delta checking."""
        try:
            thumb = image.copy()
            thumb.thumbnail((160, 120))
            thumb = thumb.convert("L")  # 8-bit grayscale
            raw_bytes = thumb.tobytes()
            return hashlib.sha256(raw_bytes).hexdigest()[:16]
        except Exception:
            return ""

    def capture_screen_image(self, region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """Capture screenshot via pyautogui and return PIL Image."""
        try:
            return pyautogui.screenshot(region=region)
        except Exception as exc:
            logger.warning("pyautogui.screenshot failed (%s), returning fallback blank image", exc)
            return Image.new("RGB", (1920, 1080), color=(255, 255, 255))

    def capture_observation(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        force_fresh: bool = False,
        max_age: Optional[float] = None,
        save_to_disk: bool = False,
    ) -> VisionObservation:
        """
        Capture or retrieve a cached VisionObservation.
        Screen capture is maintained in RAM (PIL Image) by default.
        Disk persistence only occurs if save_to_disk=True or debug mode is enabled.
        """
        effective_max_age = max_age if max_age is not None else self.default_max_age

        if (
            not force_fresh
            and self._cached_observation is not None
            and not self._cached_observation.is_stale(effective_max_age)
        ):
            return self._cached_observation

        # Capture new screen in RAM
        started = time.perf_counter()
        image = self.capture_screen_image(region=region)
        width, height = image.width, image.height
        window_title = self.get_active_window_title()
        img_hash = self.compute_image_hash(image)

        # Save screenshot file ONLY if explicitly requested for debug/diagnostics
        saved_path_str = None
        if save_to_disk or getattr(self, "save_screenshots", False):
            timestamp_str = time.strftime("%Y%m%d-%H%M%S")
            file_path = self.output_dir / f"screenshot_{timestamp_str}_{int(time.time()*1000)%10000}.png"
            try:
                image.save(file_path)
                saved_path_str = str(file_path.resolve())
            except Exception as exc:
                logger.warning("Could not persist screenshot to disk: %s", exc)
                saved_path_str = None

        # Extract OCR elements if available
        ocr_status, elements = self.ocr.extract_elements(image)

        obs = VisionObservation(
            screen_width=width,
            screen_height=height,
            window_title=window_title,
            elements=elements,
            screenshot_path=saved_path_str,
            timestamp=time.time(),
            source="vision_kernel",
            image_hash=img_hash,
        )

        self._cached_observation = obs
        self._cached_image = image

        elapsed = time.perf_counter() - started
        logger.debug(
            "Captured VisionObservation in %.3fs: %dx%d, %d elements, hash=%s, window='%s'",
            elapsed, width, height, len(elements), img_hash, window_title,
        )
        return obs

    def create_observation_record(
        self,
        vision_obs: VisionObservation,
        request_id: Optional[str] = None,
        step_id: Optional[int] = None,
    ) -> Observation:
        """Converts a VisionObservation to the standard core/observation.py Observation record."""
        return Observation(
            source="VisionService",
            type=ObservationType.VISION,
            data=vision_obs.to_dict(),
            confidence=1.0 if vision_obs.elements else 0.8,
            evidence={
                "screen_width": vision_obs.screen_width,
                "screen_height": vision_obs.screen_height,
                "window_title": vision_obs.window_title,
                "image_hash": vision_obs.image_hash,
                "screenshot_path": vision_obs.screenshot_path,
                "elements_count": len(vision_obs.elements),
            },
            timestamp=vision_obs.timestamp,
            request_id=request_id,
            step_id=step_id,
        )


# Global singleton
_default_vision_service: Optional[VisionService] = None


def get_vision_service() -> VisionService:
    global _default_vision_service
    if _default_vision_service is None:
        _default_vision_service = VisionService()
    return _default_vision_service
