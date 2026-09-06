# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional
from core.memory_manager import get_memory_manager


class _DynamicTaskMemoryPath:
    def __fspath__(self) -> str:
        return get_memory_manager().task_memory_file

    def __str__(self) -> str:
        return get_memory_manager().task_memory_file

    def __eq__(self, other: Any) -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))


TASK_MEMORY_FILE = _DynamicTaskMemoryPath()
DATA_DIR = _DynamicTaskMemoryPath()


class TaskMemory:
    """
    Task Memory interface that delegates all persistence operations to MemoryManager.
    """

    def __init__(self) -> None:
        self.current_task: str = ""
        self.steps: List[Dict[str, Any]] = []
        self.last_result: str = ""

    def save(self) -> None:
        """Saves current task state to MemoryManager."""
        data = {
            "current_task": self.current_task,
            "steps": self.steps,
            "last_result": self.last_result,
        }
        get_memory_manager().save_task_memory(data)

    def load(self) -> bool:
        """Loads task state from MemoryManager."""
        data = get_memory_manager().load_task_memory()
        self.current_task = data.get("current_task", "")
        self.steps = data.get("steps", [])
        self.last_result = data.get("last_result", "")
        return bool(self.current_task or self.steps)

    def reset(self) -> None:
        """Resets current state and clears TaskMemory in MemoryManager."""
        self.current_task = ""
        self.steps = []
        self.last_result = ""
        get_memory_manager().reset_task_memory()

    def start_task(self, goal: str, steps: List[Dict[str, Any]]) -> None:
        """Initializes task memory with a new goal and steps."""
        self.current_task = goal
        self.steps = []
        for step in steps:
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
        """Updates status of a step at index."""
        if 0 <= index < len(self.steps):
            self.steps[index]["status"] = status
            if result:
                self.last_result = result
            self.save()
