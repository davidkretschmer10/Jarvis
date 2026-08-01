import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Voice.utils.config import VoiceConfig
from Voice.wakeword.porcupine_engine import PorcupineWakeWordEngine


class WakeWordTests(unittest.TestCase):
    def test_engine_lifecycle_without_starting_audio(self):
        engine = PorcupineWakeWordEngine(VoiceConfig(wake_word_sensitivity=0.5))
        self.assertFalse(engine.is_running)
        engine.stop()
        self.assertFalse(engine.is_running)


if __name__ == "__main__":
    unittest.main()
