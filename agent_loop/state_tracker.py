from __future__ import annotations

from dataclasses import dataclass, field
import time

from agent_loop.step_result import StepResult
from agent_loop.task_context import TaskContext


@dataclass
class TaskState:
    goal: str
    status: str = "pending"
    expected_state: dict[str, object] = field(default_factory=dict)
    current_app: str | None = None
    current_step: int = 0
    retry_count: int = 0
    progress: float = 0.0
    started_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    history: list[StepResult] = field(default_factory=list)


class StateTracker:
    def __init__(self) -> None:
        self.state: TaskState | None = None

    def start(self, context: TaskContext) -> TaskState:
        self.state = TaskState(
            goal=context.goal,
            status="running",
            expected_state={
                "screen_type": context.expected_state.screen_type,
                "required_text": list(context.expected_state.required_text),
                "required_element_types": list(context.expected_state.required_element_types),
                "required_element_texts": list(context.expected_state.required_element_texts),
                "min_elements": context.expected_state.min_elements,
            },
            current_app=context.current_app,
        )
        return self.state

    def record_step(self, result: StepResult, total_steps: int) -> None:
        state = self._require_state()
        state.history.append(result)
        state.current_step = result.step_index + 1
        state.retry_count = result.retry_count
        state.progress = min(1.0, state.current_step / max(1, total_steps))
        state.updated_at = time.monotonic()

    def set_status(self, status: str) -> None:
        state = self._require_state()
        state.status = status
        state.updated_at = time.monotonic()

    def increment_retry(self) -> int:
        state = self._require_state()
        state.retry_count += 1
        state.updated_at = time.monotonic()
        return state.retry_count

    def reset_retry(self) -> None:
        state = self._require_state()
        state.retry_count = 0
        state.updated_at = time.monotonic()

    def elapsed_seconds(self) -> float:
        state = self._require_state()
        return time.monotonic() - state.started_at

    def _require_state(self) -> TaskState:
        if self.state is None:
            raise RuntimeError("Task state has not been started")
        return self.state
