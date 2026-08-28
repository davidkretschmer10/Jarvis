import json
import os

from core.services.application_resolver import get_default_appdata_path

SETTINGS_FILE = get_default_appdata_path("jarvis_settings.json")
DATA_DIR = os.path.dirname(SETTINGS_FILE)

DEFAULT_SETTINGS = {
    "mode": "auto",
    "response_mode": "balanced",
    "personality": "jarvis",
    "enabled_models": ["llama3", "mistral", "phi3", "gemma", "qwen", "deepseek-coder"],
}

GENERAL_MODEL_PRIORITY = ["llama3", "mistral", "phi3", "qwen", "gemma", "deepseek-coder"]


def load_settings():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=4, ensure_ascii=False)
        return DEFAULT_SETTINGS

    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        settings = json.load(f)
    merged = DEFAULT_SETTINGS.copy()
    merged.update(settings)
    return merged


def save_settings(settings):
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)


# Feature toggle for stable single-brain assistant mode
CORE_ASSISTANT_MODE = True


def select_model(prompt, settings, chat_model=None):
    if chat_model and chat_model != "auto":
        return chat_model

    mode = settings.get("mode", "auto")
    if mode == "programming":
        return "deepseek-coder"
    if mode == "creative":
        return "gemma"
    if mode == "logic":
        return "mistral"
    if mode == "planning":
        return "qwen"

    if CORE_ASSISTANT_MODE:
        # Route explicitly to qwen2.5-vl if vision keywords are matched, otherwise default to llama3
        from ai.routing.keyword_classifier import strip_diacritics
        from ai.routing.routing_rules import KEYWORDS_VISION
        text = strip_diacritics(prompt.lower().strip())
        if any(strip_diacritics(kw.lower()) in text for kw in KEYWORDS_VISION):
            return "qwen2.5-vl"
        return "llama3"

    # Delegate dynamic auto-routing to the intelligent classification router
    from ai.routing.router import route_task
    res = route_task(prompt, chat_model)
    return res.recommended_model


