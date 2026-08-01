# -*- coding: utf-8 -*-
import os
import json
import urllib.parse
import time
from typing import Any, Dict, List, Optional, Tuple

from core.intents.target_extractor import normalize_text, strip_greetings

# Known mappings for apps, websites, and actions
APP_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "blender": "blender",
    "vscode": "vscode",
    "steam": "steam",
    "epic": "epic games launcher",
    "epic games launcher": "epic games launcher",
    "kalkulacka": "calculator",
    "kalkulacku": "calculator",
    "calculator": "calculator",
    "calc": "calculator",
    "poznamkovy blok": "notepad",
    "notepad": "notepad",
}

WEBSITE_URLS = {
    "seznam": "https://www.seznam.cz",
    "seznam.cz": "https://www.seznam.cz",
    "google": "https://www.google.com",
    "google.com": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "youtube.com": "https://www.youtube.com",
}

def get_appdata_path(filename: str) -> str:
    appdata_dir = os.getenv("APPDATA")
    if not appdata_dir:
        appdata_dir = os.path.expanduser("~/.jarvis")
    else:
        appdata_dir = os.path.join(appdata_dir, "Jarvis")
    os.makedirs(appdata_dir, exist_ok=True)
    return os.path.join(appdata_dir, filename)

def load_user_preferences() -> Dict[str, str]:
    pref_file = get_appdata_path("user_preferences.json")
    if os.path.exists(pref_file):
        try:
            with open(pref_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def save_user_preference(key: str, val: str) -> None:
    pref_file = get_appdata_path("user_preferences.json")
    prefs = load_user_preferences()
    prefs[key] = val
    try:
        with open(pref_file, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[ROUTER] Error saving user preference: {e}")

def load_apps_cache() -> Dict[str, str]:
    cache_file = get_appdata_path("apps_cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def is_ignored_app(name: str, path: str) -> bool:
    if not path:
        return False
    name_lower = name.lower()
    path_lower = path.lower()
    exe_name = os.path.basename(path_lower)
    
    ignored_keywords = ["epicwebhelper", "updater", "crash reporter", "crashreporter", "crash_reporter", "helper"]
    
    if any(kw in name_lower for kw in ignored_keywords):
        return True
    if any(kw in exe_name for kw in ignored_keywords):
        return True
    return False

def resolve_app_from_cache_with_score(query: str) -> Optional[Tuple[str, str, int]]:
    from utils.helpers import normalize_name
    query_norm = normalize_name(query)
    if not query_norm:
        return None

    # Map target using APP_ALIASES
    query_norm = APP_ALIASES.get(query_norm, query_norm)

    # 1. Check user preferences
    prefs = load_user_preferences()
    pref_path = prefs.get(query_norm)
    if pref_path and os.path.exists(pref_path):
        basename = os.path.splitext(os.path.basename(pref_path))[0]
        return basename, pref_path, 100

    # 2. Check apps cache
    cache = load_apps_cache()
    if not cache:
        from utils.helpers import scan_apps
        cache = scan_apps()
    
    # Filter helper apps
    cache = {k: v for k, v in cache.items() if not is_ignored_app(k, v)}
    
    candidates = []
    for app_name, path in cache.items():
        app_name_norm = normalize_name(app_name)
        app_name_canon = APP_ALIASES.get(app_name_norm, app_name_norm)
        
        score = 0
        if query_norm == app_name_canon:
            score = 100
        elif app_name_canon.startswith(query_norm):
            score = 80
        elif query_norm in app_name_canon:
            score = 70
        else:
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, query_norm, app_name_canon).ratio()
            if ratio >= 0.75:
                score = 60
                
        if score >= 60:
            candidates.append((score, app_name, path))
            
    if candidates:
        # Sort by score descending, then by name length ascending
        candidates.sort(key=lambda x: (-x[0], len(x[1])))
        best_score, best_name, best_path = candidates[0]
        return best_name, best_path, best_score

    return None

def increment_router_stat(
    level: str,
    elapsed_time: float = 0.0,
    fallback: bool = False,
    confirmation: bool = False,
    fallback_reason: Optional[str] = None
) -> None:
    stats_file = get_appdata_path("router_stats.json")
    stats = {
        "fast_command": 0,
        "mini_planner": 0,
        "planner_v2": 0,
        "avg_fast_time": 0.0,
        "avg_mini_time": 0.0,
        "avg_planner_time": 0.0,
        "fallbacks": 0,
        "confirmations": 0,
        "ollama_calls_prevented": 0,
        "requests_completed": 0,
        "requests_cancelled": 0,
        "requests_failed": 0,
        "fallback_log": []
    }
    
    if os.path.exists(stats_file):
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        if k in stats:
                            stats[k] = v
        except Exception:
            pass

    level_key = level.lower()
    if level_key in stats:
        stats[level_key] = stats.get(level_key, 0) + 1

    if level == "FAST_COMMAND":
        stats["ollama_calls_prevented"] = stats.get("ollama_calls_prevented", 0) + 1

    if level == "FAST_COMMAND" and elapsed_time > 0:
        prev_count = stats.get("fast_command", 1) - 1
        prev_avg = stats.get("avg_fast_time", 0.0)
        new_avg = ((prev_avg * prev_count) + elapsed_time) / (prev_count + 1)
        stats["avg_fast_time"] = round(new_avg, 3)
    elif level == "MINI_PLANNER" and elapsed_time > 0:
        prev_count = stats.get("mini_planner", 1) - 1
        prev_avg = stats.get("avg_mini_time", 0.0)
        new_avg = ((prev_avg * prev_count) + elapsed_time) / (prev_count + 1)
        stats["avg_mini_time"] = round(new_avg, 3)
    elif level == "PLANNER_V2" and elapsed_time > 0:
        prev_count = stats.get("planner_v2", 1) - 1
        prev_avg = stats.get("avg_planner_time", 0.0)
        new_avg = ((prev_avg * prev_count) + elapsed_time) / (prev_count + 1)
        stats["avg_planner_time"] = round(new_avg, 3)

    if fallback:
        stats["fallbacks"] = stats.get("fallbacks", 0) + 1
        if fallback_reason:
            log_entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "reason": fallback_reason
            }
            if "fallback_log" not in stats:
                stats["fallback_log"] = []
            stats["fallback_log"].append(log_entry)

    if confirmation:
        stats["confirmations"] = stats.get("confirmations", 0) + 1

    try:
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[ROUTER] Error saving router statistics: {e}")

def update_request_stat(status: str) -> None:
    stats_file = get_appdata_path("router_stats.json")
    stats = {
        "fast_command": 0,
        "mini_planner": 0,
        "planner_v2": 0,
        "avg_fast_time": 0.0,
        "avg_mini_time": 0.0,
        "avg_planner_time": 0.0,
        "fallbacks": 0,
        "confirmations": 0,
        "ollama_calls_prevented": 0,
        "requests_completed": 0,
        "requests_cancelled": 0,
        "requests_failed": 0,
        "fallback_log": []
    }
    
    if os.path.exists(stats_file):
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        if k in stats:
                            stats[k] = v
        except Exception:
            pass

    key = f"requests_{status}"
    if key in stats:
        stats[key] = stats.get(key, 0) + 1

    try:
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[ROUTER] Error saving request statistics: {e}")

def get_fast_command_step(goal: str) -> Optional[Tuple[Dict[str, Any], float, Optional[List[str]]]]:
    """
    Checks if the goal is a fast command.
    Returns: Tuple of (step, confidence, candidates_list) or None if not matched.
    """
    import re
    # Robust calculator routing
    norm_goal = normalize_text(goal)
    clean_goal = norm_goal
    for word in ["prosim te", "prosim", "te", "jarvis", "jarvisi", "ahoj", "cau", "dobry den", "hej jarvis", "ok jarvis"]:
        clean_goal = re.sub(rf"\b{word}\b", "", clean_goal)
    clean_goal = re.sub(r"\s+", " ", clean_goal).strip()

    calc_exact = {
        "calc", "calculator", "kalkulacka", "kalkulacku",
        "otevri kalkulacku", "zapni kalkulacku", "spust kalkulacku", "spustit kalkulacku",
        "otevri kalkulacka", "zapni kalkulacka", "spust kalkulacka", "spustit kalkulacka",
        "otevri calc", "zapni calc", "spust calc", "spustit calc",
        "otevri calculator", "zapni calculator", "spust calculator", "spustit calculator"
    }

    if clean_goal in calc_exact:
        return {"tool": "open_app", "input": {"name": "calculator"}, "description": "Otevřít kalkulačku"}, 1.0, None

    cleaned = strip_greetings(goal)
    if not cleaned:
        return None

    # Normalization: lower, no diacritics
    norm = normalize_text(cleaned)

    # Direct calculator matching
    calc_commands = (
        "calc", "calculator", "kalkulacka",
        "otevri kalkulacku", "zapni kalkulacku", "spust kalkulacku", "spustit kalkulacku",
        "otevri calc", "zapni calc", "spust calc",
        "otevri calculator", "zapni calculator", "spust calculator"
    )
    calc_norm = norm.replace(" prosim", "").strip()
    if calc_norm in calc_commands or norm in calc_commands:
        return {"tool": "open_app", "input": {"name": "calculator"}, "description": "Otevřít kalkulačku"}, 1.0, None

    # Fast router exclusions: if it contains multiple actions or complex keywords, it is not a FAST_COMMAND
    multi_action_indicators = [" a ", " pak ", " potom "]
    for indicator in multi_action_indicators:
        if indicator in norm:
            return None

    planner_v2_keywords = [
        "vytvor", "prezentac", "report", "zprav", "model", "naprogramuj", 
        "kod", "program"
    ]
    for kw in planner_v2_keywords:
        if kw in norm:
            return None

    # 1. Check direct matches for simple commands without prefixes
    if norm in ("screenshot", "udelej screenshot"):
        return {"tool": "screenshot", "input": {}, "description": "Pořídit snímek obrazovky"}, 1.0, None
    if norm in ("precti obrazovku", "cti obrazovku"):
        return {"tool": "read_screen", "input": {}, "description": "Přečíst obrazovku pomocí OCR"}, 1.0, None
    if norm in ("zavri okno", "zavri aktivni okno"):
        return {"tool": "close_window", "input": {}, "description": "Zavřít aktivní okno"}, 1.0, None
    if norm == "stiskni enter":
        return {"tool": "press_key", "input": {"key": "enter"}, "description": "Stisknout klávesu Enter"}, 1.0, None
    if norm == "stiskni escape":
        return {"tool": "press_key", "input": {"key": "escape"}, "description": "Stisknout klávesu Escape"}, 1.0, None
    if norm in ("vypis slozku", "zobraz soubory"):
        return {"tool": "list_dir", "input": {"path": "."}, "description": "Vypsat obsah složky"}, 1.0, None
    if norm in ("refresh_apps", "refresh apps"):
        return {"tool": "refresh_apps", "input": {}, "description": "Znovu načíst cache aplikací a aktualizovat seznam"}, 1.0, None

    # 2. Check search commands: "vyhledej <query>", "najdi <query>", "search <query>"
    search_prefixes = ("vyhledej ", "najdi ", "search ")
    for prefix in search_prefixes:
        if norm.startswith(prefix):
            query = cleaned[len(prefix):].strip()
            # If query is empty, do not treat it as search command
            if query:
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                return {"tool": "open_website", "input": {"url": search_url}, "description": f"Vyhledat „{query}“ v prohlížeči"}, 1.0, None

    # 3. Check website commands: "otevri <web>", "zapni <web>"
    open_prefixes = ("otevri ", "zapni ", "spust ", "pust ")
    
    # Check if the goal itself is just a known website (e.g. "seznam.cz")
    if norm in WEBSITE_URLS:
        url = WEBSITE_URLS[norm]
        return {"tool": "open_website", "input": {"url": url}, "description": f"Otevřít web {norm} v prohlížeči"}, 1.0, None

    for prefix in open_prefixes:
        if norm.startswith(prefix):
            target = norm[len(prefix):].strip()
            if target in WEBSITE_URLS:
                url = WEBSITE_URLS[target]
                return {"tool": "open_website", "input": {"url": url}, "description": f"Otevřít web {target} v prohlížeči"}, 1.0, None

    # 4. Check app commands: "otevri <app>", "zapni <app>" or just single word
    target_app = None
    matched_prefix = None
    for prefix in open_prefixes:
        if norm.startswith(prefix):
            matched_prefix = prefix
            target_app = cleaned[len(prefix):].strip()
            break

    if not target_app and " " not in norm:
        target_app = cleaned

    if target_app:
        target_norm = normalize_text(target_app)
        
        # Ambiguous check
        if target_norm in ("prohlizec", "browser"):
            prefs = load_user_preferences()
            saved_browser = prefs.get("prohlizec") or prefs.get("browser")
            if saved_browser:
                resolved = resolve_app_from_cache_with_score(saved_browser)
                if resolved:
                    best_name, best_path, best_score = resolved
                    return {"tool": "open_app", "input": {"name": best_name}, "description": f"Otevřít preferovaný prohlížeč {best_name}"}, 0.95, None
            return None, 0.65, ["Chrome", "Edge", "Firefox"]

        resolved = resolve_app_from_cache_with_score(target_app)
        if resolved:
            best_name, best_path, match_score = resolved
            if match_score == 100:
                conf = 0.98
            elif match_score == 95:
                conf = 0.97
            elif match_score == 90:
                conf = 0.96
            elif match_score == 80:
                conf = 0.95
            elif match_score == 70:
                conf = 0.92
            else:
                conf = 0.90
                
            print(f"[FAST_ROUTER]\nMatched alias: {target_app}\nResolved application: {best_name}\nConfidence: {conf:.2f}\n\nDecision:\nFAST_COMMAND")
            return {"tool": "open_app", "input": {"name": best_name}, "description": f"Otevřít aplikaci {best_name}"}, conf, None

    return None

def classify_routing_level(goal: str) -> Dict[str, Any]:
    """
    Main entry point for classifying and routing commands.
    Returns: A dictionary with 'route', 'confidence', 'step', and optional 'candidates'.
    """
    fast_res = get_fast_command_step(goal)
    if fast_res is not None:
        step, confidence, candidates = fast_res
        return {
            "route": "FAST_COMMAND",
            "confidence": confidence,
            "step": step,
            "candidates": candidates
        }
    
    cleaned = strip_greetings(goal)
    norm = normalize_text(cleaned)
    
    planner_v2_keywords = [
        "vytvor", "prezentac", "report", "zprav", "model", "naprogramuj", 
        "kod", "program"
    ]
    
    for kw in planner_v2_keywords:
        if kw in norm:
            return {
                "route": "PLANNER_V2",
                "confidence": 0.95,
                "step": None,
                "candidates": None
            }
            
    return {
        "route": "MINI_PLANNER",
        "confidence": 0.85,
        "step": None,
        "candidates": None
    }
