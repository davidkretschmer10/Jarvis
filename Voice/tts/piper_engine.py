from __future__ import annotations

# Compatibility wrapper for Voice.tts.piper_engine
from Voice.tts_engine import (
    BaseTTS,
    PiperEngine,
    PiperTTS,
    split_for_tts,
    split_sentences,
)

__all__ = ["PiperEngine", "PiperTTS", "BaseTTS", "split_for_tts", "split_sentences"]
