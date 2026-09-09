from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


LOGGER = logging.getLogger(__name__)


def get_default_audio_dir() -> str:
    """Return standard AppData directory for voice recordings."""
    try:
        from core.services.application_resolver import ApplicationResolver
        return ApplicationResolver.get_default_appdata_path("audio")
    except Exception:
        appdata = os.getenv("APPDATA") or os.path.expanduser("~")
        return os.path.join(appdata, "Jarvis", "audio")


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
    save_recordings: bool = False
    recordings_dir: str = field(default_factory=get_default_audio_dir)
    wake_word: str = "jarvis"
    wake_word_enabled: bool = False
    _porcupine_access_key: Optional[str] = field(default=None, repr=False)
    _wake_word_sensitivity: float = field(default=0.65, repr=False)

    def __init__(
        self,
        enabled: bool = True,
        stt_model: str = "large-v3-turbo",
        stt_fallback_model: str = "small",
        tts_backend: str = "piper",
        language: str = "cs",
        sample_rate: int = 16000,
        device: Optional[int | str] = None,
        input_device: Optional[int | str] = None,
        output_device: Optional[int | str] = None,
        vad_enabled: bool = True,
        vad_aggressiveness: int = 2,
        vad_rms_threshold: float = 0.012,
        streaming_enabled: bool = True,
        interrupt_enabled: bool = True,
        noise_reduction: bool = True,
        volume: float = 1.0,
        speed: float = 0.92,
        pitch: int = -2,
        chunk_ms: int = 30,
        silence_timeout: float = 1.1,
        speech_start_timeout: float = 4.0,
        max_record_seconds: float = 20.0,
        min_record_seconds: float = 0.35,
        partial_transcription_seconds: float = 1.5,
        whisper_device: str = "auto",
        whisper_compute_type: str = "float16",
        piper_voice: str = "cs_CZ-jirka-medium.onnx",
        tts_sentence_pause: float = 0.12,
        tts_max_chunk_chars: int = 180,
        tts_ai_style: bool = True,
        save_recordings: bool = False,
        recordings_dir: Optional[str] = None,
        wake_word: str = "jarvis",
        wake_word_enabled: bool = False,
        **kwargs: Any,
    ):
        self.enabled = enabled
        self.stt_model = kwargs.get("whisper_model", stt_model)
        self.stt_fallback_model = kwargs.get("whisper_fallback_model", stt_fallback_model)
        self.tts_backend = tts_backend
        self.language = kwargs.get("whisper_language", language)
        self.sample_rate = sample_rate
        self.device = device
        self.input_device = kwargs.get("microphone_device", input_device)
        self.output_device = kwargs.get("speaker_device", output_device)
        self.vad_enabled = vad_enabled
        self.vad_aggressiveness = vad_aggressiveness
        self.vad_rms_threshold = vad_rms_threshold
        self.streaming_enabled = kwargs.get("realtime_mode", streaming_enabled)
        self.interrupt_enabled = interrupt_enabled
        self.noise_reduction = noise_reduction
        self.volume = kwargs.get("tts_volume", volume)
        self.speed = kwargs.get("tts_rate", speed)
        self.pitch = kwargs.get("tts_pitch", pitch)
        self.chunk_ms = chunk_ms
        self.silence_timeout = silence_timeout
        self.speech_start_timeout = speech_start_timeout
        self.max_record_seconds = max_record_seconds
        self.min_record_seconds = min_record_seconds
        self.partial_transcription_seconds = partial_transcription_seconds
        self.whisper_device = whisper_device
        self.whisper_compute_type = whisper_compute_type
        self.piper_voice = kwargs.get("tts_voice", piper_voice)
        self.tts_sentence_pause = tts_sentence_pause
        self.tts_max_chunk_chars = tts_max_chunk_chars
        self.tts_ai_style = tts_ai_style
        self.save_recordings = save_recordings
        # Safeguard: never let recordings_dir default to repository source directory
        if not recordings_dir or recordings_dir == "Voice":
            self.recordings_dir = get_default_audio_dir()
        else:
            self.recordings_dir = recordings_dir
        self.wake_word = wake_word
        self.wake_word_enabled = wake_word_enabled
        self._porcupine_access_key = kwargs.get("porcupine_access_key")
        self._wake_word_sensitivity = float(kwargs.get("wake_word_sensitivity", 0.65))

    @property
    def microphone_device(self) -> Optional[int | str]:
        return self.input_device if self.input_device is not None else self.device

    @microphone_device.setter
    def microphone_device(self, value: Optional[int | str]) -> None:
        self.input_device = value

    @property
    def speaker_device(self) -> Optional[int | str]:
        return self.output_device

    @speaker_device.setter
    def speaker_device(self, value: Optional[int | str]) -> None:
        self.output_device = value

    # --- Backward compatibility aliases ---
    @property
    def whisper_model(self) -> str:
        return self.stt_model

    @whisper_model.setter
    def whisper_model(self, value: str) -> None:
        self.stt_model = value

    @property
    def whisper_fallback_model(self) -> str:
        return self.stt_fallback_model

    @whisper_fallback_model.setter
    def whisper_fallback_model(self, value: str) -> None:
        self.stt_fallback_model = value

    @property
    def whisper_language(self) -> str:
        return self.language

    @whisper_language.setter
    def whisper_language(self, value: str) -> None:
        self.language = value

    @property
    def tts_voice(self) -> str:
        return self.piper_voice

    @tts_voice.setter
    def tts_voice(self, value: str) -> None:
        self.piper_voice = value

    @property
    def tts_rate(self) -> float:
        return self.speed

    @tts_rate.setter
    def tts_rate(self, value: float) -> None:
        self.speed = value

    @property
    def tts_pitch(self) -> int:
        return self.pitch

    @tts_pitch.setter
    def tts_pitch(self, value: int) -> None:
        self.pitch = value

    @property
    def tts_volume(self) -> float:
        return self.volume

    @tts_volume.setter
    def tts_volume(self, value: float) -> None:
        self.volume = value

    @property
    def realtime_mode(self) -> bool:
        return self.streaming_enabled

    @realtime_mode.setter
    def realtime_mode(self, value: bool) -> None:
        self.streaming_enabled = value

    @property
    def porcupine_access_key(self) -> Optional[str]:
        return self._porcupine_access_key

    @porcupine_access_key.setter
    def porcupine_access_key(self, value: Optional[str]) -> None:
        self._porcupine_access_key = value

    @property
    def wake_word_sensitivity(self) -> float:
        return self._wake_word_sensitivity

    @wake_word_sensitivity.setter
    def wake_word_sensitivity(self, value: float) -> None:
        self._wake_word_sensitivity = float(value)


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

    known_keys = {
        "enabled", "stt_model", "stt_fallback_model", "tts_backend", "language",
        "sample_rate", "device", "input_device", "output_device", "vad_enabled",
        "vad_aggressiveness", "vad_rms_threshold", "streaming_enabled", "interrupt_enabled",
        "noise_reduction", "volume", "speed", "pitch", "chunk_ms", "silence_timeout",
        "speech_start_timeout", "max_record_seconds", "min_record_seconds",
        "partial_transcription_seconds", "whisper_device", "whisper_compute_type",
        "piper_voice", "tts_sentence_pause", "tts_max_chunk_chars", "tts_ai_style",
        "save_recordings", "recordings_dir", "wake_word", "wake_word_enabled",
        "porcupine_access_key", "wake_word_sensitivity"
    }
    filtered = {k: v for k, v in data.items() if k in known_keys}
    return VoiceConfig(**filtered)


def save_voice_config(config: VoiceConfig, path: str = DEFAULT_CONFIG_PATH) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    raw_dict = asdict(config)
    # Remove internal underscore attributes from direct serialization
    raw_dict.pop("_porcupine_access_key", None)
    raw_dict.pop("_wake_word_sensitivity", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"voice": raw_dict}, f, indent=2, ensure_ascii=False)
