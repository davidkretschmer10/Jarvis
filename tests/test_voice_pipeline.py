import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Voice.pipeline.realtime_pipeline import PipelineCallbacks, RealtimeVoicePipeline
from Voice.utils.config import VoiceConfig


class FakeTTS:
    def __init__(self):
        self.interrupted = False

    def speak_stream(self, chunks):
        return "".join(chunks)

    def interrupt(self):
        self.interrupted = True

    def shutdown(self):
        pass


class FakeCapture:
    def stop(self):
        pass


class FakeWake:
    def stop(self):
        pass


class RealtimePipelineTests(unittest.TestCase):
    def test_process_text_streams_chunks_and_done_callback(self):
        seen_chunks = []
        done = []
        pipeline = RealtimeVoicePipeline(
            VoiceConfig(),
            response_stream_factory=lambda text: iter(["Ahoj", "."]),
            callbacks=PipelineCallbacks(ai_chunk=seen_chunks.append, ai_done=done.append),
        )
        pipeline.tts.shutdown()
        pipeline.tts = FakeTTS()
        pipeline.capture = FakeCapture()
        pipeline.wakeword = FakeWake()

        reply = pipeline.process_text("test")
        self.assertEqual(reply, "Ahoj.")
        self.assertEqual(seen_chunks, ["Ahoj", "."])
        self.assertEqual(done, ["Ahoj."])


if __name__ == "__main__":
    unittest.main()
