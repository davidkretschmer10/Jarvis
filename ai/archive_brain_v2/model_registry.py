from __future__ import annotations

MODEL_SPECIALTIES = {
    "deepseek-coder": "coding",
    "mistral": "planning",
    "qwen2.5-vl": "vision",
    "gemma": "voice",
    "qwen": "agent",
    "phi3": "fast",
    "llama3": "general"
}

SUPPORTED_MODELS = list(MODEL_SPECIALTIES.keys())
