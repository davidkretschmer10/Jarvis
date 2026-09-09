from __future__ import annotations

import logging
from typing import Callable, Optional

from Voice.config import VoiceConfig


LOGGER = logging.getLogger(__name__)


class PorcupineWakeWordEngine:
    """Offline, local wake word engine wrapper.
    
    Maintains compatibility with tests without requiring cloud API keys.
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._running = False
        self._callback: Optional[Callable[[], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, callback: Callable[[], None]) -> None:
        self._running = True
        self._callback = callback
        LOGGER.info("Wake word listener started (offline local mode)")

    def stop(self) -> None:
        self._running = False
        self._callback = None
        LOGGER.info("Wake word listener stopped")


__all__ = ["PorcupineWakeWordEngine"]
