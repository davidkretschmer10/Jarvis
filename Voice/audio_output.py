from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np


LOGGER = logging.getLogger(__name__)


@dataclass
class PlaybackItem:
    audio: np.ndarray
    sample_rate: int
    volume: float = 1.0


class AudioOutput:
    def __init__(self, device: Optional[int | str] = None):
        self.device = device
        self._queue: "queue.Queue[Optional[PlaybackItem]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def play(self, audio: np.ndarray, sample_rate: int, volume: float = 1.0) -> None:
        if len(audio):
            self._queue.put(PlaybackItem(audio.astype("float32"), int(sample_rate), float(volume)))

    def stop(self) -> None:
        self._stop_event.set()
        try:
            import sounddevice as sd

            sd.stop()
        except Exception as exc:
            LOGGER.debug("Audio stop failed: %s", exc)
        self.clear()
        self._stop_event.clear()

    def clear(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        self._queue.put(None)

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                if self._stop_event.is_set():
                    continue
                self._play_now(item)
            except Exception as exc:
                LOGGER.warning("Audio playback failed: %s", exc)
            finally:
                self._queue.task_done()

    def _play_now(self, item: PlaybackItem) -> None:
        import sounddevice as sd

        start = time.perf_counter()
        audio = item.audio
        if item.volume != 1.0:
            audio = np.clip(audio * item.volume, -1.0, 1.0)

        if item.sample_rate <= 0 or not len(audio):
            return

        if self.device is not None:
            old_device = sd.default.device
            try:
                sd.default.device = (old_device[0], self.device)
                sd.play(audio, samplerate=item.sample_rate)
                sd.wait()
            finally:
                sd.default.device = old_device
        else:
            sd.play(audio, samplerate=item.sample_rate)
            sd.wait()
        LOGGER.info("Playback latency %.3fs", time.perf_counter() - start)
