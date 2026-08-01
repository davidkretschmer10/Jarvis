from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
from scipy.signal import butter, lfilter

from Voice.audio.vad import VoiceActivityDetector
from Voice.utils.config import VoiceConfig


LOGGER = logging.getLogger(__name__)


AudioCallback = Callable[[np.ndarray, int], None]
VolumeCallback = Callable[[int], None]


@dataclass
class RecordingResult:
    audio: np.ndarray
    sample_rate: int
    duration: float
    stopped_by_silence: bool


def normalize_audio(audio: np.ndarray, peak: float = 0.95) -> np.ndarray:
    max_value = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if max_value < 1e-6:
        return audio
    return np.clip(audio / max_value * peak, -1.0, 1.0)


def _filter_audio(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    if not len(audio):
        return audio
    nyq = 0.5 * sample_rate
    hp_b, hp_a = butter(3, 80 / nyq, btype="high", analog=False)
    lp_b, lp_a = butter(4, 3600 / nyq, btype="low", analog=False)
    return lfilter(lp_b, lp_a, lfilter(hp_b, hp_a, audio))


class AudioCapture:
    """Thread-safe microphone capture with queue-based frames and silence stop."""

    def __init__(self, config: VoiceConfig):
        self.config = config
        self.sample_rate = int(config.sample_rate)
        self.chunk_ms = int(config.chunk_ms)
        self.blocksize = max(160, int(self.sample_rate * self.chunk_ms / 1000))
        self.frames: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream = None
        self._lock = threading.Lock()
        self._recording = threading.Event()
        self._vad = VoiceActivityDetector(self.sample_rate, config.vad_aggressiveness)

    @property
    def is_recording(self) -> bool:
        return self._recording.is_set()

    def start(self, volume_callback: Optional[VolumeCallback] = None, frame_callback: Optional[AudioCallback] = None) -> None:
        import sounddevice as sd

        with self._lock:
            self.stop()
            while not self.frames.empty():
                try:
                    self.frames.get_nowait()
                except queue.Empty:
                    break
            self._recording.set()

            def callback(indata, frames, time_info, status):
                if status:
                    LOGGER.debug("Audio input status: %s", status)
                if not self._recording.is_set():
                    return
                audio = np.asarray(indata, dtype="float32").reshape(-1)
                audio = audio - np.mean(audio)
                audio = np.tanh(np.clip(audio * 1.2, -1.0, 1.0))
                result = self._vad.analyze_float32(audio)
                if volume_callback:
                    volume_callback(result.volume)
                self.frames.put(audio.copy())
                if frame_callback:
                    frame_callback(audio.copy(), self.sample_rate)

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self.blocksize,
                device=self.config.microphone_device,
                callback=callback,
            )
            self._stream.start()

    def stop(self) -> None:
        self._recording.clear()
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                LOGGER.warning("Could not close audio stream: %s", exc)

    def record_until_silence(self, volume_callback: Optional[VolumeCallback] = None) -> RecordingResult:
        self.start(volume_callback=volume_callback)
        chunks: list[np.ndarray] = []
        start = time.time()
        last_speech = None
        speech_started = False
        stopped_by_silence = False
        
        # Max duration to wait for the user to start speaking
        speech_start_timeout = 4.0

        try:
            while self.is_recording:
                now = time.time()
                if now - start >= self.config.max_record_seconds:
                    break

                try:
                    chunk = self.frames.get(timeout=0.1)
                except queue.Empty:
                    continue

                chunks.append(chunk)
                vad = self._vad.analyze_float32(chunk)
                
                if vad.is_speech:
                    if not speech_started:
                        LOGGER.debug("VAD: Detekován začátek řeči")
                        speech_started = True
                    last_speech = now
                else:
                    if not speech_started:
                        # If user hasn't started speaking yet, check start timeout
                        if now - start >= speech_start_timeout:
                            LOGGER.debug("VAD: Vypršel limit pro začátek řeči")
                            break
                    else:
                        # Once speech has started, check silence timeout
                        if now - start >= self.config.min_record_seconds and now - last_speech >= self.config.silence_timeout:
                            LOGGER.debug("VAD: Detekováno ticho, nahrávání dokončeno")
                            stopped_by_silence = True
                            break
        finally:
            self.stop()

        audio = np.concatenate(chunks) if chunks else np.array([], dtype="float32")
        audio = normalize_audio(_filter_audio(audio.astype("float32"), self.sample_rate))
        return RecordingResult(
            audio=audio,
            sample_rate=self.sample_rate,
            duration=time.time() - start,
            stopped_by_silence=stopped_by_silence,
        )
