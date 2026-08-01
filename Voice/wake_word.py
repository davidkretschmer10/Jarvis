from __future__ import annotations

import logging
from typing import Callable, Optional

from Voice.config import VoiceConfig


LOGGER = logging.getLogger(__name__)


class WakeWord:
    """Local wake-word placeholder.

    The new voice stack keeps wake-word integration isolated and disabled by
    default because this project must not depend on cloud enrollment or API
    keys. A future local open model can implement the same start/stop surface.
    """

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._callback: Optional[Callable[[], None]] = None
        self._running = False

    def start(self, callback: Callable[[], None]) -> None:
        self._callback = callback
        self._running = True
        LOGGER.info("Wake word prepared but disabled; local backend not configured.")

    def stop(self) -> None:
        self._running = False
        self._callback = None
