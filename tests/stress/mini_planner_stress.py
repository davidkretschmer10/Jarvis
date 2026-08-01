import time
import random
from unittest.mock import patch
from core.intents.fast_command_router import classify_routing_level
from core.planner import Planner

MINI_PLANNER_COMMANDS = [
    "otevři chrome a vyhledej nvidia",
    "otevři youtube a vyhledej ai",
    "otevři seznam a najdi počasí"
]

MOCK_PLANNER_RESPONSES = {
    "otevři chrome a vyhledej nvidia": '[{"tool": "open_app", "input": {"name": "chrome"}, "description": "Otevřít Chrome"}, {"tool": "open_website", "input": {"url": "https://www.google.com/search?q=nvidia"}, "description": "Vyhledat nvidia"}]',
    "otevři youtube a vyhledej ai": '[{"tool": "open_website", "input": {"url": "https://www.youtube.com/results?search_query=ai"}, "description": "Vyhledat ai na Youtube"}]',
    "otevři seznam a najdi počasí": '[{"tool": "open_website", "input": {"url": "https://www.seznam.cz"}, "description": "Otevřít Seznam"}, {"tool": "open_website", "input": {"url": "https://www.google.com/search?q=počasí"}, "description": "Vyhledat počasí"}]'
}

def run_mini_planner_stress(num_iterations=5):
    stats = {
        "total_runs": 0,
        "success_runs": 0,
        "failed_runs": 0,
        "ollama_calls": 0,
        "failures_details": []
    }
    
    for _ in range(num_iterations):
        cmd = random.choice(MINI_PLANNER_COMMANDS)
        stats["total_runs"] += 1
        
        try:
            route_info = classify_routing_level(cmd)
            if route_info["route"] != "MINI_PLANNER":
                stats["failed_runs"] += 1
                stats["failures_details"].append({
                    "command": cmd,
                    "reason": f"wrong_routing_level: expected MINI_PLANNER, got {route_info['route']}"
                })
                continue
                
            mock_plan_json = MOCK_PLANNER_RESPONSES.get(cmd, "[]")
            
            with patch("ai.engine.ask_ai", return_value=mock_plan_json) as mock_ask_ai:
                # Mock a simple registry so the planner runs without loading all tools
                mock_reg = patch("tools.registry.ToolRegistry").start()
                mock_reg.describe_for_planner.return_value = "open_app, open_website"
                
                planner = Planner(registry=mock_reg)
                steps = planner.plan(cmd)
                
                patch.stopall()
                
                stats["ollama_calls"] += mock_ask_ai.call_count
                
                if mock_ask_ai.call_count > 1:
                    stats["failed_runs"] += 1
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": f"too_many_ollama_calls: expected <= 1, got {mock_ask_ai.call_count}"
                    })
                    continue
                    
                if not steps:
                    stats["failed_runs"] += 1
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": "empty_plan_generated"
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
