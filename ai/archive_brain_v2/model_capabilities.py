from __future__ import annotations

# Centralized registry of model specialties
MODEL_CAPABILITIES = {
    "llama3": ["general", "chat", "everyday_tasks", "assistant_conversation"],
    "gemma": ["voice", "overlay_mode", "voice_assistant", "low_latency"],
    "deepseek-coder": ["coding", "python", "debugging", "refactor", "gui", "architecture", "automation"],
    "mistral": ["planning", "task_decomposition", "logic", "workflows", "tool_selection"],
    "qwen": ["agent", "autonomy", "next_step_reasoning", "observation_loop", "ui_reasoning", "state_analysis"],
    "qwen2.5-vl": ["vision", "screenshot_analysis", "ui_detection", "ocr_understanding", "multimodal_reasoning"],
    "phi3": ["fast", "lightweight", "quick_actions", "background_assistant"]
}

# Dynamic inference fallback map
FALLBACK_MAP = {
    "deepseek-coder": "llama3",
    "gemma": "phi3",
    "qwen": "mistral",
    "mistral": "qwen",
    "qwen2.5-vl": "qwen",
    "phi3": "llama3",
    "llama3": "phi3"
}

SUPPORTED_MODELS = list(MODEL_CAPABILITIES.keys())
