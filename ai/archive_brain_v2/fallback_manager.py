from __future__ import annotations

# Centralized fallback map. Llama3 is the main fallback brain.
FALLBACK_MAP = {
    "deepseek-coder": "llama3",
    "mistral": "llama3",
    "gemma": "llama3",
    "phi3": "llama3",
    "qwen": "llama3",
    "qwen2.5-vl": "llama3"
}
