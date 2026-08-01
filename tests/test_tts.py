import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Voice.tts.piper_engine import PiperEngine, split_sentences
from Voice.utils.config import VoiceConfig


class PiperEngineTests(unittest.TestCase):
    def test_split_sentences_keeps_partial_buffer(self):
        sentences, rest = split_sentences("Ahoj. Jak se mas")
        self.assertEqual(sentences, ["Ahoj."])
        self.assertEqual(rest, " Jak se mas")

    def test_normalize_text_for_czech_tts(self):
        engine = PiperEngine(VoiceConfig())
        self.addCleanup(engine.shutdown)
        self.assertIn("A I", engine._normalize_text("AI asistent"))


if __name__ == "__main__":
    unittest.main()
