import concurrent.futures
import json
import subprocess
import sys
import time
from typing import Any, Optional
import uuid
import threading

from core.lifecycle import (
    InvalidStateTransitionError,
    RequestContext,
    RequestStatus,
    cancel_current_request,
    check_request_context_block,
    complete_current_request,
    fail_current_request,
    get_current_request,
    get_current_request_or_none,
    reset_current_request,
    set_current_request,
)

import requests
from requests.adapters import HTTPAdapter

from ai.model_manager import load_settings, select_model
from ai.prompts.language_rules import build_language_instruction
from ai.prompts.master_prompt import build_master_prompt
from ai.prompts.merge_prompt import build_merge_prompt
from ai.prompts.response_style import sanitize_response_text, sanitize_stream_start

_ollama_session = None
_ollama_status = {
    "running": False,
    "active_model": None,
    "downloading_model": None,
    "error": None,
}


def _update_ollama_status(**updates: Any) -> None:
    _ollama_status.update(updates)


def get_ollama_status() -> dict[str, Any]:
    running = check_ollama_health()
    router = sys.modules.get("ai.routing.router")
    if router is not None and getattr(router, "_downloading_vision", False):
        _update_ollama_status(downloading_model="qwen2.5-vl")
    elif _ollama_status.get("downloading_model") == "qwen2.5-vl":
        _update_ollama_status(downloading_model=None)
    status = dict(_ollama_status)
    status["running"] = running
    return status

def get_ollama_session():
    global _ollama_session
    if _ollama_session is None:
        _ollama_session = requests.Session()
        # Keep up to 10 HTTP connections open to enable Keep-Alive pooling
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        _ollama_session.mount("http://", adapter)
        _ollama_session.mount("https://", adapter)
    return _ollama_session


def check_ollama_health():
    try:
        session = get_ollama_session()
        res = session.get("http://localhost:11434/api/tags", timeout=5)
        ok = res.status_code == 200
        _update_ollama_status(running=ok, error=None if ok else f"HTTP {res.status_code}")
        return ok
    except Exception as e:
        print(f"[OLLAMA] Health check failed: {e}")
        _update_ollama_status(running=False, error=str(e))
        return False


def _post_with_retry(url, json, stream=False, max_retries=3, initial_delay=1.0):
    session = get_ollama_session()
    delay = initial_delay
    last_exception = None
    
    for attempt in range(1, max_retries + 1):
        start_t = time.time()
        try:
            # Connect timeout: 30s, Read timeout: 300s
            response = session.post(
                url,
                json=json,
                stream=stream,
                timeout=(30, 300)
            )
            if response.status_code == 200:
                return response
            else:
                print(f"[OLLAMA] Attempt {attempt}/{max_retries} failed with status: {response.status_code} in {time.time() - start_t:.2f}s")
                last_exception = requests.RequestException(f"Ollama returned HTTP status {response.status_code}")
        except Exception as e:
            print(f"[OLLAMA] Attempt {attempt}/{max_retries} exception in {time.time() - start_t:.2f}s: {e}")
            last_exception = e
            
        if attempt < max_retries:
            print(f"[OLLAMA] Retrying in {delay:.1f}s (exponential backoff)...")
            time.sleep(delay)
            delay *= 2.0
            
    if last_exception:
        raise last_exception
    raise requests.RequestException("Max retries reached without success.")


experts = {
    "general": "llama3",
    "coding": "deepseek-coder",
    "logic": "mistral",
    "analysis": "phi3",
    "creative": "gemma",
    "planner": "qwen",
}


def send_agent_command(action, value=""):
    try:
        print(f"[DEBUG] Sending command: {action} -> {value}")
        response = requests.post(
            "http://127.0.0.1:5000/command",
            json={"action": action, "value": value},
            timeout=5,
        )
        print(f"[DEBUG] Response status: {response.status_code}")
        print(f"[DEBUG] Response text: {response.text}")
        return response.text
    except Exception as e:
        print(f"[ERROR] Agent call failed: {e}")
        return "ERROR"


def start_ollama():
    try:
        session = get_ollama_session()
        session.get("http://localhost:11434", timeout=5)
        _update_ollama_status(running=True, error=None)
        return
    except Exception:
        pass

    try:
        _update_ollama_status(running=False, error="Starting Ollama")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
        check_ollama_health()
    except Exception as e:
        print(f"Ollama start failed: {e}")
        _update_ollama_status(running=False, error=str(e))


def ensure_models():
    # Only pull llama3 at startup.
    models = ["llama3"]
    try:
        session = get_ollama_session()
        response = session.get("http://localhost:11434/api/tags", timeout=5)
        installed_models = [m["name"].split(":")[0] for m in response.json().get("models", [])]
    except Exception as e:
        print(f"Error checking models: {e}")
        installed_models = []

    for model in models:
        if model.split(":")[0] not in installed_models:
            print("Downloading model:", model)
            try:
                _update_ollama_status(downloading_model=model, error=None)
                subprocess.run(["ollama", "pull", model])
                _update_ollama_status(downloading_model=None, error=None)
            except Exception as e:
                print(f"Error pulling {model}: {e}")
                _update_ollama_status(downloading_model=None, error=str(e))



