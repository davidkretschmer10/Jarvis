# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from core.observation import BoundingBox, VisionElement, VisionObservation
from core.verification import (
    StepVerifierRegistry,
    UIInteractionVerifier,
    VerificationStatus,
)
from core.vision import OCRStatus


class TestGUIVerification(unittest.TestCase):
    def setUp(self):
        self.verifier = UIInteractionVerifier()

    def test_observed_delta_explicit_success(self):
        step = {"tool": "click", "input": {"x": 100, "y": 200}}
        tool_output = {"ok": True, "observed_delta": True, "delta_evidence": "Button clicked"}

        res = self.verifier.verify(step, tool_output)
        self.assertEqual(res.status, VerificationStatus.VERIFIED)
        self.assertTrue(res.is_verified())

    def test_observed_delta_explicit_failure(self):
        step = {"tool": "click", "input": {"x": 100, "y": 200}}
        tool_output = {"ok": True, "observed_delta": False, "delta_evidence": "Screen unchanged"}

        res = self.verifier.verify(step, tool_output)
        self.assertEqual(res.status, VerificationStatus.FAILED)
        self.assertTrue(res.is_failed())

    def test_screen_hash_delta_verification(self):
        step = {"tool": "click"}
        # Different hashes -> screen changed!
        tool_output = {"ok": True, "pre_hash": "abc12345", "post_hash": "def67890"}

        res = self.verifier.verify(step, tool_output)
        self.assertEqual(res.status, VerificationStatus.VERIFIED)

    def test_expected_window_title_verification(self):
        step = {"tool": "click", "expected": {"window_title": "Editor"}}
        tool_output = {"ok": True}

        with patch("core.vision.VisionService.get_active_window_title", return_value="Visual Studio Code - Editor"):
            res = self.verifier.verify(step, tool_output)
            self.assertEqual(res.status, VerificationStatus.VERIFIED)

        with patch("core.vision.VisionService.get_active_window_title", return_value="Calculator"):
            res_fail = self.verifier.verify(step, tool_output)
            self.assertEqual(res_fail.status, VerificationStatus.FAILED)

    def test_expected_text_appears_with_ocr_available(self):
        step = {"tool": "smart_click", "expected": "text appears: Úspěšně uloženo"}
        tool_output = {"ok": True}

        matching_el = VisionElement(
            id="el_msg",
            text="Úspěšně uloženo",
            bbox=BoundingBox(10, 10, 100, 20),
            confidence=0.95,
        )
        fake_obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="App",
            elements=[matching_el],
        )

        with patch("core.vision.VisionService.capture_observation", return_value=fake_obs), \
             patch("core.vision.TesseractOCRProvider.get_status", return_value=OCRStatus.OCR_AVAILABLE):
            res = self.verifier.verify(step, tool_output)
            self.assertEqual(res.status, VerificationStatus.VERIFIED)

    def test_expected_text_appears_when_ocr_unavailable_returns_unknown(self):
        step = {"tool": "smart_click", "expected": "text appears: Úspěšně uloženo"}
        tool_output = {"ok": True}

        with patch("core.vision.TesseractOCRProvider.get_status", return_value=OCRStatus.OCR_UNAVAILABLE):
            res = self.verifier.verify(step, tool_output)
            # CRITICAL RULE: OCR unavailable must yield UNKNOWN, never VERIFIED or SUCCESS!
            self.assertEqual(res.status, VerificationStatus.UNKNOWN)

    def test_expected_element_disappears_verification(self):
        step = {"tool": "click", "expected": "button disappears: Dialog Box"}
        tool_output = {"ok": True}

        # Observation where Dialog Box is gone
        empty_obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Main App",
            elements=[],
        )

        with patch("core.vision.VisionService.capture_observation", return_value=empty_obs), \
             patch("core.vision.TesseractOCRProvider.get_status", return_value=OCRStatus.OCR_AVAILABLE):
            res = self.verifier.verify(step, tool_output)
            self.assertEqual(res.status, VerificationStatus.VERIFIED)

    def test_unknown_result_when_no_delta_can_be_proven(self):
        step = {"tool": "click", "input": {"x": 50, "y": 50}}
        tool_output = {"ok": True}  # Tool says ok, but no delta, hash, or expected state

        res = self.verifier.verify(step, tool_output)
        self.assertEqual(res.status, VerificationStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
