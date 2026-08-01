import time
import random
import os
from unittest.mock import patch
from core.intents.fast_command_router import classify_routing_level
from core.planner import Planner
from core.task_memory import TaskMemory

PLANNER_V2_COMMANDS = [
    "vytvoř prezentaci o ai",
    "vytvoř report o nvidia",
    "vytvoř návrh webu"
]

MOCK_PLANNER_RESPONSES = {
    "vytvoř prezentaci o ai": '[{"tool": "open_app", "input": {"name": "powerpoint"}, "description": "Otevřít PowerPoint"}, {"tool": "write_text", "input": {"text": "Prezentace o AI"}, "description": "Napsat titulek"}]',
    "vytvoř report o nvidia": '[{"tool": "open_app", "input": {"name": "word"}, "description": "Otevřít Word"}, {"tool": "write_text", "input": {"text": "Report o Nvidia"}, "description": "Zapsat report"}]',
    "vytvoř návrh webu": '[{"tool": "open_app", "input": {"name": "chrome"}, "description": "Otevřít Chrome"}, {"tool": "open_website", "input": {"url": "https://figma.com"}, "description": "Otevřít Figma"}]'
}

def run_planner_v2_stress(num_iterations=3):
    stats = {
        "total_runs": 0,
        "success_runs": 0,
        "failed_runs": 0,
        "ollama_calls": 0,
        "failures_details": []
    }
    
    for _ in range(num_iterations):
        cmd = random.choice(PLANNER_V2_COMMANDS)
        stats["total_runs"] += 1
        
        try:
            route_info = classify_routing_level(cmd)
            if route_info["route"] != "PLANNER_V2":
                stats["failed_runs"] += 1
                stats["failures_details"].append({
                    "command": cmd,
                    "reason": f"wrong_routing_level: expected PLANNER_V2, got {route_info['route']}"
                })
                continue
                
            mock_plan_json = MOCK_PLANNER_RESPONSES.get(cmd, "[]")
            
            with patch("ai.engine.ask_ai", return_value=mock_plan_json) as mock_ask_ai:
                mock_reg = patch("tools.registry.ToolRegistry").start()
                mock_reg.describe_for_planner.return_value = "open_app, open_website, write_text"
                
                planner = Planner(registry=mock_reg)
                steps = planner.plan(cmd)
                
                patch.stopall()
                
                stats["ollama_calls"] += mock_ask_ai.call_count
                
                if not steps:
                    stats["failed_runs"] += 1
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": "empty_plan_generated"
                    })
                    continue
                    
                # Verify Task Memory
                task_mem = TaskMemory()
                task_mem.reset()
                task_mem.start_task(cmd, steps)
                
                # Verify that it saved correctly
                if task_mem.current_task != cmd or len(task_mem.steps) != len(steps):
                    stats["failed_runs"] += 1
                    stats["failures_details"].append({
                        "command": cmd,
                        "reason": "task_memory_mismatch"
                    })
                    continue
                    
                # Check status key in steps
                for step in task_mem.steps:
                    if step["status"] != "pending":
                        stats["failed_runs"] += 1
                        stats["failures_details"].append({
                            "command": cmd,
                            "reason": "task_memory_step_not_pending"
                        })
                        break
                else:
                    stats["success_runs"] += 1
                    
                task_mem.reset() # clean up
                
        except Exception as e:
            import traceback
            stats["failed_runs"] += 1
            stats["failures_details"].append({
                "command": cmd,
                "reason": f"exception: {str(e)}",
                "traceback": traceback.format_exc()
            })
            
    return stats
