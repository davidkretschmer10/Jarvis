from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vision.schemas.ui_response import UIResponse


ActionType = Literal["open_app", "write_text", "click", "press_key", "hotkey"]


@dataclass(frozen=True)
class ActionRequest:
    type: ActionType
    value: str | list[str] | dict[str, Any] = ""
    description: str = ""


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    action: ActionRequest
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class ObservationResult:
    ok: bool
    ui: UIResponse | None = None
    screenshot_path: Path | None = None
    error: str | None = None
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class StepResult:
    step_index: int
    action_result: ActionResult
    observation_result: ObservationResult | None
    evaluation_passed: bool
    message: str = ""
    retry_count: int = 0

    @property
    def ok(self) -> bool:
        return self.action_result.ok and bool(self.observation_result and self.observation_result.ok)
