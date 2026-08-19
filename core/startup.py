from __future__ import annotations

import subprocess
import sys
import threading
import time

import requests

from ai.engine import ensure_models, start_ollama


_startup_lock = threading.Lock()
_ollama_initialized = False
_agent_started = False


def ensure_ai_engine_started(load_models: bool = True) -> None:
    global _ollama_initialized
    with _startup_lock:
        if _ollama_initialized:
            return
        start_ollama()
        if load_models:
            ensure_models()
        _ollama_initialized = True


def ensure_pc_agent_started(agent_url: str = "http://127.0.0.1:5000") -> None:
    global _agent_started
    with _startup_lock:
        if _agent_started or _agent_health_ok(agent_url):
            _agent_started = True
            return

        subprocess.Popen(
            [sys.executable, "-m", "core.agent"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        _agent_started = True


def _agent_health_ok(agent_url: str) -> bool:
    try:
        res = requests.get(f"{agent_url.rstrip('/')}/health", timeout=2)
        return res.ok
    except Exception:
        return False
