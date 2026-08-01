from __future__ import annotations

import logging
import os
import struct
import threading
from typing import Callable, Optional

from Voice.utils.config import VoiceConfig


LOGGER = logging.getLogger(__name__)


class PorcupineWakeWordEngine:
    """Offline Porcupine wake word listener for 'jarvis'."""

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    def start(self, callback: Callable[[], None]) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, args=(callback,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self, callback: Callable[[], None]) -> None:
        try:
            import pvporcupine
            import sounddevice as sd
        except Exception as exc:
            LOGGER.warning("Porcupine wake word unavailable: %s", exc)
            return

        porcupine = None
        stream = None
        try:
            access_key = self.config.porcupine_access_key or os.getenv("PICOVOICE_ACCESS_KEY")
            kwargs = {
                "keywords": [self.config.wake_word],
                "sensitivities": [float(self.config.wake_word_sensitivity)],
            }
            if access_key:
                kwargs["access_key"] = access_key
            porcupine = pvporcupine.create(
                **kwargs,
            )
            self._running.set()
            stream = sd.RawInputStream(
                samplerate=porcupine.sample_rate,
                blocksize=porcupine.frame_length,
                dtype="int16",
                channels=1,
                device=self.config.microphone_device,
            )
            stream.start()
            LOGGER.info("Wake word listening for '%s'", self.config.wake_word)

            while not self._stop_event.is_set():
                pcm = stream.read(porcupine.frame_length)[0]
                frame = struct.unpack_from("h" * porcupine.frame_length, pcm)
                keyword_index = porcupine.process(frame)
                if keyword_index >= 0:
                    callback()
        except Exception as exc:
            LOGGER.warning("Wake word listener stopped with error: %s", exc)
        finally:
            self._running.clear()
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            if porcupine is not None:
                porcupine.delete()
