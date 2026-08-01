from __future__ import annotations

import time
import inspect
import threading
import subprocess
import requests

from ai.routing.model_registry import MODEL_SPECIALTIES
from ai.routing.fallback_manager import FALLBACK_MAP
from ai.routing.keyword_classifier import classify_by_keywords
from ai.routing.routing_result import RoutingResult

# Cache for installed models tags
_installed_models_cache: set[str] = set()
_last_cache_time = 0.0
_downloading_vision = False


def get_installed_models(force_refresh: bool = False) -> set[str]:
    global _installed_models_cache, _last_cache_time
    now = time.time()
    
    if not force_refresh and _installed_models_cache and (now - _last_cache_time < 8.0):
        return _installed_models_cache
        
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            models_list = response.json().get("models", [])
            installed = {m["name"].split(":")[0] for m in models_list}
            _installed_models_cache = installed
            _last_cache_time = now
            return installed
    except Exception as e:
        print(f"[ROUTER] Warning: failed to fetch installed tags: {e}")
        
    return _installed_models_cache or {"llama3"}


def is_voice_active_via_caller() -> bool:
    # Inspect stack to check if request originated from voice loops/handlers
    for frame_info in inspect.stack():
        if frame_info.function in ("handle_voice_text", "handle_wake_capture", "voice_conversation_loop"):
            return True
    return False


def start_background_pull_vision() -> None:
    global _downloading_vision
    if _downloading_vision:
        return
    _downloading_vision = True
    
    def pull_task():
        global _downloading_vision
        print("[ROUTER] Background pull of 'qwen2.5-vl' started...")
        try:
            subprocess.run(["ollama", "pull", "qwen2.5-vl"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[ROUTER] Background pull of 'qwen2.5-vl' completed successfully!")
        except Exception as e:
            print(f"[ROUTER] Background pull of 'qwen2.5-vl' failed: {e}")
        finally:
            _downloading_vision = False
            
    threading.Thread(target=pull_task, daemon=True).start()


def route_task(prompt: str, force_model: str | None = None) -> RoutingResult:
    # 1. Check if model is explicitly forced via UI selector
    if force_model and force_model != "auto":
        print(f"[ROUTER] Bypassing classification. Forced model: {force_model}")
        return RoutingResult(
            task_type="forced",
            recommended_model=force_model,
            confidence=1.0,
            reason=f"Forced via user settings: {force_model}"
        )

    # 2. Check if query is voice-driven
    if is_voice_active_via_caller():
        print("[ROUTER] Voice caller detected. Routing to gemma (voice expert).")
        res = RoutingResult(
            task_type="voice",
            recommended_model="gemma",
            confidence=1.0,
            reason="Voice caller context detection"
        )
    else:
        # Perform instant keyword classification
        task_type = classify_by_keywords(prompt)
        
        # Map task to model
        model_map = {
            "coding": "deepseek-coder",
            "planning": "mistral",
            "vision": "qwen2.5-vl",
            "agent": "qwen",
            "fast": "phi3",
            "general": "llama3"
        }
        recommended_model = model_map.get(task_type, "llama3")
        
        res = RoutingResult(
            task_type=task_type,
            recommended_model=recommended_model,
            confidence=1.0,
            reason="keyword match"
        )

    # 3. Dynamic verification and lazy loading / fallback redirection
    installed = get_installed_models()
    original_model = res.recommended_model
    
    if original_model not in installed:
        fallback = FALLBACK_MAP.get(original_model, "llama3")
        res.is_fallback = True
        res.original_model = original_model
        res.recommended_model = fallback
        
        # Trigger lazy pull for vision model qwen2.5-vl
        if original_model == "qwen2.5-vl":
            print("[ROUTER] Vision model 'qwen2.5-vl' is missing. Triggering background lazy pull.")
            start_background_pull_vision()
            
        print(f"[ROUTER] Fallback triggered: '{original_model}' is not installed. Redirecting to '{fallback}'.")
    
    # Standard Logging Output
    print("[ROUTER]")
    print(f"Task: {res.task_type}")
    print(f"Selected: {res.recommended_model}")
    print(f"Reason: {res.reason}")
    print(f"Fallback: {FALLBACK_MAP.get(res.recommended_model, 'None')}")
    
    return res
