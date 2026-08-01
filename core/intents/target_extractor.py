# -*- coding: utf-8 -*-
import re
import unicodedata


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def strip_greetings(text: str) -> str:
    normalized = normalize_text(text)
    prefixes = [
        "jarvis", "jarvisi", "ahoj", "cau", "dobry den", "prosim", "prosim te", "hej jarvis", "ok jarvis"
    ]
    suffixes = [
        "prosim", "prosim te", "jarvis", "jarvisi"
    ]
    changed = True
    while changed:
        changed = False
        normalized_stripped = normalized.strip()
        for p in prefixes:
            if normalized_stripped.startswith(p):
                # Check if it matches with word boundary or punctuation
                rem = normalized_stripped[len(p):].lstrip(" ,.-!?")
                normalized = rem
                changed = True
                break
        
        normalized_stripped = normalized.strip()
        for s in suffixes:
            if normalized_stripped.endswith(s):
                rem = normalized_stripped[:-len(s)].rstrip(" ,.-!?")
                normalized = rem
                changed = True
                break
    return normalized


def extract_target(original_text: str, matched_alias: str) -> str:
    """
    Extracts the target parameter from original_text based on the matched_alias.
    E.g. original_text = "Zapni Epic Launcher", matched_alias = "zapni" -> "Epic Launcher"
    """
    cleaned = strip_greetings(original_text)
    norm_alias = normalize_text(matched_alias)
    
    # Locate where the alias is in the cleaned string
    # We want to match it and keep the original casing of the remaining text if possible
    # But since cleaned is already normalized, let's also find the original casing version
    orig_cleaned = original_text.strip()
    
    # We can match alias normalized against normalized target and do slice on orig_cleaned
    # To keep original casing (e.g. "Epic Games" instead of "epic games"):
    norm_cleaned = normalize_text(orig_cleaned)
    
    if norm_cleaned.startswith(norm_alias):
        # Slice original cleaned to preserve case
        target = orig_cleaned[len(norm_alias):].strip()
    else:
        # Fallback to normalized cleaned version if match starts somewhere else
        if cleaned.startswith(norm_alias):
            target = cleaned[len(norm_alias):].strip()
        else:
            target = cleaned

    # Strip helper words/prepositions from the end of the target
    # e.g., 'karluv most na wikipedii' -> 'karluv most'
    changed = True
    while changed:
        changed = False
        target_norm = normalize_text(target)
        trail_helpers = ["na internetu", "v prohlizeci", "na webu", "na vebu", "v chrome"]
        for th in trail_helpers:
            if target_norm.endswith(th):
                target = target[:-len(th)].strip()
                changed = True
                break

    # Strip helper prepositions/words from the beginning of the target
    # e.g., 'najdi na internetu wikipedia' -> alias = 'najdi' -> target = 'na internetu wikipedia' -> 'wikipedia'
    helpers = [
        "na internetu", "na webu", "na vebu", "v prohlizeci", "v chrome", "v chromu",
        "chromu", "chrome", "wikipedii na tema", "wikipedie na tema", "wikipedia na tema",
        "wikipedii", "wikipedie", "wikipedia", "youtube", "spotify", "na tema", "tema",
        "mi", "v", "na", "o", "pro", "se", "stranku", "web", "internet", "prohlizec", "internetu", "webu"
    ]
    
    site_names = {
        "chrome", "chromu", "youtube", "spotify", "wikipedia", "wikipedie", "wikipedii"
    }
    
    changed = True
    while changed:
        changed = False
        target_norm = normalize_text(target)
        for h in helpers:
            if target_norm.startswith(h + " "):
                target = target[len(h):].strip()
                changed = True
                break
            elif target_norm == h:
                if h not in site_names:
                    target = ""
                    changed = True
                    break

    # Clean up punctuation and whitespace
    target = re.sub(r"^[\s\-:,\"']+", "", target)
    target = re.sub(r"[\s\-:,\"']+$", "", target)
    return target.strip()
