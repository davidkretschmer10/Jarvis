from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from core.event_bus import EventBus
from core.runtime import JarvisRuntime
from Voice.config import VoiceConfig, get_default_audio_dir
from Voice.microphone import RecordingResult
from Voice.voice_manager import VoiceManager, VoiceState, get_voice_manager, reset_voice_manager
from Voice.whisper_engine import TranscriptionResult
import interfaces.voice as voice_interface


class TestVoiceConfig(unittest.TestCase):
    def test_default_recordings_dir_is_in_appdata(self):
        config = VoiceConfig()
        self.assertFalse(config.save_recordings)
        self.assertIn("audio", config.recordings_dir.lower())
        self.assertNotEqual(config.recordings_dir, "Voice")

    def test_legacy_property_getters_and_setters(self):
        config = VoiceConfig(
            whisper_model="test-whisper",
            whisper_fallback_model="test-fallback",
            whisper_language="en",
            tts_voice="test-voice.onnx",
            tts_rate=1.15,
            tts_pitch=3,
            tts_volume=0.8,
            realtime_mode=True,
            porcupine_access_key="dummy_key",
            wake_word_sensitivity=0.75,
        )
        self.assertEqual(config.stt_model, "test-whisper")
        self.assertEqual(config.whisper_model, "test-whisper")
        self.assertEqual(config.stt_fallback_model, "test-fallback")
        self.assertEqual(config.whisper_fallback_model, "test-fallback")
        self.assertEqual(config.language, "en")
        self.assertEqual(config.whisper_language, "en")
        self.assertEqual(config.piper_voice, "test-voice.onnx")
        self.assertEqual(config.tts_voice, "test-voice.onnx")
        self.assertEqual(config.speed, 1.15)
        self.assertEqual(config.tts_rate, 1.15)
        self.assertEqual(config.pitch, 3)
        self.assertEqual(config.tts_pitch, 3)
        self.assertEqual(config.volume, 0.8)
        self.assertEqual(config.tts_volume, 0.8)
        self.assertTrue(config.streaming_enabled)
        self.assertTrue(config.realtime_mode)
        self.assertEqual(config.porcupine_access_key, "dummy_key")
        self.assertEqual(config.wake_word_sensitivity, 0.75)


class TestVoiceManagerLifecycleAndEvents(unittest.TestCase):
    def setUp(self):
        reset_voice_manager()
        self.tmp_dir = tempfile.mkdtemp()
        self.config = VoiceConfig(
            save_recordings=True,
            recordings_dir=self.tmp_dir,
            min_record_seconds=0.01,
            sample_rate=16000,
        )
        self.event_bus = EventBus()
        self.events_received = []

        for evt in [
            "voice_status_changed",
            "voice_listening",
            "voice_transcribing",
            "voice_transcribed",
            "voice_processing",
            "voice_speaking",
            "voice_finished",
            "voice_error",
            "voice_interrupted",
        ]:
            self.event_bus.on(evt, lambda data, name=evt: self.events_received.append((name, data)))

        self.manager = VoiceManager(config=self.config, event_bus=self.event_bus)

    def tearDown(self):
        self.manager.shutdown()
        reset_voice_manager()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_initial_state_is_stopped(self):
        self.assertEqual(self.manager.state, VoiceState.STOPPED)

    def test_double_start_and_double_stop_safety(self):
        # Mock microphone start to prevent opening hardware audio device
        self.manager.microphone.start = MagicMock()
        self.manager.microphone.stop = MagicMock()

        self.manager.start_recording()
        self.assertEqual(self.manager.state, VoiceState.LISTENING)

        # Second start call must not fail or corrupt state
        self.manager.start_recording()
        self.assertEqual(self.manager.state, VoiceState.LISTENING)

        self.manager.stop_recording()
        self.assertEqual(self.manager.state, VoiceState.STOPPED)

        # Second stop call must be completely safe
        self.manager.stop_recording()
        self.assertEqual(self.manager.state, VoiceState.STOPPED)

    def test_speech_to_text_with_mock_flow(self):
        self.manager.microphone.start = MagicMock()
        self.manager.microphone.stop = MagicMock()

        # Simulate audio chunk in queue
        sample_audio = np.ones(3200, dtype="float32") * 0.05
        self.manager._manual_chunks.put(sample_audio)

        self.manager.stt.transcribe_audio = MagicMock(
            return_value=TranscriptionResult("Ahoj Jarvis", "cs", 0.1, "mock-whisper")
        )

        text = self.manager.speech_to_text()
        self.assertEqual(text, "Ahoj Jarvis")

        # Verify EventBus events were fired
        event_names = [e[0] for e in self.events_received]
        self.assertIn("voice_transcribing", event_names)
        self.assertIn("voice_transcribed", event_names)
        self.assertIn("voice_finished", event_names)

        # Verify recording was saved into temp dir and NOT project root
        saved_files = os.listdir(self.tmp_dir)
        self.assertTrue(any(f.startswith("user_voice_") and f.endswith(".wav") for f in saved_files))

    def test_listen_once_to_text_with_mock_recording(self):
        sample_audio = np.ones(3200, dtype="float32") * 0.05
        mock_rec = RecordingResult(audio=sample_audio, sample_rate=16000, duration=0.2, stopped_by_silence=True)
        self.manager.microphone.record_until_silence = MagicMock(return_value=mock_rec)
        self.manager.stt.transcribe_recording = MagicMock(
            return_value=TranscriptionResult("Spusť kalkulačku", "cs", 0.1, "mock-whisper")
        )

        result = self.manager.listen_once_to_text()
        self.assertEqual(result, "Spusť kalkulačku")
        self.assertEqual(self.manager.state, VoiceState.STOPPED)

    def test_speak_and_interruption(self):
        self.manager.tts.speak = MagicMock()
        self.manager.audio_output.stop = MagicMock()

        self.manager.speak("Ahoj světe")
        self.manager.tts.speak.assert_called_once_with("Ahoj světe")

        # Interruption
        self.manager.interrupt_speech()
        self.manager.audio_output.stop.assert_called_once()
        event_names = [e[0] for e in self.events_received]
        self.assertIn("voice_interrupted", event_names)

    def test_stt_failure_handled_gracefully(self):
        sample_audio = np.ones(3200, dtype="float32") * 0.05
        self.manager._manual_chunks.put(sample_audio)
        self.manager.stt.transcribe_audio = MagicMock(side_effect=RuntimeError("Whisper CUDA OOM"))

        text = self.manager.speech_to_text()
        self.assertEqual(text, "")
        self.assertEqual(self.manager.state, VoiceState.STOPPED)

        event_names = [e[0] for e in self.events_received]
        self.assertIn("voice_error", event_names)

    def test_microphone_failure_handled_gracefully(self):
        self.manager.microphone.start = MagicMock(side_effect=OSError("Audio device busy"))
        with self.assertRaises(OSError):
            self.manager.start_recording()

        self.assertEqual(self.manager.state, VoiceState.STOPPED)
        event_names = [e[0] for e in self.events_received]
        self.assertIn("voice_error", event_names)