# Feature toggle for stable single-brain assistant mode
CORE_ASSISTANT_MODE = True

# Debug toggle for streaming mode
USE_STREAMING = True

# Centralized locked system prompt
SYSTEM_PROMPT_LOCK = """Jsi Jarvis.
Lokální AI assistant pro Windows.

Mluv česky pokud uživatel píše česky.

Buď:
- stručný,
- přirozený,
- technický,
- užitečný.

Nikdy nepoužívej:
- “As an AI language model”
- “I apologize”
- korporátní chatbot fráze.

Když nevíš:
řekni to jednoduše.

Nehalucinuj."""


def ask_model(model, prompt):
    _update_ollama_status(active_model=model)
    if not check_ollama_health():
        return ""
        
    url = "http://localhost:11434/api/generate"
    try:
        response = _post_with_retry(
            url,
            json={"model": model, "prompt": prompt, "stream": False},
            stream=False
        )
        return sanitize_response_text(response.json()["response"])
    except Exception as e:
        print(f"[ENGINE] Model error ({model}): {e}")

    if CORE_ASSISTANT_MODE:
        if model != "llama3":
            print(f"[ENGINE] Core fallback triggered: {model} -> llama3")
            try:
                response = _post_with_retry(
                    url,
                    json={"model": "llama3", "prompt": prompt, "stream": False},
                    stream=False
                )
                return sanitize_response_text(response.json()["response"])
            except Exception as ex:
                print(f"[ENGINE] Core fallback failed: {ex}")
                _update_ollama_status(error=str(ex))
        return ""
    else:
        # Fallback to Llama3/Fallback registry
        from ai.routing.fallback_manager import FALLBACK_MAP
        fb = FALLBACK_MAP.get(model)
        if fb:
            print(f"[ENGINE] Direct fallback triggered: {model} -> {fb}")
            try:
                response = _post_with_retry(
                    url,
                    json={"model": fb, "prompt": prompt, "stream": False},
                    stream=False
                )
                return sanitize_response_text(response.json()["response"])
            except Exception as e:
                print(f"[ENGINE] Fallback model error ({fb}): {e}")
                
        return ""


def _system_prompt(personality="jarvis"):
    # Lock system prompt for all expert models
    return SYSTEM_PROMPT_LOCK


def _latest_user_text(prompt):
    marker = "UZIVATEL:\n"
    if marker in prompt:
        return prompt.rsplit(marker, 1)[1].strip()
    return prompt


def _language_instruction(prompt):
    return "\n\n" + build_language_instruction(_latest_user_text(prompt))


def _compose_prompt(prompt, personality="jarvis"):
    return _system_prompt(personality=personality) + _language_instruction(prompt) + "\n\n" + prompt


def check_request_context_block() -> bool:
    req = get_current_request()
    if req.completed or req.cancelled or req.failed:
        reason = "completed" if req.completed else ("cancelled" if req.cancelled else "failed")
        print(f"[ENGINE]\nAI generation skipped\n\nReason:\nrequest already {reason}\n\nRequest state:\ncompleted={req.completed}\ncancelled={req.cancelled}\nfailed={req.failed}\n")
        return True
    return False


def ask_multi_agent(prompt, chat_model=None):
    if check_request_context_block():
        return ""
    settings = load_settings()
    user_text = _latest_user_text(prompt)
    full_prompt = _compose_prompt(prompt, personality=settings.get("personality", "jarvis"))
    
    # Jarvis runs exclusively on llama3 in this version
    model_to_use = "llama3"
    _update_ollama_status(active_model=model_to_use)
    return ask_model(model_to_use, full_prompt)


def ask_ai(prompt, chat_model=None):
    if check_request_context_block():
        return ""
    return ask_multi_agent(prompt, chat_model)


