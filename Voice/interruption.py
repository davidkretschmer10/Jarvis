from __future__ import annotations

import logging
import threading
from typing import Callable


LOGGER = logging.getLogger(__name__)


class InterruptionController:
    def __init__(self, interrupt_callback: Callable[[], None]):
        self._interrupt_callback = interrupt_callback
        self._enabled = True
        self._speaking = threading.Event()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def mark_speaking(self, speaking: bool) -> None:
        if speaking:
            self._speaking.set()
        else:
            self._speaking.clear()

    def on_user_speech(self) -> None:
        if self._enabled and self._speaking.is_set():
            LOGGER.info("Interrupt detected")
            self._interrupt_callback()
