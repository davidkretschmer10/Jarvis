import sys

from Voice.voice_manager import VoiceManager, get_voice_manager

sys.modules.setdefault("voice", sys.modules[__name__])

__all__ = ["VoiceManager", "get_voice_manager"]
