# -*- coding: utf-8 -*-
import os
import json
from core.intents.intent_types import IntentType
from core.intents.parsed_command import ParsedCommand
from core.intents.target_extractor import normalize_text, strip_greetings, extract_target


def load_aliases():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(dir_path, "command_aliases.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load command aliases: {e}")
        return {}


def classify_intent(text: str) -> ParsedCommand:
    normalized_text = normalize_text(text)
    cleaned_text = strip_greetings(text)
    
    if not cleaned_text:
        return ParsedCommand(intent=IntentType.CHAT, original_text=text, confidence=1.0)
        
    aliases_dict = load_aliases()
    all_matches = []
    
    for intent_name, aliases in aliases_dict.items():
        try:
            intent_type = IntentType(intent_name)
        except ValueError:
            continue
            
        for alias in aliases:
            norm_alias = normalize_text(alias)
            # Match prefix with space or exact match to preserve word boundaries
            if cleaned_text == norm_alias or cleaned_text.startswith(norm_alias + " "):
                confidence = 0.95
                all_matches.append((intent_type, norm_alias, confidence))
            elif norm_alias in ["screenshot", "snimek obrazovky"] and norm_alias in cleaned_text:
                all_matches.append((intent_type, norm_alias, 0.9))
                
    if all_matches:
        # Sort matches by the length of the matched alias descending
        # to ensure that longer, more specific command patterns are prioritized
        all_matches.sort(key=lambda x: len(x[1]), reverse=True)
        best_intent, best_alias, conf = all_matches[0]
        
        # Heuristics adjustment:
        # If intent is OPEN_APP, but the query contains web targets, re-classify as SEARCH_WEB!
        web_targets = [
            "wikipedia", "wikipedie", "wikipedii", "youtube", "spotify", "google", "seznam", "internet", "web", "webu", "veb", "vebu"
        ]
        if best_intent == IntentType.OPEN_APP:
            if any(wt in normalized_text for wt in web_targets):
                # But NOT if they literally just want to open browser app itself
                if not (normalized_text.endswith("chrome") or normalized_text.endswith("chromu") or normalized_text.endswith("browser") or normalized_text.endswith("prohlizec")):
                    best_intent = IntentType.SEARCH_WEB
                    conf = 0.96
        
        target = extract_target(text, best_alias)
        
        # If intent is OPEN_APP or SEARCH_WEB but target is empty, check if we can reconstruct the target website
        if best_intent in (IntentType.OPEN_APP, IntentType.SEARCH_WEB) and not target:
            if best_intent == IntentType.SEARCH_WEB and any(wt in normalized_text for wt in ["youtube", "chatgpt", "wikipedia", "wikipedie", "wikipedii", "spotify", "google", "seznam"]):
                for wt in ["youtube", "chatgpt", "wikipedia", "spotify", "google", "seznam"]:
                    if wt in normalized_text:
                        target = wt
                        break
            else:
                return ParsedCommand(
                    intent=IntentType.CHAT,
                    original_text=text,
                    confidence=1.0,
                    requires_llm=False
                )
            
        return ParsedCommand(
            intent=best_intent,
            target=target,
            original_text=text,
            confidence=conf,
            requires_llm=False
        )
        
    return ParsedCommand(
        intent=IntentType.CHAT,
        original_text=text,
        confidence=1.0,
        requires_llm=False
    )
