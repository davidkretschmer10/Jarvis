from __future__ import annotations

from ai.prompts.language_rules import build_language_instruction, build_language_rules
from ai.prompts.response_style import build_response_style_rules


def build_merge_prompt(responses: list[str], user_text: str | None = None) -> str:
    parts = [
        "Jsi merge vrstva asistenta Jarvis.",
        build_language_rules(),
        build_language_instruction(user_text),
        build_response_style_rules(),
        (
            "UKOL:\n"
            "- Zkombinuj odpovedi modelu do jedne nejlepsi odpovedi.\n"
            "- Vysledek musi byt v jazyce posledni zpravy uzivatele; kdyz je jazyk nejasny, pouzij cestinu.\n"
            "- Odstran anglicke zacatky a generic ChatGPT fraze.\n"
            "- Odstran duplicity, oprav chyby a zachovej jen spravne informace.\n"
            "- Zachovej strucnost. Nepridavej omacky."
        ),
    ]
    for index, response in enumerate(responses, start=1):
        parts.append(f"--- ODPOVED {index} ---\n{response}")
    return "\n\n".join(parts)
