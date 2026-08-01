from __future__ import annotations

import time
from typing import Callable, Iterable, Iterator, Optional


TextCallback = Callable[[str], None]


class ResponseStreamer:
    def __init__(self, chunk_callback: Optional[TextCallback] = None):
        self.chunk_callback = chunk_callback

    def stream(self, chunks: Iterable[str]) -> Iterator[str]:
        for chunk in chunks:
            if self.chunk_callback:
                self.chunk_callback(chunk)
            yield chunk


class LatencyTimer:
    def __init__(self) -> None:
        self.started = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self.started
