from __future__ import annotations

from ai.prompts.language_rules import build_language_instruction, build_language_rules
from ai.prompts.personality import get_personality_profile
from ai.prompts.response_style import build_response_style_rules


def build_master_prompt(personality: str = "jarvis") -> str:
    profile = get_personality_profile(personality)
    return "\n\n".join(
        (
            profile.render(),
            build_language_rules(),
            build_response_style_rules(),
        )
    )


def build_user_task_prompt(
    user_text: str,
    history: list[str] | None = None,
    profile_facts: list[str] | None = None,
) -> str:
    history_text = "\n".join(history or [])
    profile_text = "\n".join(profile_facts or [])

    return (
        f"{build_language_instruction(user_text)}\n\n"
        "PROFIL UZIVATELE:\n"
        f"{profile_text or '- zadny ulozeny profil'}\n\n"
        "KONTEXT CHATU:\n"
        f"{history_text or '- bez predchoziho kontextu'}\n\n"
        "UZIVATEL:\n"
        f"{user_text}"
    )
