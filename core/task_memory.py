from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from core.services.application_resolver import get_default_appdata_path

TASK_MEMORY_FILE = get_default_appdata_path("jarvis_task_memory.json")
DATA_DIR = os.path.dirname(TASK_MEMORY_FILE)

class TaskMemory:
    def __init__(self) -> None:
        self.current_task: str = ""
        self.steps: List[Dict[str, Any]] = []
        self.last_result: str = ""

    def save(self) -> None:
        """Saves current state to the persistent task memory file."""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        data = {
            "current_task": self.current_task,
            "steps": self.steps,
            "last_result": self.last_result,
        }
        try:
            with open(TASK_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[TASK_MEMORY] Error saving state: {e}")

    def load(self) -> bool:
        """Loads state from the persistent file. Returns True if successful."""
        if not os.path.exists(TASK_MEMORY_FILE):
            return False
        try:
            with open(TASK_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.current_task = data.get("current_task", "")
            self.steps = data.get("steps", [])
            self.last_result = data.get("last_result", "")
            return True
        except Exception as e:
            print(f"[TASK_MEMORY] Error loading state: {e}")
            return False

    def reset(self) -> None:
        """Resets the task memory state and deletes the persistent file."""
        self.current_task = ""
        self.steps = []
        self.last_result = ""
        if os.path.exists(TASK_MEMORY_FILE):
            try:
                os.remove(TASK_MEMORY_FILE)
            except Exception as e:
                print(f"[TASK_MEMORY] Error removing file: {e}")

    def start_task(self, goal: str, steps: List[Dict[str, Any]]) -> None:
        """Initializes task memory with a new goal and list of steps."""
        self.current_task = goal
        self.steps = []
        for step in steps:
            # Each step should have: tool, input, description, status
            # If description is missing, synthesize one
            desc = step.get("description") or f"Spustit tool {step.get('tool')}"
            self.steps.append({
                "tool": step.get("tool", ""),
                "input": step.get("input", {}),
                "description": desc,
                "status": "pending",
            })
        self.last_result = ""
        self.save()

    def update_step_status(self, index: int, status: str, result: str = "") -> None:
        """Updates the status and last result for a step at index (0-indexed)."""
        if 0 <= index < len(self.steps):
            self.steps[index]["status"] = status
            if result:
                self.last_result = result
            self.save()
