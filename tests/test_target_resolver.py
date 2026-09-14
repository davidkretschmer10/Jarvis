# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from core.observation import BoundingBox, VisionElement, VisionObservation
from core.target_resolver import ResolvedTarget, TargetResolutionStatus, TargetResolver


class TestTargetResolver(unittest.TestCase):
    def setUp(self):
        self.mock_vision_service = MagicMock()
        self.resolver = TargetResolver(
            vision_service=self.mock_vision_service,
            confidence_threshold=0.70,
        )

    def test_explicit_coordinate_resolution(self):
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Desktop",
            elements=[],
        )
        # String coords
        res1 = self.resolver.resolve("500, 300", observation=obs)
        self.assertTrue(res1.is_valid)
        self.assertEqual(res1.center, (500, 300))
        self.assertEqual(res1.source, "explicit_coordinate")

        # Dict coords
        res2 = self.resolver.resolve({"x": 640, "y": 480}, observation=obs)
        self.assertTrue(res2.is_valid)
        self.assertEqual(res2.center, (640, 480))

        # Out of bounds coords
        res_oob = self.resolver.resolve("2500, 500", observation=obs)
        self.assertFalse(res_oob.is_valid)
        self.assertEqual(res_oob.status, TargetResolutionStatus.OUT_OF_BOUNDS)

    def test_deterministic_window_resolution(self):
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Kalkulačka",
            elements=[],
        )
        res = self.resolver.resolve("kalkulačka", observation=obs)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.source, "deterministic_window")
        self.assertEqual(res.target_type, "window")

    def test_ocr_element_resolution(self):
        btn = VisionElement(
            id="btn_1",
            text="Přihlásit se",
            bbox=BoundingBox(x=100, y=200, width=120, height=40),
            confidence=0.95,
            element_type="button",
            source="ocr",
        )
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Moje Aplikace",
            elements=[btn],
        )

        res = self.resolver.resolve("tlačítko Přihlásit", observation=obs)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.name, "Přihlásit se")
        self.assertEqual(res.center, (160, 220))
        self.assertEqual(res.source, "ocr")

    def test_dialog_synonyms_resolution(self):
        ok_btn = VisionElement(
            id="btn_ok",
            text="OK",
            bbox=BoundingBox(x=500, y=600, width=80, height=35),
            confidence=0.98,
            element_type="button",
            source="ocr",
        )
        cancel_btn = VisionElement(
            id="btn_cancel",
            text="Storno",
            bbox=BoundingBox(x=600, y=600, width=80, height=35),
            confidence=0.98,
            element_type="button",
            source="ocr",
        )
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Uložit soubor",
            elements=[ok_btn, cancel_btn],
        )

        # "potvrdit" -> resolves to "OK"
        res_ok = self.resolver.resolve("potvrdit", observation=obs)
        self.assertTrue(res_ok.is_valid)
        self.assertEqual(res_ok.name, "OK")

        # "zrušit" -> resolves to "Storno"
        res_cancel = self.resolver.resolve("zrušit", observation=obs)
        self.assertTrue(res_cancel.is_valid)
        self.assertEqual(res_cancel.name, "Storno")

    def test_low_confidence_rejection(self):
        low_btn = VisionElement(
            id="btn_blur",
            text="Odeslat",
            bbox=BoundingBox(x=100, y=100, width=80, height=30),
            confidence=0.55,  # Below 0.70 threshold
            element_type="button",
            source="ocr",
        )
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Formulář",
            elements=[low_btn],
        )

        res = self.resolver.resolve("Odeslat", observation=obs)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, TargetResolutionStatus.LOW_CONFIDENCE)

    def test_ambiguous_matching(self):
        item1 = VisionElement(
            id="el_1",
            text="Nastavení profilu",
            bbox=BoundingBox(x=100, y=100, width=150, height=30),
            confidence=0.95,
            source="ocr",
        )
        item2 = VisionElement(
            id="el_2",
            text="Nastavení účtu",
            bbox=BoundingBox(x=100, y=150, width=150, height=30),
            confidence=0.95,
            source="ocr",
        )
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Settings",
            elements=[item1, item2],
        )

        res = self.resolver.resolve("Nastavení", observation=obs)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, TargetResolutionStatus.AMBIGUOUS)
        self.assertTrue(len(res.ambiguous_candidates) >= 2)

    def test_target_not_found(self):
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Plocha",
            elements=[],
        )
        res = self.resolver.resolve("NeznáméTlačítko", observation=obs)
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, TargetResolutionStatus.NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
