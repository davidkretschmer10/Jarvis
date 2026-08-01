import os
import json
import shutil
from unittest.mock import patch
from core.intents.fast_command_router import (
    classify_routing_level,
    get_appdata_path,
    load_apps_cache,
    load_user_preferences
)
from core.agent import load_scanned_apps

def run_chaos_tests():
    results = {
        "total_chaos_runs": 0,
        "success_runs": 0,
        "failed_runs": 0,
        "failures_details": []
    }
    
    cache_file = get_appdata_path("apps_cache.json")
    stats_file = get_appdata_path("router_stats.json")
    pref_file = get_appdata_path("user_preferences.json")
    
    cache_backup = cache_file + ".bak"
    stats_backup = stats_file + ".bak"
    pref_backup = pref_file + ".bak"
    
    for f_orig, f_bak in [(cache_file, cache_backup), (stats_file, stats_backup), (pref_file, pref_backup)]:
        if os.path.exists(f_orig):
            try:
                shutil.copy2(f_orig, f_bak)
            except Exception:
                pass
                
    try:
        # Chaos 1: Missing apps_cache.json
        results["total_chaos_runs"] += 1
        try:
            if os.path.exists(cache_file):
                os.remove(cache_file)
            
            with patch("core.agent.scan_all_apps", return_value={"testapp": "C:\\test.exe"}):
                apps = load_scanned_apps(force=True)
                if not os.path.exists(cache_file) or "testapp" not in apps:
                    raise AssertionError("apps_cache.json was not rebuilt automatically")
            results["success_runs"] += 1
        except Exception as e:
            results["failed_runs"] += 1
            results["failures_details"].append({
                "chaos_scenario": "missing_apps_cache",
                "reason": str(e)
            })

        # Chaos 2: Corrupted router_stats.json
        results["total_chaos_runs"] += 1
        try:
            with open(stats_file, "w", encoding="utf-8") as f:
                f.write("this is completely corrupted JSON string {[[")
            
            from core.intents.fast_command_router import increment_router_stat
            increment_router_stat("FAST_COMMAND", elapsed_time=0.1)
            
            with open(stats_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("fast_command") != 1:
                raise AssertionError("router_stats.json was not recovered")
            results["success_runs"] += 1
        except Exception as e:
            results["failed_runs"] += 1
            results["failures_details"].append({
                "chaos_scenario": "corrupted_router_stats",
                "reason": str(e)
            })

        # Chaos 3: Non-existent application
        results["total_chaos_runs"] += 1
        try:
            res = classify_routing_level("zapni supernekonecnyapp")
            if res is None or res["route"] in ("MINI_PLANNER", "PLANNER_V2"):
                results["success_runs"] += 1
            else:
                raise AssertionError(f"Unexpected routing for non-existent app: {res['route']}")
        except Exception as e:
            results["failed_runs"] += 1
            results["failures_details"].append({
                "chaos_scenario": "non_existent_app",
                "reason": str(e)
            })

        # Chaos 4: Disconnected Ollama
        results["total_chaos_runs"] += 1
        try:
            with patch("ai.engine.check_ollama_health", return_value=False):
                from ai.engine import ask_ai, generate_stream
                res = ask_ai("Ahoj")
                if res != "":
                    raise AssertionError(f"Expected empty response when Ollama offline, got '{res}'")
                
                stream_res = list(generate_stream("Ahoj"))
                if not any("spojit s Ollamou" in token for token in stream_res):
                    raise AssertionError(f"Expected offline fallback message in stream, got {stream_res}")
                    
            results["success_runs"] += 1
        except Exception as e:
            results["failed_runs"] += 1
            results["failures_details"].append({
                "chaos_scenario": "disconnected_ollama",
                "reason": str(e)
            })

        # Chaos 5: Empty user_preferences.json
        results["total_chaos_runs"] += 1
        try:
            with open(pref_file, "w", encoding="utf-8") as f:
                f.write("{}")
            
            prefs = load_user_preferences()
            if not isinstance(prefs, dict) or len(prefs) != 0:
                raise AssertionError("Failed to load empty user preferences")
                
            res = classify_routing_level("otevři prohlížeč")
            if res["route"] == "FAST_COMMAND" and res["confidence"] < 0.70:
                results["success_runs"] += 1
            else:
                raise AssertionError(f"Expected low confidence FAST_COMMAND for browser, got {res}")
        except Exception as e:
            results["failed_runs"] += 1
            results["failures_details"].append({
                "chaos_scenario": "empty_user_preferences",
                "reason": str(e)
            })

    finally:
        for f_orig, f_bak in [(cache_file, cache_backup), (stats_file, stats_backup), (pref_file, pref_backup)]:
            if os.path.exists(f_bak):
                try:
                    if os.path.exists(f_orig):
                        os.remove(f_orig)
                    shutil.move(f_bak, f_orig)
                except Exception:
                    pass
                    
    return results
