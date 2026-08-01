from __future__ import annotations

from dataclasses import dataclass, field

from agent_loop.step_result import ActionRequest


@dataclass(frozen=True)
class ExpectedState:
    screen_type: str | None = None
    required_text: tuple[str, ...] = ()
    required_element_types: tuple[str, ...] = ()
    required_element_texts: tuple[str, ...] = ()
    min_elements: int = 0


@dataclass(frozen=True)
class TaskContext:
    goal: str
    actions: list[ActionRequest]
    expected_state: ExpectedState = field(default_factory=ExpectedState)
    current_app: str | None = None
    max_steps: int = 10
    timeout_seconds: float = 120.0
    settle_seconds: float = 0.5
    observation_instruction: str | None = None

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.settle_seconds < 0:
            raise ValueError("settle_seconds cannot be negative")
