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
    lower = original_text.lower().strip()
    import unicodedata
    normalized = unicodedata.normalize("NFKD", lower)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    
    if normalized.startswith("klikni"):
        send_agent_command("click")
        return "Kliknuto."
        
    if normalized.startswith(("screenshot", "snimek obrazovky")):
        res = send_agent_command("screenshot")
        try:
            data = json.loads(res)
            if isinstance(data, dict) and "result" in data:
                res_val = data["result"]
                if isinstance(res_val, dict):
                    path = res_val.get("path")
                    return f"Snímek obrazovky byl uložen do: {path}"
        except Exception:
            pass
        return "Snímek obrazovky byl pořízen."
        
    if normalized.startswith(("prepni", "dalsi", "dalsi skladbu")):
        send_agent_command("press", "nexttrack")
        return "Přepnuto na další skladbu."
        
    if normalized.startswith(("zastav", "pauzni", "stopni", "pauza")):
        send_agent_command("press", "playpause")
        return "Přehrávání pozastaveno/spuštěno."
        
    if normalized.startswith(("predchozi", "vrat", "vratit")):
        send_agent_command("press", "prevtrack")
        return "Přepnuto na předchozí skladbu."
        
    if normalized.startswith(("stiskni", "zmackni")):
        if not target:
            return "Omlouvám se, ale neuvedl jsi, kterou klávesu mám stisknout."
            
        target_norm = normalize_text(target)
        if target_norm.startswith("klavesu "):
            target = target[len("klavesu"):].strip()
            
        if "+" in target or " " in target:
            keys = [part.strip() for part in target.replace("+", " ").split() if part.strip()]
            send_agent_command("hotkey", keys)
            return f"Stisknuta klávesová zkratka: {' + '.join(keys).upper()}."
        else:
            send_agent_command("press", target)
            return f"Stisknuta klávesa {target.upper()}."
            
    return "Akce provedena."


def execute_vision() -> str:
    res = send_agent_command("read_screen")
    try:
        data = json.loads(res)
        if isinstance(data, dict) and "result" in data:
            result_val = data["result"]
            if isinstance(result_val, dict):
                text = result_val.get("text", "").strip()
            else:
                text = str(result_val).strip()
            if text:
                return f"Na obrazovce jsem přečetl:\n\n{text}"
            else:
                return "Na obrazovce se nepodařilo najít žádný čitelný text."
    except Exception:
        pass
    return "Nepodařilo se přečíst obrazovku."


def route_and_execute_command(parsed: ParsedCommand) -> str:
    """
    Routes the parsed command to the correct tool or falls back to LLM.
    Returns the string response to show in the GUI.
    """
    intent = parsed.intent
    target = parsed.target
    original_text = parsed.original_text
    
    print(f"\n[INTENT]\nDetected: {intent.value}")
    if target:
        print(f"[TARGET]\n{target}")
    
    if intent == IntentType.OPEN_APP:
        print("[TOOL]\nLaunching application...")
        if not target:
            return "Omlouvám se, ale neuvedl jsi název aplikace, kterou chceš otevřít."
            
        res_str = send_agent_command("open", target)
        
        is_ok = True
        result_text = res_str
        try:
            res_json = json.loads(res_str)
            if isinstance(res_json, dict):
                is_ok = res_json.get("ok", True)
                result_text = res_json.get("result", res_str)
        except Exception:
            pass
            
        if not is_ok or "error" in str(result_text).lower() or "failed" in str(result_text).lower():
            return f"Nepodařilo se najít aplikaci „{target}“."
            
        mapping = {
            "epic": "Epic Games Launcher",
            "chrome": "Google Chrome",
            "discord": "Discord",
            "steam": "Steam",
            "blender": "Blender",
            "vscode": "Visual Studio Code"
        }
        app_name = mapping.get(target.lower(), target.capitalize())
        return f"{app_name} je otevřený."
        
    elif intent == IntentType.SEARCH_WEB:
        print("[TOOL]\nOpening browser search...")
        if not target:
            return "Omlouvám se, ale neuvedl jsi, co mám vyhledat."
            
        url = build_search_url(target, original_text)
        send_agent_command("website", url)
        
        target_lower = target.lower().strip()
        orig_lower = original_text.lower().strip()
        if "youtube" in orig_lower:
            return "Otevírám YouTube v prohlížeči."
        elif "chatgpt" in orig_lower:
            return "Otevírám ChatGPT v prohlížeči."
        elif "wikipedia" in orig_lower or "wikipedie" in orig_lower or "wikipedii" in orig_lower:
            return f"Vyhledávám „{target}“ na Wikipedii v prohlížeči."
        return f"Vyhledávám „{target}“ v prohlížeči."
        
    elif intent == IntentType.CONTROL_PC:
        print("[TOOL]\nExecuting PC control action...")
        return execute_control_pc(original_text, target)
        
    elif intent == IntentType.VISION:
        print("[TOOL]\nReading screen OCR...")
        return execute_vision()
        
    elif intent in (IntentType.CREATE_FILE, IntentType.CREATE_PRESENTATION):
        parsed.requires_llm = True
        return ""
        
    return ""
