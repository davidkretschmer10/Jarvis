from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = os.path.join("settings", "voice_config.json")


@dataclass
class VoiceConfig:
    enabled: bool = True
    stt_model: str = "large-v3-turbo"
    stt_fallback_model: str = "small"
    tts_backend: str = "piper"
    language: str = "cs"
    sample_rate: int = 16000
    device: Optional[int | str] = None
    input_device: Optional[int | str] = None
    output_device: Optional[int | str] = None
    vad_enabled: bool = True
    vad_aggressiveness: int = 2
    vad_rms_threshold: float = 0.012
    streaming_enabled: bool = True
    interrupt_enabled: bool = True
    noise_reduction: bool = True
    volume: float = 1.0
    speed: float = 0.92
    pitch: int = -2
    chunk_ms: int = 30
    silence_timeout: float = 1.1
    speech_start_timeout: float = 4.0
    max_record_seconds: float = 20.0
    min_record_seconds: float = 0.35
    partial_transcription_seconds: float = 1.5
    whisper_device: str = "auto"
    whisper_compute_type: str = "float16"
    piper_voice: str = "cs_CZ-jirka-medium.onnx"
    tts_sentence_pause: float = 0.12
    tts_max_chunk_chars: int = 180
    tts_ai_style: bool = True
    save_recordings: bool = True
    recordings_dir: str = "Voice"
    wake_word: str = "jarvis"
    wake_word_enabled: bool = False

    @property
    def microphone_device(self) -> Optional[int | str]:
        return self.input_device if self.input_device is not None else self.device

    @property
    def speaker_device(self) -> Optional[int | str]:
        return self.output_device


_LEGACY_KEYS = {
    "microphone_device": "input_device",
    "speaker_device": "output_device",
    "whisper_model": "stt_model",
    "whisper_fallback_model": "stt_fallback_model",
    "whisper_language": "language",
    "tts_voice": "piper_voice",
    "tts_rate": "speed",
    "tts_pitch": "pitch",
    "tts_volume": "volume",
    "realtime_mode": "streaming_enabled",
}


def _flatten_voice_section(data: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(data.get("voice"), dict):
        merged = dict(data)
        voice_data = merged.pop("voice")
        merged.update(voice_data)
        return merged
    return data


def _normalize_config_data(data: Dict[str, Any]) -> Dict[str, Any]:
    data = _flatten_voice_section(data)
    normalized: Dict[str, Any] = {}
    for key, value in data.items():
        normalized[_LEGACY_KEYS.get(key, key)] = value
    return normalized


def load_voice_config(path: str = DEFAULT_CONFIG_PATH) -> VoiceConfig:
    config = VoiceConfig()
    if not os.path.exists(path):
        save_voice_config(config, path)
        return config

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _normalize_config_data(json.load(f))
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
        json.dump({"voice": asdict(config)}, f, indent=2, ensure_ascii=False)
