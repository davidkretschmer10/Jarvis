from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np


LOGGER = logging.getLogger(__name__)


@dataclass
class VADResult:
    is_speech: bool
    rms: float
    volume: int


class VoiceActivityDetector:
    """Frame-level VAD with WebRTC when available and an RMS fallback."""

    def __init__(self, sample_rate: int = 16000, aggressiveness: int = 2, rms_threshold: float = 0.012):
        self.sample_rate = sample_rate
        self.rms_threshold = rms_threshold
        self._webrtcvad = None
        try:
            import webrtcvad

            self._webrtcvad = webrtcvad.Vad(int(aggressiveness))
        except Exception as exc:
            LOGGER.info("webrtcvad unavailable, using RMS VAD fallback: %s", exc)

    def analyze_float32(self, audio: np.ndarray) -> VADResult:
        mono = np.asarray(audio, dtype="float32").flatten()
        rms = float(np.sqrt(np.mean(mono**2))) if len(mono) else 0.0
        volume = max(0, min(100, int(rms * 180)))
        is_speech = rms >= self.rms_threshold

        if self._webrtcvad is not None and len(mono):
            pcm = np.clip(mono, -1.0, 1.0)
            pcm16 = (pcm * 32767).astype(np.int16).tobytes()
            try:
                is_speech = bool(self._webrtcvad.is_speech(pcm16, self.sample_rate))
            except Exception:
                is_speech = rms >= self.rms_threshold

        return VADResult(is_speech=is_speech, rms=rms, volume=volume)
