# -*- coding: utf-8 -*-
import unittest
from core.intents.intent_types import IntentType
from core.intents.intent_classifier import classify_intent
from core.intents.target_extractor import extract_target
from core.intents.command_router import build_search_url, route_and_execute_command
from unittest.mock import patch


class IntentsTests(unittest.TestCase):
    def test_intent_classification(self):
        test_cases = [
            ("zapni epic", IntentType.OPEN_APP, "epic"),
            ("otev\u0159i chrome", IntentType.OPEN_APP, "chrome"),
            ("spus\u0165 discord", IntentType.OPEN_APP, "discord"),
            ("launchni steam", IntentType.OPEN_APP, "steam"),
            ("naho\u010f blender", IntentType.OPEN_APP, "blender"),
            ("najdi youtube", IntentType.SEARCH_WEB, "youtube"),
            ("vyhledej chatgpt", IntentType.SEARCH_WEB, "chatgpt"),
            ("hledej wikipedia praha", IntentType.SEARCH_WEB, "praha"),
            ("stiskni enter", IntentType.CONTROL_PC, "enter"),
            ("zmackni ctrl+shift+esc", IntentType.CONTROL_PC, "ctrl+shift+esc"),
            ("screenshot", IntentType.CONTROL_PC, ""),
            ("sn\u00edmek obrazovky", IntentType.CONTROL_PC, ""),
            ("p\u0159e\u010dti obrazovku", IntentType.VISION, ""),
            ("ocr", IntentType.VISION, ""),
            ("co vid\u00ed\u0161", IntentType.VISION, ""),
            ("Ahoj Jarvis, jak se m\u00e1\u0161?", IntentType.CHAT, ""),
            ("napl\u00e1nuj mi v\u00fdlet", IntentType.CHAT, ""),
        ]
        
        for text, expected_intent, expected_target in test_cases:
            parsed = classify_intent(text)
            self.assertEqual(parsed.intent, expected_intent, f"Failed on: {text}")
            if expected_target:
                self.assertEqual(parsed.target.lower(), expected_target.lower(), f"Target mismatch on: {text}")

    def test_target_extraction_with_greetings_and_prepositions(self):
        self.assertEqual(extract_target("Jarvis, zapni epic", "zapni"), "epic")
        self.assertEqual(extract_target("Ahoj Jarvis, otev\u0159i chrome", "otevri"), "chrome")
        self.assertEqual(extract_target("najdi na internetu wikipedia praha", "najdi"), "praha")
        self.assertEqual(extract_target("vyhledej v prohl\u00ed\u017ee\u010di chatgpt", "vyhledej"), "chatgpt")
        self.assertEqual(extract_target("najdi youtube na webu", "najdi"), "youtube")

    def test_search_url_building(self):
        self.assertEqual(build_search_url("youtube"), "https://www.youtube.com/")
        self.assertEqual(build_search_url("chatgpt"), "https://chatgpt.com/")
        self.assertEqual(build_search_url("wikipedia praha", "wikipedia praha"), "https://cs.wikipedia.org/w/index.php?search=praha")
        self.assertEqual(build_search_url("nejlepsi procesory"), "https://www.google.com/search?q=nejlepsi%20procesory")

    @patch("core.intents.command_router.send_agent_command")
    def test_routing_responses(self, mock_send):
        mock_send.return_value = '{"ok": true, "result": "SUCCESS"}'
        
        # Test open app response formatting
        parsed = classify_intent("zapni epic")
        res = route_and_execute_command(parsed)
        self.assertEqual(res, "Epic Games Launcher je otev\u0159en\u00fd.")
        mock_send.assert_called_with("open", "epic")

        # Test search web response formatting
        parsed = classify_intent("najdi youtube")
        res = route_and_execute_command(parsed)
        self.assertEqual(res, "Otev\u00edr\u00e1m YouTube v prohl\u00ed\u017ee\u010di.")
        mock_send.assert_called_with("website", "https://www.youtube.com/")


if __name__ == "__main__":
    unittest.main()