class TestVoiceSubpackagesCompatibility(unittest.TestCase):
    def test_stt_subpackage_wrapper(self):
        from Voice.stt.whisper_engine import WhisperEngine, TranscriptionResult
        self.assertTrue(callable(WhisperEngine))
        self.assertTrue(callable(TranscriptionResult))

    def test_tts_subpackage_wrapper(self):
        from Voice.tts.piper_engine import PiperEngine, PiperTTS, split_sentences, split_for_tts
        self.assertTrue(callable(PiperEngine))
        self.assertTrue(callable(PiperTTS))
        s, rest = split_sentences("Ahoj! Jak se mas?")
        self.assertEqual(s, ["Ahoj!", "Jak se mas?"])
        self.assertEqual(rest, "")

    def test_tts_audio_player_wrapper(self):
        from Voice.tts.audio_player import AudioPlayer
        player = AudioPlayer()
        self.addCleanup(player.shutdown)
        self.assertTrue(hasattr(player, "play"))
        self.assertTrue(hasattr(player, "stop"))

    def test_audio_capture_wrapper(self):
        from Voice.audio.audio_capture import AudioCapture, RecordingResult
        capture = AudioCapture(VoiceConfig())
        self.assertTrue(hasattr(capture, "start"))
        self.assertTrue(hasattr(capture, "stop"))

    def test_audio_vad_wrapper(self):
        from Voice.audio.vad import VoiceActivityDetector, VADResult
        vad = VoiceActivityDetector()
        res = vad.analyze_float32(np.zeros(160, dtype="float32"))
        self.assertFalse(res.is_speech)

    def test_utils_config_wrapper(self):
        from Voice.utils.config import VoiceConfig as UtilConfig, load_voice_config
        cfg = UtilConfig()
        self.assertTrue(hasattr(cfg, "whisper_model"))

    def test_wakeword_wrapper(self):
        from Voice.wakeword.porcupine_engine import PorcupineWakeWordEngine
        engine = PorcupineWakeWordEngine()
        self.assertFalse(engine.is_running)
        engine.stop()
        self.assertFalse(engine.is_running)


class TestVoiceInterfaceAndRuntimeIntegration(unittest.TestCase):
    def setUp(self):
        reset_voice_manager()
        self.event_bus = EventBus()
        import sys
        if "interfaces.voice" in sys.modules and getattr(sys.modules["interfaces.voice"], "__file__", None) is None:
            sys.modules.pop("interfaces.voice", None)
        global voice_interface
        import interfaces.voice as voice_interface
        voice_interface.set_event_bus(self.event_bus)

    def tearDown(self):
        reset_voice_manager()

    def test_interface_delegation(self):
        vm = get_voice_manager()
        vm.microphone.start = MagicMock()
        vm.microphone.stop = MagicMock()

        voice_interface.start_recording()
        self.assertEqual(voice_interface.get_voice_state(), VoiceState.LISTENING)
        voice_interface.stop_recording()
        self.assertEqual(voice_interface.get_voice_state(), VoiceState.STOPPED)

    def test_no_recordings_in_project_root(self):
        # Verify that no .wav or .mp3 files exist in workspace root
        for fname in os.listdir("."):
            if fname.endswith((".wav", ".mp3", ".ogg", ".flac")):
                self.fail(f"Audio file found in project root: {fname}")


if __name__ == "__main__":
    unittest.main()
