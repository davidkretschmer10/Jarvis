# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import unittest

from core.observation import (
    BoundingBox,
    Observation,
    ObservationType,
    VisionElement,
    VisionObservation,
)


class TestVisionObservation(unittest.TestCase):
    def test_bounding_box_properties_and_center(self):
        bbox = BoundingBox(x=100, y=200, width=50, height=40)
        self.assertEqual(bbox.center, (125, 220))
        self.assertEqual(bbox.area, 2000)
        self.assertEqual(bbox.right, 150)
        self.assertEqual(bbox.bottom, 240)
        self.assertEqual(bbox.to_list(), [100, 200, 50, 40])
        self.assertEqual(bbox.to_dict(), {"x": 100, "y": 200, "width": 50, "height": 40})

    def test_bounding_box_is_inside(self):
        screen_w, screen_h = 1920, 1080
        valid_bbox = BoundingBox(x=100, y=100, width=200, height=50)
        self.assertTrue(valid_bbox.is_inside(screen_w, screen_h))

        # Negative x or y
        self.assertFalse(BoundingBox(x=-5, y=10, width=50, height=50).is_inside(screen_w, screen_h))
        self.assertFalse(BoundingBox(x=10, y=-5, width=50, height=50).is_inside(screen_w, screen_h))

        # Exceeds bounds
        self.assertFalse(BoundingBox(x=1900, y=100, width=50, height=50).is_inside(screen_w, screen_h))
        self.assertFalse(BoundingBox(x=100, y=1060, width=50, height=50).is_inside(screen_w, screen_h))

        # Zero or negative width/height
        self.assertFalse(BoundingBox(x=100, y=100, width=0, height=50).is_inside(screen_w, screen_h))
        self.assertFalse(BoundingBox(x=100, y=100, width=50, height=-10).is_inside(screen_w, screen_h))

    def test_bounding_box_contains_point(self):
        bbox = BoundingBox(x=50, y=50, width=100, height=100)
        self.assertTrue(bbox.contains_point(50, 50))
        self.assertTrue(bbox.contains_point(100, 100))
        self.assertTrue(bbox.contains_point(150, 150))
        self.assertFalse(bbox.contains_point(49, 100))
        self.assertFalse(bbox.contains_point(151, 100))

    def test_bounding_box_from_data(self):
        b1 = BoundingBox.from_data([10, 20, 30, 40])
        self.assertEqual(b1.to_list(), [10, 20, 30, 40])

        b2 = BoundingBox.from_data({"x": 15, "y": 25, "width": 35, "height": 45})
        self.assertEqual(b2.to_list(), [15, 25, 35, 45])

        b3 = BoundingBox.from_data(b1)
        self.assertEqual(b3.to_list(), [10, 20, 30, 40])

    def test_vision_element_serialization(self):
        el = VisionElement(
            id="el_1",
            text="Přihlásit",
            bbox=BoundingBox(x=200, y=300, width=100, height=40),
            confidence=0.96,
            element_type="button",
            source="ocr",
        )
        d = el.to_dict()
        self.assertEqual(d["text"], "Přihlásit")
        self.assertEqual(d["type"], "button")
        self.assertEqual(d["bbox"], [200, 300, 100, 40])
        self.assertEqual(d["confidence"], 0.96)

        restored = VisionElement.from_dict(d)
        self.assertEqual(restored.text, "Přihlásit")
        self.assertEqual(restored.element_type, "button")
        self.assertEqual(restored.bbox.to_list(), [200, 300, 100, 40])

    def test_vision_observation_staleness(self):
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Test Window",
            elements=[],
            timestamp=time.time() - 10.0,
        )
        self.assertTrue(obs.is_stale(max_age_seconds=5.0))
        self.assertFalse(obs.is_stale(max_age_seconds=15.0))

    def test_observation_with_vision_type(self):
        obs = Observation(
            source="VisionService",
            type=ObservationType.VISION,
            data={"window": "Browser"},
            confidence=0.95,
            request_id="req_123",
            step_id=2,
        )
        d = obs.to_dict()
        self.assertEqual(d["type"], "VISION")
        self.assertEqual(d["source"], "VisionService")
        self.assertEqual(d["request_id"], "req_123")
        self.assertEqual(d["step_id"], 2)
        self.assertTrue(len(d["id"]) > 0)


if __name__ == "__main__":
    unittest.main()
