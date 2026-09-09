from __future__ import annotations

# Compatibility wrapper for Voice.audio.audio_capture
from Voice.microphone import (
    AudioCallback,
    Microphone as AudioCapture,
    RecordingResult,
    VolumeCallback,
    filter_audio,
    normalize_audio,
    reduce_noise,
)

__all__ = [
    "AudioCapture",
    "RecordingResult",
    "AudioCallback",
    "VolumeCallback",
    "normalize_audio",
    "reduce_noise",
    "filter_audio",
]
