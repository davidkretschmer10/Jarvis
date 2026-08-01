from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from vision.parsers.response_validator import UIResponseValidator
from vision.parsers.ui_parser import UIParser
from vision.prompt_builder import build_ui_detection_prompt
from vision.schemas.ui_response import UIResponse
from vision.screenshot_manager import ScreenshotManager
from vision.vision_engine import VisionEngine


LOGGER = logging.getLogger(__name__)


class VisionError(Exception):
    """Exception raised when Tesseract OCR or Vision features are not available or fail."""
    pass


class UIDetector:
    def __init__(
        self,
        vision_engine: VisionEngine | None = None,
        screenshot_manager: ScreenshotManager | None = None,
        parser: UIParser | None = None,
        validator: UIResponseValidator | None = None,
    ) -> None:
        self.screenshot_manager = screenshot_manager or ScreenshotManager()
        self.vision_engine = vision_engine or VisionEngine(screenshot_manager=self.screenshot_manager)
        self.parser = parser or UIParser()
        self.validator = validator or UIResponseValidator()

    def detect_screen(self, extra_instruction: str | None = None) -> UIResponse:
        screenshot = self.screenshot_manager.capture(
            max_size=self.vision_engine.config.default_max_image_size,
        )
        return self.detect_screenshot(
            screenshot.path,
            screen_width=screenshot.width,
            screen_height=screenshot.height,
            extra_instruction=extra_instruction,
        )

    def _extract_ocr_elements(self, image: Image.Image) -> list[dict[str, Any]]:
        try:
            import pytesseract
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception as e:
            LOGGER.error("pytesseract error during layout extraction: %s", e)
            return []

        words = []
        n_boxes = len(data.get("text", []))
        for i in range(n_boxes):
            text = str(data["text"][i]).strip()
            conf_val = data["conf"][i]
            try:
                conf = float(conf_val)
            except (ValueError, TypeError):
                conf = -1.0
            if not text or conf < 30:
                continue
            words.append({
                "text": text,
                "x": int(data["left"][i]),
                "y": int(data["top"][i]),
                "w": int(data["width"][i]),
                "h": int(data["height"][i]),
                "line": int(data["line_num"][i]),
                "block": int(data["block_num"][i]),
            })

        if not words:
            return []

        # Group adjacent words on same line
        words.sort(key=lambda w: (w["block"], w["line"], w["x"]))

        grouped_elements = []
        current = words[0]
        for next_word in words[1:]:
            same_line = next_word["block"] == current["block"] and next_word["line"] == current["line"]
            near_x = next_word["x"] - (current["x"] + current["w"]) < 25  # px threshold
            
            if same_line and near_x:
                x_min = min(current["x"], next_word["x"])
                y_min = min(current["y"], next_word["y"])
                x_max = max(current["x"] + current["w"], next_word["x"] + next_word["w"])
                y_max = max(current["y"] + current["h"], next_word["y"] + next_word["h"])
                current = {
                    "text": current["text"] + " " + next_word["text"],
                    "x": x_min,
                    "y": y_min,
                    "w": x_max - x_min,
                    "h": y_max - y_min,
                    "line": current["line"],
                    "block": current["block"],
                }
            else:
                grouped_elements.append(current)
                current = next_word
        grouped_elements.append(current)

        return [
            {
                "text": el["text"],
                "x": el["x"],
                "y": el["y"],
                "width": el["w"],
                "height": el["h"],
            }
            for el in grouped_elements
        ]

    def _build_ui_layout_prompt(self, window_title: str, elements: list[dict[str, Any]], extra_instruction: str | None = None) -> str:
        elements_str = ""
        for idx, el in enumerate(elements):
            elements_str += f"ID: {idx} | Text: \"{el['text']}\" | Box: [{el['x']}, {el['y']}, {el['width']}, {el['height']}]\n"

        prompt = f"""Jsi UI detection modul asistenta Jarvis pro Windows.
Máš k dispozici seznam textových prvků nalezených na obrazovce pomocí OCR.
Aktivní okno: "{window_title}"

Tvým úkolem je analyzovat tyto prvky a identifikovat, které z nich jsou interaktivní ovládací prvky (tlačítka, vstupní pole, checkboxy, dropdowny, záložky, položky menu atd.).
Přiřaď každému nalezenému interaktivnímu prvku správný typ (button, input, dropdown, menu_item, checkbox, tab, popup).
U vstupních polí (input), pokud OCR nalezlo pouze textový popisek (např. "Hledat" nebo "Uživatelské jméno"), ale samotné pole je vedle něj prázdné, můžeš použít souřadnice popisku nebo odvodit souřadnice klikatelné oblasti hned vedle.
U tlačítek (button) a odkazů (které mapuj jako button nebo menu_item) použij přesně souřadnice textu.

Vrať POUZE validní JSON objekt. Žádný text okolo, žádné vysvětlení, žádné markdown uvozovky ```json.

Formát JSON:
{{
  "screen_type": "název_aplikace_nebo_webu",
  "elements": [
    {{
      "id": "btn_login",
      "type": "button",
      "text": "Přihlásit",
      "x": 441,
      "y": 220,
      "width": 120,
      "height": 40,
      "confidence": 0.95
    }}
  ]
}}

Zde jsou nalezené textové prvky na obrazovce:
{elements_str}
"""
        if extra_instruction:
            prompt += f"\nDodatečná instrukce: {extra_instruction.strip()}"
        return prompt

    def detect_screenshot(
        self,
        image_path: str | Path,
        screen_width: int | None = None,
        screen_height: int | None = None,
        extra_instruction: str | None = None,
    ) -> UIResponse:
        from vision.tesseract_validator import check_tesseract
        ok, msg = check_tesseract()
        if not ok:
            raise VisionError("Vision systém není dostupný. Zkontrolujte instalaci OCR (Tesseract).")

        path = Path(image_path)
        if screen_width is None or screen_height is None:
            screen_width, screen_height = self._read_image_size(path)

        try:
            image = Image.open(path)
        except Exception as e:
            LOGGER.error("Failed to open screenshot for OCR: %s", e)
            return UIResponse(screen_type="unknown", elements=[], image_path=path)

        try:
            import pyautogui
            window_title = pyautogui.getActiveWindowTitle() or "Neznámé okno"
        except Exception:
            window_title = "Neznámé okno"

        raw_ocr = self._extract_ocr_elements(image)
        prompt = self._build_ui_layout_prompt(window_title, raw_ocr, extra_instruction)

        from ai.engine import ask_ai
        raw_response = ask_ai(prompt, chat_model="llama3")

        try:
            parsed = self.parser.parse(raw_response)
        except Exception as e:
            LOGGER.warning("Failed to parse Llama 3 response as JSON: %s. Raw: %s", e, raw_response)
            parsed = {"screen_type": "unknown", "elements": []}

        response = self.validator.validate(
            parsed,
            screen_width=screen_width,
            screen_height=screen_height,
            image_path=path,
            raw_response=raw_response,
        )
        LOGGER.info("Detected %s UI elements on %s", len(response.elements), path)
        return response

    def _read_image_size(self, image_path: Path) -> tuple[int, int]:
        with Image.open(image_path) as image:
            return image.width, image.height

