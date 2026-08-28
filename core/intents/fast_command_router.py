# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

from core.intents.target_extractor import normalize_text, strip_greetings
from core.services.application_resolver import (
    APP_ALIASES_MAP,
    APP_ALIAS_LOOKUP,
    ApplicationResolver,
    get_application_resolver,
    get_default_appdata_path,
)

APP_ALIASES = APP_ALIAS_LOOKUP

WEBSITE_URLS = {
    "seznam": "https://www.seznam.cz",
    "seznam.cz": "https://www.seznam.cz",
    "google": "https://www.google.com",
    "google.com": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "youtube.com": "https://www.youtube.com",
}


def get_appdata_path(filename: str) -> str:
    return get_default_appdata_path(filename)


def load_user_preferences() -> Dict[str, str]:
    return get_application_resolver().load_preferences()


def save_user_preference(key: str, val: str) -> None:
    get_application_resolver().save_preference(key, val)


def load_apps_cache() -> Dict[str, str]:
    return get_application_resolver().load_cache()


def is_ignored_app(name: str, path: str) -> bool:
    return get_application_resolver().is_ignored_app(name, path)


def resolve_app_from_cache_with_score(query: str) -> Optional[Tuple[str, str, int]]:
    resolver = get_application_resolver()
    mocked_cache = load_apps_cache()
    if mocked_cache is not None:
        resolver._cached_apps = dict(mocked_cache)
    res = resolver.resolve(query)
    if res.found and res.path:
        return res.name, res.path, res.score
    return None


