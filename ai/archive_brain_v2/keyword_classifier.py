from __future__ import annotations

import unicodedata
from ai.routing.routing_rules import (
    KEYWORDS_CODING,
    KEYWORDS_PLANNING,
    KEYWORDS_VISION,
    KEYWORDS_AGENT
)


def strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def classify_by_keywords(prompt: str) -> str:
    text = strip_diacritics(prompt.lower().strip())
    
    # Check vision
    for keyword in KEYWORDS_VISION:
        cleaned_kw = strip_diacritics(keyword.lower())
        if cleaned_kw in text:
            return "vision"
            
    # Check coding
    for keyword in KEYWORDS_CODING:
        cleaned_kw = strip_diacritics(keyword.lower())
        if cleaned_kw in text:
            return "coding"
            
    # Check planning
    for keyword in KEYWORDS_PLANNING:
        cleaned_kw = strip_diacritics(keyword.lower())
        if cleaned_kw in text:
            return "planning"
            
    # Check agent
    for keyword in KEYWORDS_AGENT:
        cleaned_kw = strip_diacritics(keyword.lower())
        if cleaned_kw in text:
            return "agent"
            
    return "general"
