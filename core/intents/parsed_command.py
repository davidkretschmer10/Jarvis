from dataclasses import dataclass
from core.intents.intent_types import IntentType


@dataclass
class ParsedCommand:
    intent: IntentType
    target: str = ""
    original_text: str = ""
    confidence: float = 1.0
    requires_llm: bool = False
