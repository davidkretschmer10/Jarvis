from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


LOGGER = logging.getLogger(__name__)


@dataclass
class VoiceConfig:
    microphone_device: Optional[int | str] = None
    speaker_device: Optional[int | str] = None
    wake_word: str = "jarvis"
    porcupine_access_key: Optional[str] = None
    wake_word_sensitivity: float = 0.65
    silence_timeout: float = 1.1
    max_record_seconds: float = 20.0
    min_record_seconds: float = 0.35
    whisper_model: str = "large-v3-turbo"
    whisper_fallback_model: str = "small"
    whisper_language: str = "cs"
    whisper_device: str = "auto"
    whisper_compute_type: str = "float16"
    vad_aggressiveness: int = 2
    sample_rate: int = 16000
    chunk_ms: int = 30
    partial_transcription_seconds: float = 1.5
    tts_voice: str = "cs_CZ-jirka-medium.onnx"
    tts_rate: float = 0.92
    tts_pitch: int = -2
    tts_volume: float = 1.0
    tts_sentence_pause: float = 0.12
    tts_max_chunk_chars: int = 180
    tts_ai_style: bool = True
    realtime_mode: bool = True
    save_recordings: bool = True
    recordings_dir: str = "Voice"


DEFAULT_CONFIG_PATH = os.path.join("settings", "voice_config.json")


def load_voice_config(path: str = DEFAULT_CONFIG_PATH) -> VoiceConfig:
    config = VoiceConfig()
    if not os.path.exists(path):
        save_voice_config(config, path)
        return config

    try:
        with open(path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
    except Exception as exc:
        LOGGER.warning("Could not load voice config %s: %s", path, exc)
        return config

    known = asdict(config)
    known.update({key: value for key, value in data.items() if key in known})
    return VoiceConfig(**known)


def save_voice_config(config: VoiceConfig, path: str = DEFAULT_CONFIG_PATH) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2, ensure_ascii=False)
