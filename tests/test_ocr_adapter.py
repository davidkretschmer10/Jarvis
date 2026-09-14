# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from core.vision import (
    OCRStatus,
    OllamaVisionProvider,
    TesseractOCRProvider,
    VisionModelStatus,
    VisionService,
)


class TestOCRAdapter(unittest.TestCase):
    def setUp(self):
        self.dummy_image = Image.new("RGB", (300, 200), color="white")

    @patch("vision.tesseract_validator.check_tesseract", return_value=(False, "Chybí Tesseract"))
    def test_ocr_unavailable_when_tesseract_missing(self, mock_check):
        provider = TesseractOCRProvider()
        status = provider.get_status()
        self.assertEqual(status, OCRStatus.OCR_UNAVAILABLE)

        st, elements = provider.extract_elements(self.dummy_image)
        self.assertEqual(st, OCRStatus.OCR_UNAVAILABLE)
        self.assertEqual(elements, [])

        st, text = provider.read_text(self.dummy_image)
        self.assertEqual(st, OCRStatus.OCR_UNAVAILABLE)
        self.assertEqual(text, "")

    @patch("vision.tesseract_validator.check_tesseract", return_value=(True, "Připraveno"))
    def test_ocr_available_extracts_and_groups_elements(self, mock_check):
        provider = TesseractOCRProvider()

        # Mock pytesseract.image_to_data
        fake_data = {
            "text": ["", "Login", "Button", "", "Cancel"],
            "conf": [-1, "95", "90", -1, "85"],
            "left": [0, 50, 100, 0, 200],
            "top": [0, 30, 30, 0, 30],
            "width": [0, 45, 55, 0, 60],
            "height": [0, 20, 20, 0, 20],
            "line_num": [0, 1, 1, 0, 1],
            "block_num": [0, 1, 1, 0, 1],
        }

        with patch("pytesseract.image_to_data", return_value=fake_data):
            st, elements = provider.extract_elements(self.dummy_image)
            self.assertEqual(st, OCRStatus.OCR_AVAILABLE)
            self.assertEqual(len(elements), 2)  # "Login Button" grouped, and "Cancel"
            self.assertEqual(elements[0].text, "Login Button")
            self.assertEqual(elements[0].bbox.x, 50)
            self.assertEqual(elements[0].bbox.width, 105)
            self.assertAlmostEqual(elements[0].confidence, 0.925, places=2)
            self.assertEqual(elements[1].text, "Cancel")

    @patch("vision.tesseract_validator.check_tesseract", return_value=(True, "Připraveno"))
    def test_ocr_failure_handled_gracefully(self, mock_check):
        provider = TesseractOCRProvider()
        with patch("pytesseract.image_to_data", side_effect=RuntimeError("OCR Crash")):
            st, elements = provider.extract_elements(self.dummy_image)
            self.assertEqual(st, OCRStatus.OCR_FAILED)
            self.assertEqual(elements, [])

    def test_ollama_vision_unavailable_when_model_missing(self):
        provider = OllamaVisionProvider(model_name="qwen2.5-vl:7b")
        # Mocking session response without the vision model
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "models": [{"name": "llama3:latest"}, {"name": "mistral:latest"}]
        }

        mock_session = MagicMock()
        mock_session.get.return_value = fake_response

        with patch("ai.engine.get_ollama_session", return_value=mock_session):
            status = provider.get_status()
            self.assertEqual(status, VisionModelStatus.VISION_UNAVAILABLE)

            st, result = provider.analyze(image_path=MagicMock(), prompt="test")
            self.assertEqual(st, VisionModelStatus.VISION_UNAVAILABLE)
            self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
