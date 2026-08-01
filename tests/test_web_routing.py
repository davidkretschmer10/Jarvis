# -*- coding: utf-8 -*-
import unittest
from core.intents.intent_types import IntentType
from core.intents.intent_classifier import classify_intent
from core.intents.command_router import build_search_url


class WebRoutingTests(unittest.TestCase):
    def test_wikipedia_open_request_is_web_request(self):
        text = "otevri mi v chromu wikipedii na tema karluv most"
        parsed = classify_intent(text)
        self.assertEqual(parsed.intent, IntentType.SEARCH_WEB)

    def test_wikipedia_url_uses_search_page(self):
        text = "otevri mi v chromu wikipedii na tema karluv most"
        parsed = classify_intent(text)
        url = build_search_url(parsed.target, text)
        self.assertEqual(url, "https://cs.wikipedia.org/w/index.php?search=karluv%20most")

    def test_google_search_request(self):
        text = "najdi mi nejlepsi grafickou kartu"
        parsed = classify_intent(text)
        url = build_search_url(parsed.target, text)
        self.assertEqual(url, "https://www.google.com/search?q=nejlepsi%20grafickou%20kartu")

    def test_youtube_search_request(self):
        text = "otevri youtube na tema python tutorial"
        parsed = classify_intent(text)
        url = build_search_url(parsed.target, text)
        self.assertEqual(url, "https://www.youtube.com/results?search_query=python%20tutorial")


if __name__ == "__main__":
    unittest.main()
