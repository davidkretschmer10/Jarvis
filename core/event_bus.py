# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional


class EventBus:
    """Thread-safe event bus for inter-component communication and lifecycle events."""

    def __init__(self) -> None:
        self.listeners: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock = threading.RLock()

    def on(self, event_name: str, handler: Callable[[Any], None]) -> None:
        with self._lock:
            if event_name not in self.listeners:
                self.listeners[event_name] = []
            self.listeners[event_name].append(handler)

    def off(self, event_name: str, handler: Optional[Callable[[Any], None]] = None) -> None:
        with self._lock:
            if event_name in self.listeners:
                if handler is None:
                    del self.listeners[event_name]
                else:
                    self.listeners[event_name] = [h for h in self.listeners[event_name] if h != handler]

    def emit(self, event_name: str, data: Any = None) -> None:
        handlers: List[Callable[[Any], None]] = []
        with self._lock:
            if event_name in self.listeners:
                handlers = list(self.listeners[event_name])

        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                print(f"EventBus error in handler for '{event_name}': {e}")
                if event_name != "error":
                    self.emit("error", f"Error in {event_name}: {str(e)}")

    def emit_lifecycle(self, event_name: str, request_id: str, **kwargs: Any) -> None:
        payload = {
            "event": event_name,
            "request_id": request_id,
            "timestamp": time.time(),
        }
        payload.update(kwargs)
        self.emit(event_name, payload)
