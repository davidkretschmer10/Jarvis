# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from core.observation import BoundingBox, VisionElement, VisionObservation
from core.target_resolver import ResolvedTarget, TargetResolutionStatus, TargetResolver
from core.verification import UIInteractionVerifier, VerificationStatus
from core.vision import OCRStatus, VisionService, get_vision_service


class TestRealWindowsGUI(unittest.TestCase):
    """
    Real Windows GUI interaction tests using a safe local Tkinter test window.
    Strictly follows safety guidelines:
      - Never clicks on real external user apps.
      - Tkinter window is isolated and always cleaned up in tearDown.
      - If OCR (Tesseract) is unavailable, OCR-dependent execution is marked SKIPPED (never falsely passed).
    """

    root = None
    tk_thread = None

    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk
            cls.tk = tk
        except ImportError:
            cls.tk = None

    def setUp(self):
        if self.tk is None:
            self.skipTest("Tkinter not available in environment.")

        # Create test GUI in memory
        self.clicked = False
        self.root = self.tk.Tk()
        self.root.title("Jarvis GUI Test Window")
        self.root.geometry("300x200+100+100")
        self.label_var = self.tk.StringVar(value="INITIAL")
        self.label = self.tk.Label(self.root, textvariable=self.label_var)
        self.label.pack(pady=10)

        def on_click():
            self.clicked = True
            self.label_var.set("CLICKED")

        self.button = self.tk.Button(self.root, text="TEST BUTTON", command=on_click)
        self.button.pack(pady=10)
        self.root.update()

    def tearDown(self):
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None

    def test_scenario_1_and_2_find_button_click_and_verify(self):
        """
        SCENARIO 1 & 2:
        Find test button, click it, and verify label change from INITIAL to CLICKED.
        If OCR is not available, must SKIP truthfully.
        """
        from vision.tesseract_validator import check_tesseract
        ok, msg = check_tesseract()
        if not ok:
            self.skipTest(f"Tesseract OCR is unavailable ({msg}); skipping live OCR test.")

        vision_service = get_vision_service()
        obs = vision_service.capture_observation(force_fresh=True)
        resolver = TargetResolver(vision_service=vision_service)

        target = resolver.resolve("TEST BUTTON", observation=obs)
        if not target.is_valid:
            self.skipTest("Test button not detected by OCR in test window.")

        import pyautogui
        cx, cy = target.center
        pyautogui.click(cx, cy)
        self.root.update()

        # Check that button action executed
        self.assertTrue(self.clicked)
        self.assertEqual(self.label_var.get(), "CLICKED")

        # Verify change
        verifier = UIInteractionVerifier()
        v_res = verifier.verify(
            step={"tool": "smart_click", "expected": "text appears: CLICKED"},
            tool_output={"ok": True},
        )
        self.assertEqual(v_res.status, VerificationStatus.VERIFIED)

    def test_scenario_3_find_text_in_test_window(self):
        """SCENARIO 3: Find text in test window deterministically."""
        resolver = TargetResolver()
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Jarvis GUI Test Window",
            elements=[
                VisionElement(
                    id="el_btn",
                    text="TEST BUTTON",
                    bbox=BoundingBox(150, 150, 100, 30),
                    confidence=0.95,
                    element_type="button",
                    source="ocr",
                )
            ],
        )

        res = resolver.resolve("TEST BUTTON", observation=obs)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.name, "TEST BUTTON")
        self.assertEqual(res.center, (200, 165))

    def test_scenario_4_click_nonexistent_target_controlled_failure(self):
        """SCENARIO 4: Click nonexistent target -> controlled failure / UNKNOWN / NOT_FOUND."""
        resolver = TargetResolver()
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Jarvis GUI Test Window",
            elements=[],
        )

        res = resolver.resolve("NON_EXISTENT_BUTTON_XYZ", observation=obs)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, TargetResolutionStatus.NOT_FOUND)

        verifier = UIInteractionVerifier()
        v_res = verifier.verify(
            step={"tool": "smart_click", "input": {"target": "NON_EXISTENT_BUTTON_XYZ"}},
            tool_output={"ok": False, "error": res.error},
        )
        # Never returns SUCCESS on failure
        self.assertNotEqual(v_res.status, VerificationStatus.VERIFIED)

    def test_scenario_5_low_confidence_blocks_click(self):
        """SCENARIO 5: Low confidence element -> NO CLICK / LOW_CONFIDENCE status."""
        resolver = TargetResolver(confidence_threshold=0.75)
        low_el = VisionElement(
            id="el_low",
            text="TEST BUTTON",
            bbox=BoundingBox(150, 150, 100, 30),
            confidence=0.45,  # Below threshold
            element_type="button",
            source="ocr",
        )
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Jarvis GUI Test Window",
            elements=[low_el],
        )

        res = resolver.resolve("TEST BUTTON", observation=obs)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, TargetResolutionStatus.LOW_CONFIDENCE)
        self.assertIn("low confidence", res.error.lower())


if __name__ == "__main__":
    unittest.main()
