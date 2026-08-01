from __future__ import annotations

from typing import Callable, Optional

from Voice.voice_manager import get_voice_manager


def start_recording(volume_callback: Optional[Callable[[int], None]] = None) -> None:
    get_voice_manager().start_recording(volume_callback)


def stop_recording() -> None:
    get_voice_manager().stop_recording()


def speech_to_text() -> str:
    return get_voice_manager().speech_to_text()


def listen_once_to_text(volume_callback: Optional[Callable[[int], None]] = None) -> str:
    return get_voice_manager().listen_once_to_text(volume_callback)


def speak(text: str) -> None:
    get_voice_manager().speak(text)


def speak_stream(chunks) -> str:
    return get_voice_manager().speak_stream(chunks)


def interrupt_speech() -> None:
    get_voice_manager().interrupt_speech()


def wake_listener(callback: Callable[[], None]) -> None:
    get_voice_manager().wake_listener(callback)


def stop_wake_listener() -> None:
    get_voice_manager().stop_wake_listener()


def get_voice_config():
    return get_voice_manager().config
