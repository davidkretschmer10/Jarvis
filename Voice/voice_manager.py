from __future__ import annotations

import logging
import os
import queue
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Optional

import numpy as np
import soundfile as sf

from Voice.audio_output import AudioOutput
from Voice.config import VoiceConfig, get_default_audio_dir, load_voice_config
from Voice.interruption import InterruptionController
from Voice.microphone import Microphone
from Voice.streaming import LatencyTimer
from Voice.tts_engine import BaseTTS, create_tts
from Voice.wake_word import WakeWord
from Voice.whisper_engine import TranscriptionResult, WhisperEngine


LOGGER = logging.getLogger(__name__)
VolumeCallback = Callable[[int], None]


class VoiceState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    STOPPING = "stopping"


class VoiceManager:
    """Thread-safe unified voice coordinator connecting audio capture, STT, TTS, and EventBus."""

    def __init__(self, config: Optional[VoiceConfig] = None, event_bus: Optional[Any] = None):
        self.config = config or load_voice_config()
        self.event_bus = event_bus
        self.microphone = Microphone(self.config)
        self.stt = WhisperEngine(self.config)
        self.audio_output = AudioOutput(self.config.speaker_device)
        self.tts: BaseTTS = create_tts(self.config, self.audio_output)
        self.wake_word = WakeWord(self.config)
        self.interruption = InterruptionController(self.interrupt_speech)
        self.interruption.set_enabled(self.config.interrupt_enabled)
        self._manual_chunks: "queue.Queue[np.ndarray]" = queue.Queue()
        self._record_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._state: VoiceState = VoiceState.STOPPED

    @property
    def state(self) -> VoiceState:
        with self._state_lock:
            return self._state

    def set_event_bus(self, event_bus: Any) -> None:
        self.event_bus = event_bus

    def _emit(self, event_name: str, data: Any = None) -> None:
        if self.event_bus is not None and hasattr(self.event_bus, "emit"):
            try:
                self.event_bus.emit(event_name, data)
            except Exception as exc:
                LOGGER.debug("Failed to emit event '%s': %s", event_name, exc)

    def _set_state(self, new_state: VoiceState, details: Optional[Dict[str, Any]] = None) -> None:
        with self._state_lock:
            if self._state == new_state and new_state != VoiceState.LISTENING:
                return
            prev_state = self._state
            self._state = new_state

        payload = {"state": new_state.value, "previous_state": prev_state.value}
        if details:
            payload.update(details)
        self._emit("voice_status_changed", payload)

        if new_state == VoiceState.LISTENING:
            self._emit("voice_listening", payload)
        elif new_state == VoiceState.TRANSCRIBING:
            self._emit("voice_transcribing", payload)
        elif new_state == VoiceState.PROCESSING:
            self._emit("voice_processing", payload)
        elif new_state == VoiceState.SPEAKING:
            self._emit("voice_speaking", payload)
        elif new_state == VoiceState.STOPPED:
            self._emit("voice_finished", payload)

    def set_stt_model(self, model_name: str) -> None:
        self.stt.set_model(model_name)

    def start_recording(self, volume_callback: Optional[VolumeCallback] = None) -> None:
        with self._record_lock:
            self._set_state(VoiceState.STARTING)
            self.interrupt_speech()
            self._clear_manual_chunks()

            def frame_callback(audio: np.ndarray, sample_rate: int) -> None:
                self._manual_chunks.put(audio)

            try:
                self.microphone.start(
                    volume_callback=volume_callback,
                    frame_callback=frame_callback,
                    speech_callback=self.interruption.on_user_speech,
                )
                self._set_state(VoiceState.LISTENING, {"mode": "manual"})
            except Exception as exc:
                LOGGER.warning("start_recording failed: %s", exc)
                self._set_state(VoiceState.STOPPED, {"error": str(exc)})
                self._emit("voice_error", {"error": str(exc), "stage": "start_recording"})
                raise

    def stop_recording(self) -> None:
        with self._record_lock:
            self.microphone.stop()
            if self.state == VoiceState.LISTENING:
                self._set_state(VoiceState.STOPPED)

    def speech_to_text(self, partial_callback: Optional[Callable[[str], None]] = None) -> str:
        with self._record_lock:
            self.stop_recording()
            chunks = []
            while not self._manual_chunks.empty():
                try:
                    chunks.append(self._manual_chunks.get_nowait())
                    self._manual_chunks.task_done()
                except queue.Empty:
                    break
            if not chunks:
                self._set_state(VoiceState.STOPPED)
                return ""

            audio = np.concatenate(chunks).astype("float32")
            if len(audio) < int(self.config.min_record_seconds * self.config.sample_rate):
                self._set_state(VoiceState.STOPPED)
                return ""

            self._set_state(VoiceState.TRANSCRIBING)
            self._save_recording(audio, self.config.sample_rate)

            try:
                result = self.stt.transcribe_audio(audio, self.config.sample_rate, partial_callback)
                text = result.text.strip()
                self._emit("voice_transcribed", {"text": text, "duration": result.duration})
                return text
            except Exception as exc:
                LOGGER.warning("STT transcription failed: %s", exc)
                self._emit("voice_error", {"error": str(exc), "stage": "speech_to_text"})
                return ""
            finally:
                self._set_state(VoiceState.STOPPED)

    def listen_once_to_text(
        self,
        volume_callback: Optional[VolumeCallback] = None,
        partial_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        with self._record_lock:
            self._set_state(VoiceState.LISTENING, {"mode": "listen_once"})
            try:
                recording = self.microphone.record_until_silence(
                    volume_callback=volume_callback,
                    speech_callback=self.interruption.on_user_speech,
                )
                if len(recording.audio) < int(self.config.min_record_seconds * recording.sample_rate):
                    self._set_state(VoiceState.STOPPED)
                    return ""

                self._set_state(VoiceState.TRANSCRIBING)
                self._save_recording(recording.audio, recording.sample_rate)
                result = self.stt.transcribe_recording(recording, partial_callback=partial_callback)
                text = result.text.strip()
                self._emit("voice_transcribed", {"text": text, "duration": result.duration})
                return text
            except Exception as exc:
                LOGGER.warning("Voice listen/transcribe failed: %s", exc)
                self._emit("voice_error", {"error": str(exc), "stage": "listen_once_to_text"})
                return ""
            finally:
                self._set_state(VoiceState.STOPPED)

    def transcribe_recording(self, audio: np.ndarray, sample_rate: int) -> TranscriptionResult:
        self._set_state(VoiceState.TRANSCRIBING)
        try:
            return self.stt.transcribe_audio(audio, sample_rate)
        finally:
            self._set_state(VoiceState.STOPPED)

    def speak(self, text: str) -> None:
        if not text or not self.config.enabled:
            return
        self._set_state(VoiceState.SPEAKING, {"text": text})
        try:
            self.interruption.mark_speaking(True)
            self.tts.speak(text)
        except Exception as exc:
            LOGGER.warning("Voice speak failed: %s", exc)
            self._emit("voice_error", {"error": str(exc), "stage": "speak"})
        finally:
            self._set_state(VoiceState.STOPPED)

    def speak_stream(self, chunks: Iterable[str]) -> str:
        if not self.config.enabled:
            return "".join(chunks)
        self._set_state(VoiceState.SPEAKING, {"streaming": True})
        try:
            self.interruption.mark_speaking(True)
            return self.tts.speak_stream(chunks)
        except Exception as exc:
            LOGGER.warning("Voice speak_stream failed: %s", exc)
            self._emit("voice_error", {"error": str(exc), "stage": "speak_stream"})
            return ""
        finally:
            self._set_state(VoiceState.STOPPED)

    def stream_llm_to_tts(
        self,
        chunks: Iterable[str],
        chunk_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        timer = LatencyTimer()

        def yielding_stream():
            for chunk in chunks:
                if chunk_callback:
                    try:
                        chunk_callback(chunk)
                    except Exception as exc:
                        LOGGER.debug("Error in chunk_callback: %s", exc)
                yield chunk

        full = self.speak_stream(yielding_stream())
        LOGGER.info("LLM latency %.3fs", timer.elapsed())
        return full

    def interrupt_speech(self) -> None:
        self.tts.interrupt()
        self.interruption.mark_speaking(False)
        self._emit("voice_interrupted", {})
        if self.state == VoiceState.SPEAKING:
            self._set_state(VoiceState.STOPPED)

    def wake_listener(self, callback: Callable[[], None]) -> None:
        self.wake_word.start(callback)

    def stop_wake_listener(self) -> None:
        self.wake_word.stop()

    def shutdown(self) -> None:
        self._set_state(VoiceState.STOPPING)
        self.stop_wake_listener()
        self.microphone.stop()
        self.tts.shutdown()
        self.audio_output.shutdown()
        self._set_state(VoiceState.STOPPED)

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
            target_dir = self.config.recordings_dir
            if not target_dir or target_dir == "Voice":
                target_dir = get_default_audio_dir()
            os.makedirs(target_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            path = os.path.join(target_dir, f"user_voice_{timestamp}.wav")
            sf.write(path, audio, sample_rate)
        except Exception as exc:
            LOGGER.debug("Could not save voice recording to AppData: %s", exc)


_manager: Optional[VoiceManager] = None
_manager_lock = threading.RLock()


def get_voice_manager(event_bus: Optional[Any] = None) -> VoiceManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = VoiceManager(event_bus=event_bus)
        elif event_bus is not None and _manager.event_bus is None:
            _manager.set_event_bus(event_bus)
        return _manager


def reset_voice_manager() -> None:
    """Reset global voice manager instance (used for testing or reconfiguration)."""
    global _manager
    with _manager_lock:
        if _manager is not None:
            try:
                _manager.shutdown()
            except Exception:
                pass
            _manager = None
