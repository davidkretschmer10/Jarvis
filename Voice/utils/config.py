from __future__ import annotations

# Compatibility wrapper for Voice.utils.config
from Voice.config import (
    DEFAULT_CONFIG_PATH,
    VoiceConfig,
    load_voice_config,
    save_voice_config,
)

__all__ = ["VoiceConfig", "load_voice_config", "save_voice_config", "DEFAULT_CONFIG_PATH"]
