from __future__ import annotations

import re

from ai.prompts.language_rules import FORBIDDEN_OPENERS


def build_response_style_rules() -> str:
    return (
        "STYL ODPOVEDI:\n"
        "- Odpovidej kratce, pokud uzivatel nechce detail.\n"
        "- Preferuj 1 az 4 vety pro bezne dotazy.\n"
        "- U technickych veci dej nejdriv vysledek, potom kratke vysvetleni.\n"
        "- Nepremlouvej a neomlouvej se zbytecne.\n"
        "- Nepouzivej vypln typu rad pomohu, samozrejme, urcite, omlouvam se.\n"
        "- Pro TTS pis kratsi vety a neroztahuj odstavce."
    )


def sanitize_response_text(text: str) -> str:
    out = str(text).strip()
    out = _remove_forbidden_opener(out)
    out = _replace_common_english_phrases(out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def sanitize_stream_start(text: str) -> str:
    return _remove_forbidden_opener(str(text))


def _remove_forbidden_opener(text: str) -> str:
    out = text.lstrip()
    for opener in FORBIDDEN_OPENERS:
        pattern = re.compile(rf"^{re.escape(opener)}[,.!:\-\s]*", re.IGNORECASE)
        out = pattern.sub("", out).lstrip()
    return out


def _replace_common_english_phrases(text: str) -> str:
    replacements = {
        r"\bI'm sorry,?\s*": "",
        r"\bI am sorry,?\s*": "",
        r"\bI'd be happy to\s*": "",
        r"\bCertainly,?\s*": "",
        r"\bSure,?\s*": "",
    }
    out = text
    for pattern, replacement in replacements.items():
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out
