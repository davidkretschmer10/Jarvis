from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np


LOGGER = logging.getLogger(__name__)


class AudioPlayer:
    """Interruptible sounddevice playback wrapper."""

    def __init__(self, device: Optional[int | str] = None):
        self.device = device
        self._lock = threading.Lock()

    def play(self, audio: np.ndarray, sample_rate: int, volume: float = 1.0) -> None:
        import sounddevice as sd
        import time

        start_time = time.perf_counter()
        if volume != 1.0:
            audio = np.clip(audio * volume, -1.0, 1.0)
            
        with self._lock:
            latency = (time.perf_counter() - start_time) * 1000
            LOGGER.debug("Audio playback latency (lock wait + volume adjust): %.2f ms", latency)
            
            if self.device is not None:
                old_device = sd.default.device
                try:
                    sd.default.device = (old_device[0], self.device)
                    sd.play(audio, samplerate=sample_rate)
                    sd.wait()
                finally:
                    sd.default.device = old_device
            else:
                sd.play(audio, samplerate=sample_rate)
                sd.wait()

    def stop(self) -> None:
        try:
            import sounddevice as sd

            sd.stop()
        except Exception as exc:
            LOGGER.debug("Audio stop failed: %s", exc)