def _execute_ollama_request(model, prompt):
    """
    Executes a request to Ollama (streaming or non-streaming).
    Yields response chunks and returns True on success, False on failure.
    If streaming fails mid-way, falls back automatically to non-streaming POST
    and yields the suffix cleanly.
    """
    start_time = time.time()
    print(f"[OLLAMA] Request started for model '{model}'")
    _update_ollama_status(active_model=model, error=None)
    accumulated = ""
    
    # 1. Health check guard
    if not check_ollama_health():
        print(f"[OLLAMA] Health check failed before request.")
        return False

    url = "http://localhost:11434/api/generate"
    
    if USE_STREAMING:
        # A. Streaming Mode
        print("[OLLAMA] Entering stream mode...")
        try:
            response = _post_with_retry(
                url,
                json={"model": model, "prompt": prompt, "stream": True},
                stream=True
            )
            first_chunk = True
            
            # Read from stream line-by-line
            try:
                for line in response.iter_lines():
                    if line:
                        # Robust UTF-8 decoding
                        if isinstance(line, bytes):
                            line_str = line.decode('utf-8', errors='replace')
                        else:
                            line_str = line
                        
                        # Robust JSON parsing
                        try:
                            data = json.loads(line_str)
                        except json.JSONDecodeError as je:
                            print(f"[OLLAMA] JSON decode error on chunk: {je}")
                            continue
                            
                        chunk = data.get("response", "")
                        if chunk:
                            if first_chunk:
                                first_token_time = time.time() - start_time
                                print(f"[OLLAMA] First token received: {first_token_time:.2f} sec")
                                chunk = sanitize_stream_start(chunk)
                                first_chunk = False
                            
                            accumulated += chunk
                            yield chunk
                            
                duration = time.time() - start_time
                print(f"[OLLAMA] Stream completed in {duration:.2f} sec")
                return True
                
            except Exception as stream_err:
                print(f"[OLLAMA] Stream failed mid-way: {stream_err}. Triggering non-streaming fallback...")
                # Fall through to non-streaming fallback recovery below
        except Exception as conn_err:
            print(f"[OLLAMA] Stream connection failed: {conn_err}. Triggering non-streaming fallback...")
            # Fall through to non-streaming fallback recovery below
            
        # B. Fallback recovery: non-streaming request
        print("[OLLAMA] Executing non-streaming fallback recovery...")
        fallback_start = time.time()
        try:
            response = _post_with_retry(
                url,
                json={"model": model, "prompt": prompt, "stream": False},
                stream=False
            )
            data = response.json()
            full_text = data.get("response", "")
            full_text = sanitize_response_text(full_text)
            
            # Calculate suffix to avoid duplicating already yielded text
            suffix = ""
            if full_text.startswith(accumulated):
                suffix = full_text[len(accumulated):]
            else:
                # Fallback to character-by-character common prefix check
                common_prefix_len = 0
                for i in range(min(len(accumulated), len(full_text))):
                    if accumulated[i] == full_text[i]:
                        common_prefix_len += 1
                    else:
                        break
                if common_prefix_len > 0:
                    suffix = full_text[common_prefix_len:]
                else:
                    # No common prefix match, just yield a newline and full text to be safe
                    suffix = "\n" + full_text
            
            duration = time.time() - start_time
            print(f"[OLLAMA] Non-streaming fallback completed in {time.time() - fallback_start:.2f}s. Total time: {duration:.2f}s")
            if suffix:
                yield suffix
            return True
        except Exception as fb_err:
            print(f"[OLLAMA] Non-streaming fallback failed: {fb_err}")
            return False
            
    else:
        # C. Non-Streaming Mode
        print("[OLLAMA] Entering non-streaming mode...")
        try:
            response = _post_with_retry(
                url,
                json={"model": model, "prompt": prompt, "stream": False},
                stream=False
            )
            data = response.json()
            full_text = data.get("response", "")
            full_text = sanitize_response_text(full_text)
            
            duration = time.time() - start_time
            print(f"[OLLAMA] Non-streaming request completed in {duration:.2f} sec")
            yield full_text
            return True
        except Exception as err:
            print(f"[OLLAMA] Non-streaming request failed: {err}")
            return False


def raw_stream_with_fallback(model, stream_prompt):
    success = yield from _execute_ollama_request(model, stream_prompt)

    if not success:
        if CORE_ASSISTANT_MODE:
            if model != "llama3":
                print(f"[ENGINE] Core fallback triggered: {model} -> llama3")
                success = yield from _execute_ollama_request("llama3", stream_prompt)
            if not success:
                yield (
                    "\nJarvis se nedokázal spojit s Ollamou.\n"
                    "Zkontroluj:\n"
                    "- zda běží Ollama,\n"
                    "- zda je načtený model,\n"
                    "- nebo zda model neodpovídá příliš dlouho."
                )
        else:
            from ai.routing.fallback_manager import FALLBACK_MAP
            fb = FALLBACK_MAP.get(model, "llama3")
            print(f"[ENGINE] Dynamic streaming fallback triggered: {model} -> {fb}")
            success = yield from _execute_ollama_request(fb, stream_prompt)
            if not success:
                yield (
                    "\nJarvis se nedokázal spojit s Ollamou.\n"
                    "Zkontroluj:\n"
                    "- zda běží Ollama,\n"
                    "- zda je načtený model,\n"
                    "- nebo zda model neodpovídá příliš dlouho."
                )


def generate_stream(prompt, chat_model=None):
    if check_request_context_block():
        return
    settings = load_settings()
    user_text = _latest_user_text(prompt)
    full_prompt = _compose_prompt(prompt, personality=settings.get("personality", "jarvis"))
    
    model_to_use = "llama3"
    _update_ollama_status(active_model=model_to_use)
    print(f"[ENGINE] Core assistant mode active. Selected model: {model_to_use}")
    yield from raw_stream_with_fallback(model_to_use, full_prompt)
