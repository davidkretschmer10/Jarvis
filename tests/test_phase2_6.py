from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from core.planner import Planner
from tools.registry import ToolRegistry
from core.agent import open_program
from core.intents.command_router import build_search_url


class TestAppMatching(unittest.TestCase):
    @patch("core.agent.load_scanned_apps")
    @patch("os.startfile")
    def test_app_matching_scoring_priorities(self, mock_startfile, mock_load):
        # Setup mock scanned apps list representing the user's issue
        mock_load.return_value = {
            "c": "C:\\Program Files\\Dev-Cpp\\c++.exe",
            "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "notepad": "C:\\Windows\\notepad.exe",
            "kalkulacka": "C:\\Windows\\System32\\calc.exe",
        }

        # 1. Exact match Chrome
        res = open_program("chrome")
        self.assertTrue(res.get("ok"))
        self.assertIn("SUCCESS", res.get("result", ""))
        self.assertIn("chrome.exe", res.get("result", ""))
        mock_startfile.assert_called_with("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")

        # 2. Alias match "Google Chrome"
        res = open_program("Google Chrome")
        self.assertTrue(res.get("ok"))
        self.assertIn("SUCCESS", res.get("result", ""))
        self.assertIn("chrome.exe", res.get("result", ""))

        # 3. Alias match "poznámkový blok" -> notepad
        res = open_program("poznámkový blok")
        self.assertTrue(res.get("ok"))
        self.assertIn("SUCCESS", res.get("result", ""))
        self.assertIn("notepad.exe", res.get("result", ""))

        # 4. Alias match "calc" -> kalkulacka
        res = open_program("calc")
        self.assertTrue(res.get("ok"))
        self.assertIn("SUCCESS", res.get("result", ""))
        self.assertIn("calc.exe", res.get("result", ""))

        # 5. Collision mitigation: "Chrome" should NEVER resolve to "c++.exe" (scanned as 'c')
        # Even though "c" is a substring of "chrome", exact/alias/executable matches must win.
        # Ensure 'c' is not matched for Chrome.
        res = open_program("chrome")
        self.assertNotIn("c++.exe", res.get("result", ""))


class TestUrlFirstRouting(unittest.TestCase):
    @patch("ai.engine.ask_ai")
    def test_planner_validation_loop(self, mock_ask_ai):
        # Registry and planner setup
        reg = ToolRegistry()
        planner = Planner(registry=reg)

        # Mock 1st attempt: returns illegal smart_click and smart_write steps
        illegal_plan = json.dumps([
            {"tool": "open_app", "input": {"name": "chrome"}, "description": "Otevřít Chrome"},
            {"tool": "smart_write", "input": {"target": "Hledat", "text": "seznam"}, "description": "Napsat seznam"},
            {"tool": "press_key", "input": {"key": "enter"}, "description": "Potvrdit"}
        ])

        # Mock 2nd attempt: corrected plan using open_website
        corrected_plan = json.dumps([
            {"tool": "open_app", "input": {"name": "chrome"}, "description": "Otevřít Chrome"},
            {"tool": "open_website", "input": {"url": "https://www.seznam.cz"}, "description": "Otevřít Seznam"}
        ])

        mock_ask_ai.side_effect = [illegal_plan, corrected_plan]

        # Call planner for "Otevři Chrome a vyhledej Seznam"
        steps = planner.plan("Otevři Chrome a vyhledej Seznam")

        # Verify loop executed and rejected the first plan, accepting the second
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["tool"], "open_app")
        self.assertEqual(steps[1]["tool"], "open_website")
        self.assertEqual(steps[1]["input"]["url"], "https://www.seznam.cz")
        self.assertEqual(mock_ask_ai.call_count, 2)

    def test_search_url_generation(self):
        # Vyhledej Nvidia
        url = build_search_url("Nvidia", "Vyhledej Nvidia")
        self.assertEqual(url, "https://www.google.com/search?q=Nvidia")

        # Otevři Seznam
        url = build_search_url("Seznam", "Otevři Seznam")
        self.assertEqual(url, "https://www.seznam.cz/")
