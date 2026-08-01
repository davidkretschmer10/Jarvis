from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Callable, Iterable, Optional

import numpy as np
import soundfile as sf

from Voice.audio_output import AudioOutput
from Voice.config import VoiceConfig, load_voice_config
from Voice.interruption import InterruptionController
from Voice.microphone import Microphone
from Voice.streaming import LatencyTimer
from Voice.tts_engine import BaseTTS, create_tts
from Voice.wake_word import WakeWord
from Voice.whisper_engine import TranscriptionResult, WhisperEngine


LOGGER = logging.getLogger(__name__)
VolumeCallback = Callable[[int], None]


class VoiceManager:
    """Thread-safe local voice facade used by GUI and compatibility adapters."""

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or load_voice_config()
        self.microphone = Microphone(self.config)
        self.stt = WhisperEngine(self.config)
        self.audio_output = AudioOutput(self.config.speaker_device)
        self.tts: BaseTTS = create_tts(self.config, self.audio_output)
        self.wake_word = WakeWord(self.config)
        self.interruption = InterruptionController(self.interrupt_speech)
        self.interruption.set_enabled(self.config.interrupt_enabled)
        self._manual_chunks: "queue.Queue[np.ndarray]" = queue.Queue()
        self._record_lock = threading.Lock()

    def set_stt_model(self, model_name: str) -> None:
        self.stt.set_model(model_name)

    def start_recording(self, volume_callback: Optional[VolumeCallback] = None) -> None:
        self.interrupt_speech()
        with self._record_lock:
            self._clear_manual_chunks()

            def frame_callback(audio: np.ndarray, sample_rate: int) -> None:
                self._manual_chunks.put(audio)

            self.microphone.start(
                volume_callback=volume_callback,
                frame_callback=frame_callback,
                speech_callback=self.interruption.on_user_speech,
            )

    def stop_recording(self) -> None:
        self.microphone.stop()

    def speech_to_text(self, partial_callback: Optional[Callable[[str], None]] = None) -> str:
        self.stop_recording()
        chunks = []
        while not self._manual_chunks.empty():
            try:
                chunks.append(self._manual_chunks.get_nowait())
                self._manual_chunks.task_done()
            except queue.Empty:
                break
        if not chunks:
            return ""

        audio = np.concatenate(chunks).astype("float32")
        if len(audio) < int(self.config.min_record_seconds * self.config.sample_rate):
            return ""
        self._save_recording(audio, self.config.sample_rate)
        result = self.stt.transcribe_audio(audio, self.config.sample_rate, partial_callback)
        return result.text

    def listen_once_to_text(
        self,
        volume_callback: Optional[VolumeCallback] = None,
        partial_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        try:
            recording = self.microphone.record_until_silence(
                volume_callback=volume_callback,
                speech_callback=self.interruption.on_user_speech,
            )
            if len(recording.audio) < int(self.config.min_record_seconds * recording.sample_rate):
                return ""
            self._save_recording(recording.audio, recording.sample_rate)
            result = self.stt.transcribe_recording(recording, partial_callback=partial_callback)
            return result.text
        except Exception as exc:
            LOGGER.warning("Voice listen/transcribe failed: %s", exc)
            return ""

    def transcribe_recording(self, audio: np.ndarray, sample_rate: int) -> TranscriptionResult:
        return self.stt.transcribe_audio(audio, sample_rate)

    def speak(self, text: str) -> None:
        if not text or not self.config.enabled:
            return
        self.interruption.mark_speaking(True)
        self.tts.speak(text)

    def speak_stream(self, chunks: Iterable[str]) -> str:
        if not self.config.enabled:
            return "".join(chunks)
        self.interruption.mark_speaking(True)
        return self.tts.speak_stream(chunks)

    def stream_llm_to_tts(
        self,
        chunks: Iterable[str],
        chunk_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        timer = LatencyTimer()

        def yielding_stream():
            for chunk in chunks:
                if chunk_callback:
                    chunk_callback(chunk)
                yield chunk

        full = self.speak_stream(yielding_stream())
        LOGGER.info("LLM latency %.3fs", timer.elapsed())
        return full

    def interrupt_speech(self) -> None:
        self.tts.interrupt()
        self.audio_output.stop()
        self.interruption.mark_speaking(False)

    def wake_listener(self, callback: Callable[[], None]) -> None:
        self.wake_word.start(callback)

    def stop_wake_listener(self) -> None:
        self.wake_word.stop()

    def shutdown(self) -> None:
        self.stop_wake_listener()
        self.microphone.stop()
        self.tts.shutdown()

    def _clear_manual_chunks(self) -> None:
        while not self._manual_chunks.empty():
            try:
                self._manual_chunks.get_nowait()
                self._manual_chunks.task_done()
            except queue.Empty:
                break

    def _save_recording(self, audio: np.ndarray, sample_rate: int) -> None:
        if not self.config.save_recordings:
            return
        try:
            os.makedirs(self.config.recordings_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            path = os.path.join(self.config.recordings_dir, f"user_voice_{timestamp}.wav")
            sf.write(path, audio, sample_rate)
        except Exception as exc:
            LOGGER.debug("Could not save voice recording: %s", exc)


_manager: Optional[VoiceManager] = None
_manager_lock = threading.Lock()


def get_voice_manager() -> VoiceManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = VoiceManager()
        return _manager