def increment_router_stat(
    level: str,
    elapsed_time: float = 0.0,
    fallback: bool = False,
    confirmation: bool = False,
    fallback_reason: Optional[str] = None,
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
        "fallback_log": [],
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
                "reason": fallback_reason,
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
        "fallback_log": [],
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
    import re

    norm_goal = normalize_text(goal)
    clean_goal = norm_goal
    for word in [
        "prosim te",
        "prosim",
        "te",
        "jarvis",
        "jarvisi",
        "ahoj",
        "cau",
        "dobry den",
        "hej jarvis",
        "ok jarvis",
    ]:
        clean_goal = re.sub(rf"\b{word}\b", "", clean_goal)
    clean_goal = re.sub(r"\s+", " ", clean_goal).strip()

    calc_exact = {
        "calc",
        "calculator",
        "kalkulacka",
        "kalkulacku",
        "otevri kalkulacku",
        "zapni kalkulacku",
        "spust kalkulacku",
        "spustit kalkulacku",
        "otevri kalkulacka",
        "zapni kalkulacka",
        "spust kalkulacka",
        "spustit kalkulacka",
        "otevri calc",
        "zapni calc",
        "spust calc",
        "spustit calc",
        "otevri calculator",
        "zapni calculator",
        "spust calculator",
        "spustit calculator",
    }

    if clean_goal in calc_exact:
        return {"tool": "open_app", "input": {"name": "calculator"}, "description": "Otevřít kalkulačku"}, 1.0, None

    cleaned = strip_greetings(goal)
    if not cleaned:
        return None

    norm = normalize_text(cleaned)

    calc_commands = (
        "calc",
        "calculator",
        "kalkulacka",
        "otevri kalkulacku",
        "zapni kalkulacku",
        "spust kalkulacku",
        "spustit kalkulacku",
        "otevri calc",
        "zapni calc",
        "spust calc",
        "otevri calculator",
        "zapni calculator",
        "spust calculator",
    )
    calc_norm = norm.replace(" prosim", "").strip()
    if calc_norm in calc_commands or norm in calc_commands:
        return {"tool": "open_app", "input": {"name": "calculator"}, "description": "Otevřít kalkulačku"}, 1.0, None

    multi_action_indicators = [" a ", " pak ", " potom "]
    for indicator in multi_action_indicators:
        if indicator in norm:
            return None

    planner_v2_keywords = [
        "vytvor",
        "prezentac",
        "report",
        "zprav",
        "model",
        "naprogramuj",
        "kod",
        "program",
    ]
    for kw in planner_v2_keywords:
        if kw in norm:
            return None

    if norm in ("screenshot", "udelej screenshot", "snimek obrazovky"):
        return {"tool": "screenshot", "input": {}, "description": "Pořídit snímek obrazovky"}, 1.0, None
    if norm in ("precti obrazovku", "cti obrazovku", "ocr"):
        return {"tool": "read_screen", "input": {}, "description": "Přečíst obrazovku pomocí OCR"}, 1.0, None
    if norm in ("zavri okno", "zavri aktivni okno"):
        return {"tool": "close_window", "input": {}, "description": "Zavřít aktivní okno"}, 1.0, None
    if norm == "stiskni enter":
        return {"tool": "press_key", "input": {"key": "enter"}, "description": "Stisknout klávesu Enter"}, 1.0, None
    if norm == "stiskni escape":
        return {"tool": "press_key", "input": {"key": "escape"}, "description": "Stisknout klávesu Escape"}, 1.0, None
    if norm in ("prepni", "dalsi", "dalsi skladba"):
        return {"tool": "press_key", "input": {"key": "nexttrack"}, "description": "Přepnout na další skladbu"}, 1.0, None
    if norm in ("zastav", "pauzni", "stopni", "pauza", "play", "pause"):
        return {"tool": "press_key", "input": {"key": "playpause"}, "description": "Pozastavit / Spustit přehrávání"}, 1.0, None
    if norm in ("predchozi", "vrat", "predchozi skladba"):
        return {"tool": "press_key", "input": {"key": "prevtrack"}, "description": "Vrátit na předchozí skladbu"}, 1.0, None
    if norm in ("vypis slozku", "zobraz soubory"):
        return {"tool": "list_dir", "input": {"path": "."}, "description": "Vypsat obsah složky"}, 1.0, None
    if norm in ("refresh_apps", "refresh apps"):
        return {"tool": "refresh_apps", "input": {}, "description": "Znovu načíst cache aplikací a aktualizovat seznam"}, 1.0, None

    key_prefixes = ("stiskni ", "zmackni ")
    for prefix in key_prefixes:
        if norm.startswith(prefix):
            val = norm[len(prefix):].strip()
            if "+" in val or " " in val:
                keys = [p for p in val.replace("+", " ").split() if p]
                return {"tool": "hotkey", "input": {"keys": keys}, "description": f"Stisknout klávesovou zkratku {'+'.join(keys)}"}, 1.0, None
            return {"tool": "press_key", "input": {"key": val}, "description": f"Stisknout klávesu {val}"}, 1.0, None


    search_prefixes = ("vyhledej ", "najdi ", "search ")
    for prefix in search_prefixes:
        if norm.startswith(prefix):
            query = cleaned[len(prefix):].strip()
            if query:
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                return {"tool": "open_website", "input": {"url": search_url}, "description": f"Vyhledat „{query}“ v prohlížeči"}, 1.0, None

    open_prefixes = ("otevri ", "zapni ", "spust ", "pust ")

    if norm in WEBSITE_URLS:
        url = WEBSITE_URLS[norm]
        return {"tool": "open_website", "input": {"url": url}, "description": f"Otevřít web {norm} v prohlížeči"}, 1.0, None

    for prefix in open_prefixes:
        if norm.startswith(prefix):
            target = norm[len(prefix):].strip()
            if target in WEBSITE_URLS:
                url = WEBSITE_URLS[target]
                return {"tool": "open_website", "input": {"url": url}, "description": f"Otevřít web {target} v prohlížeči"}, 1.0, None

    target_app = None
    for prefix in open_prefixes:
        if norm.startswith(prefix):
            target_app = cleaned[len(prefix):].strip()
            break

    if not target_app and " " not in norm:
        target_app = cleaned

    if target_app:
        target_norm = normalize_text(target_app)

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
            conf = get_application_resolver().score_to_confidence(match_score)
            print(f"[FAST_ROUTER]\nMatched alias: {target_app}\nResolved application: {best_name}\nConfidence: {conf:.2f}\n\nDecision:\nFAST_COMMAND")
            return {"tool": "open_app", "input": {"name": best_name}, "description": f"Otevřít aplikaci {best_name}"}, conf, None

    return None


def classify_routing_level(goal: str) -> Dict[str, Any]:
    fast_res = get_fast_command_step(goal)
    if fast_res is not None:
        step, confidence, candidates = fast_res
        return {
            "route": "FAST_COMMAND",
            "confidence": confidence,
            "step": step,
            "candidates": candidates,
        }

    cleaned = strip_greetings(goal)
    norm = normalize_text(cleaned)

    planner_v2_keywords = [
        "vytvor",
        "prezentac",
        "report",
        "zprav",
        "model",
        "naprogramuj",
        "kod",
        "program",
    ]

    for kw in planner_v2_keywords:
        if kw in norm:
            return {
                "route": "PLANNER_V2",
                "confidence": 0.95,
                "step": None,
                "candidates": None,
            }

    return {
        "route": "MINI_PLANNER",
        "confidence": 0.85,
        "step": None,
        "candidates": None,
    }
