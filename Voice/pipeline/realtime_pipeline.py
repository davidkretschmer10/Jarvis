from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from Voice.audio.audio_capture import AudioCapture
from Voice.stt.whisper_engine import TranscriptionResult, WhisperEngine
from Voice.tts.piper_engine import PiperEngine
from Voice.utils.config import VoiceConfig
from Voice.wakeword.porcupine_engine import PorcupineWakeWordEngine


LOGGER = logging.getLogger(__name__)


StatusCallback = Callable[[str], None]
TextCallback = Callable[[str], None]
VolumeCallback = Callable[[int], None]
ResponseStreamFactory = Callable[[str], object]


@dataclass
class PipelineCallbacks:
    status: Optional[StatusCallback] = None
    user_text: Optional[TextCallback] = None
    partial_text: Optional[TextCallback] = None
    ai_chunk: Optional[TextCallback] = None
    ai_done: Optional[TextCallback] = None
    volume: Optional[VolumeCallback] = None
    error: Optional[TextCallback] = None


class RealtimeVoicePipeline:
    """Wake -> record -> transcribe -> stream AI -> sentence TTS orchestration."""

    def __init__(self, config: VoiceConfig, response_stream_factory: ResponseStreamFactory, callbacks: Optional[PipelineCallbacks] = None):
        self.config = config
        self.callbacks = callbacks or PipelineCallbacks()
        self.response_stream_factory = response_stream_factory
        self.capture = AudioCapture(config)
        self.stt = WhisperEngine(config)
        self.tts = PiperEngine(config)
        self.wakeword = PorcupineWakeWordEngine(config)
        self._active = threading.Event()
        self._conversation_lock = threading.Lock()
        self._cancel_event = threading.Event()

    def start_wake_word(self) -> None:
        self._emit_status("Wake word listening")
        self.wakeword.start(self._on_wake_word)

    def stop_wake_word(self) -> None:
        self.wakeword.stop()
        self._emit_status("Wake word disabled")

    def start_manual_recording(self, volume_callback: Optional[VolumeCallback] = None) -> None:
        cb = volume_callback or self.callbacks.volume
        self.interrupt()
        self._emit_status("Recording")
        self.capture.start(volume_callback=cb)

    def stop_manual_recording(self) -> TranscriptionResult:
        self.capture.stop()
        chunks = []
        while not self.capture.frames.empty():
            chunks.append(self.capture.frames.get())
        self._emit_status("Transcribing")
        return self.stt.transcribe_chunks(chunks, self.config.sample_rate, self._emit_partial)

    def record_once_and_process(self) -> None:
        threading.Thread(target=self._record_once_and_process, daemon=True).start()

    def interrupt(self) -> None:
        self._cancel_event.set()
        self.capture.stop()
        self.tts.interrupt()
        self._cancel_event.clear()

    def shutdown(self) -> None:
        self.stop_wake_word()
        self.interrupt()
        self.tts.shutdown()

    def _on_wake_word(self) -> None:
        self._emit_status("Wake word detected")
        self.record_once_and_process()

    def _record_once_and_process(self) -> None:
        if not self._conversation_lock.acquire(blocking=False):
            return
        try:
            self.interrupt()
            self._emit_status("Recording")
            recording = self.capture.record_until_silence(volume_callback=self.callbacks.volume)
            self._emit_status("Transcribing")
            result = self.stt.transcribe_recording(recording, partial_callback=self._emit_partial)
            if not result.text:
                self._emit_status("Ready")
                return
            if self.callbacks.user_text:
                self.callbacks.user_text(result.text)
            self.process_text(result.text)
        except Exception as exc:
            LOGGER.exception("Realtime pipeline failed")
            if self.callbacks.error:
                self.callbacks.error(str(exc))
        finally:
            self._emit_status("Ready")
            self._conversation_lock.release()

    def process_text(self, text: str) -> str:
        self._emit_status("Thinking")
        stream = self.response_stream_factory(text)
        self._emit_status("Speaking")

        def yielding_stream():
            for chunk in stream:
                if self._cancel_event.is_set():
                    break
                if self.callbacks.ai_chunk:
                    self.callbacks.ai_chunk(chunk)
                yield chunk

        full_reply = self.tts.speak_stream(yielding_stream())
        if self.callbacks.ai_done:
            self.callbacks.ai_done(full_reply)
        return full_reply

    def _emit_status(self, status: str) -> None:
        if self.callbacks.status:
            self.callbacks.status(status)

    def _emit_partial(self, text: str) -> None:
        if self.callbacks.partial_text:
            self.callbacks.partial_text(text)
