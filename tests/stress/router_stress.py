import time
import random
from unittest.mock import patch
from core.intents.fast_command_router import classify_routing_level

# Expected mapping for accuracy testing
ROUTER_ACCURACY_MAP = {
    "zapni chrome": "google chrome",
    "zapni chrom": "google chrome",
    "otevři chrome": "google chrome",
    "zapni epic": "epic games launcher",
    "otevři epic games": "epic games launcher",
    "zapni blender": "blender",
    "otevři vscode": "visual studio code",
}

COMMAND_LIST = [
    "zapni chrome",
    "zapni chrom",
    "otevři chrome",
    "zapni epic",
    "otevři epic games",
    "zapni blender",
    "otevři vscode",
    "otevři kalkulačku",
    "otevři youtube",
    "otevři seznam",
    "vyhledej nvidia",
    "vyhledej amd",
    "refresh_apps"
]

def run_router_stress(num_iterations=10, mock_cache_data=None):
    if mock_cache_data is None:
        mock_cache_data = {
            "google chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "epic games launcher": "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\EpicGamesLauncher.exe",
            "notepad": "C:\\Windows\\notepad.exe",
            "calculator": "C:\\Windows\\System32\\calc.exe",
            "blender": "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe",
            "steam": "C:\\Program Files (x86)\\Steam\\steam.exe",
            "visual studio code": "C:\\Users\\User\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
        }

    stats = {
        "total_runs": 0,
        "success_runs": 0,
        "failed_runs": 0,
        "elapsed_times": [],
        "ollama_leaks": 0,
        "accuracy_runs": 0,
        "accuracy_success": 0,
        "failures_details": []
    }

    # Setup mocks
    with patch("core.intents.fast_command_router.load_apps_cache", return_value=mock_cache_data), \
         patch("ai.engine.ask_ai") as mock_ask_ai, \
         patch("ai.engine.generate_stream") as mock_generate_stream:

        mock_ask_ai.return_value = ""
        
        for _ in range(num_iterations):
            cmd = random.choice(COMMAND_LIST)
            stats["total_runs"] += 1
            
            start_t = time.perf_counter()
            ollama_called_before = mock_ask_ai.call_count + mock_generate_stream.call_count
            
            try:
                route_info = classify_routing_level(cmd)
                elapsed = time.perf_counter() - start_t
                stats["elapsed_times"].append(elapsed)
                
                # Check for Ollama leaks
                ollama_called_after = mock_ask_ai.call_count + mock_generate_stream.call_count
                if ollama_called_after > ollama_called_before:
                    stats["ollama_leaks"] += 1
                    stats["failed_runs"] += 1
                    print(f"[CRITICAL]\nFAST_COMMAND triggered Ollama\n\nCommand:\n{cmd}\n")
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": "ollama_leak"
                    })
                    continue

                if route_info["route"] != "FAST_COMMAND":
                    stats["failed_runs"] += 1
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": f"wrong_routing_level: expected FAST_COMMAND, got {route_info['route']}"
                    })
                    continue

                step = route_info["step"]
                if not step:
                    stats["failed_runs"] += 1
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": "step was None"
                    })
                    continue

                # Verify mapped tool
                expected_tool = None
                if cmd in ("zapni chrome", "zapni chrom", "otevři chrome", "zapni epic", "otevři epic games", "zapni blender", "otevři vscode", "otevři kalkulačku"):
                    expected_tool = "open_app"
                elif cmd in ("otevři youtube", "otevři seznam", "vyhledej nvidia", "vyhledej amd"):
                    expected_tool = "open_website"
                elif cmd == "refresh_apps":
                    expected_tool = "refresh_apps"
                
                if expected_tool and step["tool"] != expected_tool:
                    stats["failed_runs"] += 1
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": f"wrong tool: expected {expected_tool}, got {step['tool']}"
                    })
                    continue

                # Accuracy checks (expected vs actual app name)
                if cmd in ROUTER_ACCURACY_MAP:
                    stats["accuracy_runs"] += 1
                    expected_app = ROUTER_ACCURACY_MAP[cmd]
                    actual_app = step["input"].get("name")
                    if actual_app == expected_app:
                        stats["accuracy_success"] += 1
                    else:
                        stats["failed_runs"] += 1
                        stats["failures_details"].append({
                            "command": cmd,
                            "expected": expected_app,
                            "actual": actual_app,
                            "reason": "wrong application match"
                        })
                        continue
                
                stats["success_runs"] += 1
                
            except Exception as e:
                import traceback
                stats["failed_runs"] += 1
                stats["failures_details"].append({
                    "command": cmd,
                    "reason": f"exception: {str(e)}",
                    "traceback": traceback.format_exc()
                })

    return stats
