from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
from scipy.signal import butter, lfilter

from Voice.config import VoiceConfig
from Voice.vad import VoiceActivityDetector


LOGGER = logging.getLogger(__name__)
AudioCallback = Callable[[np.ndarray, int], None]
VolumeCallback = Callable[[int], None]
SpeechCallback = Callable[[], None]


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


def reduce_noise(audio: np.ndarray, sample_rate: int, enabled: bool) -> np.ndarray:
    if not enabled or not len(audio):
        return audio
    try:
        import noisereduce as nr

        return np.asarray(nr.reduce_noise(y=audio, sr=sample_rate), dtype="float32")
    except Exception as exc:
        LOGGER.debug("Noise reduction skipped: %s", exc)
        return audio


def filter_audio(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    if not len(audio):
        return audio
    nyq = 0.5 * sample_rate
    hp_b, hp_a = butter(3, 80 / nyq, btype="high", analog=False)
    lp_b, lp_a = butter(4, 3600 / nyq, btype="low", analog=False)
    return lfilter(lp_b, lp_a, lfilter(hp_b, hp_a, audio)).astype("float32")


class Microphone:
    def __init__(self, config: VoiceConfig):
        self.config = config
        self.sample_rate = int(config.sample_rate)
        self.chunk_ms = int(config.chunk_ms)
        self.blocksize = max(160, int(self.sample_rate * self.chunk_ms / 1000))
        self.frames: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream = None
        self._lock = threading.RLock()
        self._recording = threading.Event()
        self._vad = VoiceActivityDetector(
            self.sample_rate,
            config.vad_aggressiveness,
            config.vad_rms_threshold,
            config.vad_enabled,
        )

    @property
    def is_recording(self) -> bool:
        return self._recording.is_set()

    def clear(self) -> None:
        while not self.frames.empty():
            try:
                self.frames.get_nowait()
                self.frames.task_done()
            except queue.Empty:
                break

    def start(
        self,
        volume_callback: Optional[VolumeCallback] = None,
        frame_callback: Optional[AudioCallback] = None,
        speech_callback: Optional[SpeechCallback] = None,
    ) -> None:
        import sounddevice as sd

        with self._lock:
            self.stop()
            self.clear()
            self._recording.set()
            speech_seen = False

            def callback(indata, frames, time_info, status):
                nonlocal speech_seen
                if status:
                    LOGGER.debug("Audio input status: %s", status)
                if not self._recording.is_set():
                    return
                audio = np.asarray(indata, dtype="float32").reshape(-1)
                audio = audio - np.mean(audio)
                vad = self._vad.analyze_float32(audio)
                if vad.is_speech and not speech_seen:
                    speech_seen = True
                    LOGGER.info("Speech start")
                    if speech_callback:
                        speech_callback()
                if volume_callback:
                    volume_callback(vad.volume)
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

    def record_until_silence(
        self,
        volume_callback: Optional[VolumeCallback] = None,
        speech_callback: Optional[SpeechCallback] = None,
    ) -> RecordingResult:
        self.start(volume_callback=volume_callback, speech_callback=speech_callback)
        chunks: list[np.ndarray] = []
        start = time.perf_counter()
        last_speech: Optional[float] = None
        speech_started = False
        stopped_by_silence = False

        LOGGER.info("VAD start")
        try:
            while self.is_recording:
                now = time.perf_counter()
                if now - start >= self.config.max_record_seconds:
                    break
                try:
                    chunk = self.frames.get(timeout=0.1)
                except queue.Empty:
                    continue

                vad = self._vad.analyze_float32(chunk)
                if vad.is_speech or speech_started:
                    chunks.append(chunk)

                if vad.is_speech:
                    speech_started = True
                    last_speech = now
                elif not speech_started and now - start >= self.config.speech_start_timeout:
                    break
                elif speech_started and last_speech is not None:
                    if now - start >= self.config.min_record_seconds and now - last_speech >= self.config.silence_timeout:
                        stopped_by_silence = True
                        break
        finally:
            self.stop()
            LOGGER.info("VAD stop")

        audio = np.concatenate(chunks) if chunks else np.array([], dtype="float32")
        audio = filter_audio(audio.astype("float32"), self.sample_rate)
        audio = reduce_noise(audio, self.sample_rate, self.config.noise_reduction)
        audio = normalize_audio(audio)
        if speech_started:
            LOGGER.info("Speech end")
        return RecordingResult(audio, self.sample_rate, time.perf_counter() - start, stopped_by_silence)
