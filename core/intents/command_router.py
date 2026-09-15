# -*- coding: utf-8 -*-
import json
import urllib.parse
from core.intents.intent_types import IntentType
from core.intents.parsed_command import ParsedCommand
from core.intents.target_extractor import normalize_text
from ai.engine import send_agent_command


def build_search_url(target: str, original_text: str = "") -> str:
    target_lower = target.lower().strip()
    orig_lower = original_text.lower().strip()
    
    known_sites = {
        "youtube": "https://www.youtube.com/",
        "chatgpt": "https://chatgpt.com/",
        "google": "https://www.google.com/",
        "wikipedia": "https://cs.wikipedia.org/",
        "seznam": "https://www.seznam.cz/",
        "facebook": "https://www.facebook.com/",
        "github": "https://github.com/",
        "spotify": "https://open.spotify.com/"
    }
    
    import re
    import unicodedata
    
    def strip_accents(text: str) -> str:
        text_norm = unicodedata.normalize("NFD", text)
        return "".join(c for c in text_norm if unicodedata.category(c) != "Mn")
        
    orig_clean = strip_accents(orig_lower)
    
    # Check direct base openings without query
    if orig_clean in ("otevri google", "otevri seznam", "otevri youtube", "google", "seznam", "youtube"):
        if "google" in orig_clean:
            return known_sites["google"]
        elif "seznam" in orig_clean:
            return known_sites["seznam"]
        elif "youtube" in orig_clean:
            return known_sites["youtube"]
            
    # Check specific search regex patterns
    google_match = re.search(r"otevri\s+google\s+a\s+vyhledej\s+(.*)", orig_clean)
    if google_match:
        query = google_match.group(1).strip()
        return f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        
    youtube_match = re.search(r"otevri\s+youtube\s+a\s+vyhledej\s+(.*)", orig_clean)
    if youtube_match:
        query = youtube_match.group(1).strip()
        return f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        
    seznam_match = re.search(r"otevri\s+seznam\s+a\s+vyhledej\s+(.*)", orig_clean)
    if seznam_match:
        query = seznam_match.group(1).strip()
        return f"https://search.seznam.cz/?q={urllib.parse.quote(query)}"
        
    # Also support "vyhledej na google/youtube/seznam [query]"
    google_match2 = re.search(r"vyhledej\s+na\s+googlu?\s+(.*)", orig_clean)
    if google_match2:
        query = google_match2.group(1).strip()
        return f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        
    youtube_match2 = re.search(r"vyhledej\s+na\s+youtube?\s+(.*)", orig_clean)
    if youtube_match2:
        query = youtube_match2.group(1).strip()
        return f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        
    seznam_match2 = re.search(r"vyhledej\s+na\s+seznamu?\s+(.*)", orig_clean)
    if seznam_match2:
        query = seznam_match2.group(1).strip()
        return f"https://search.seznam.cz/?q={urllib.parse.quote(query)}"

    # Original logic fallbacks
    if target_lower in known_sites:
        return known_sites[target_lower]
        
    if target_lower.startswith("wikipedia "):
        query = target[len("wikipedia"):].strip()
        return f"https://cs.wikipedia.org/w/index.php?search={urllib.parse.quote(query)}"
    if target_lower.startswith("wikipedie "):
        query = target[len("wikipedie"):].strip()
        return f"https://cs.wikipedia.org/w/index.php?search={urllib.parse.quote(query)}"
    if target_lower.startswith("wikipedii "):
        query = target[len("wikipedii"):].strip()
        return f"https://cs.wikipedia.org/w/index.php?search={urllib.parse.quote(query)}"
    if target_lower.startswith("youtube "):
        query = target[len("youtube"):].strip()
        return f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
    if target_lower.startswith("spotify "):
        query = target[len("spotify"):].strip()
        return f"https://open.spotify.com/search/{urllib.parse.quote(query)}"
        
    if "wikipedia" in orig_lower or "wikipedie" in orig_lower or "wikipedii" in orig_lower:
        return f"https://cs.wikipedia.org/w/index.php?search={urllib.parse.quote(target)}"
        
    if "youtube" in orig_lower:
        return f"https://www.youtube.com/results?search_query={urllib.parse.quote(target)}"
        
    if "spotify" in orig_lower:
        return f"https://open.spotify.com/search/{urllib.parse.quote(target)}"
        
    return f"https://www.google.com/search?q={urllib.parse.quote(target)}"


def execute_control_pc(original_text: str, target: str) -> str:
    """
    Routes PC control commands through the unified JarvisRuntime pipeline.
    """
    from core.runtime import JarvisRuntime
    goal = original_text.strip() or f"control pc {target}".strip()
    runtime = JarvisRuntime()
    result = runtime.run_task(goal)
    return result.summary


def execute_vision() -> str:
    """
    Routes screen reading through the unified JarvisRuntime pipeline.
    """
    from core.runtime import JarvisRuntime
    runtime = JarvisRuntime()
    result = runtime.run_task("Přečti obrazovku a popiš co na ní vidíš")
    return result.summary


def route_and_execute_command(parsed: ParsedCommand) -> str:
    """
    Routes the parsed command through the unified JarvisRuntime pipeline.
    Preserved as a thin compatibility wrapper for legacy callers.
    """
    from core.runtime import JarvisRuntime

    goal = parsed.original_text if parsed and getattr(parsed, "original_text", None) else ""
    if not goal and parsed and getattr(parsed, "intent", None):
        target = getattr(parsed, "target", "")
        goal = f"{parsed.intent.value} {target}".strip()

    if not goal:
        return "Omlouvám se, ale neuvedl jsi cíl příkazu."

    runtime = JarvisRuntime()
    result = runtime.run_task(goal)
    return result.summary

