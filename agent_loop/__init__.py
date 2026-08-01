from __future__ import annotations

from typing import TYPE_CHECKING, Any


__all__ = [
    "ActionExecutor",
    "ActionRequest",
    "ActionResult",
    "ExpectedState",
    "FailureType",
    "ObservationLoop",
    "ObservationResult",
    "RetryManager",
    "RetryPolicy",
    "StateTracker",
    "StepResult",
    "TaskContext",
    "TaskState",
]


if TYPE_CHECKING:
    from agent_loop.action_executor import ActionExecutor
    from agent_loop.observation_loop import ObservationLoop
    from agent_loop.retry_manager import FailureType, RetryManager, RetryPolicy
    from agent_loop.state_tracker import StateTracker, TaskState
    from agent_loop.step_result import ActionRequest, ActionResult, ObservationResult, StepResult
    from agent_loop.task_context import ExpectedState, TaskContext


def __getattr__(name: str) -> Any:
    if name == "ActionExecutor":
        from agent_loop.action_executor import ActionExecutor

        return ActionExecutor
    if name == "ObservationLoop":
        from agent_loop.observation_loop import ObservationLoop

        return ObservationLoop
    if name in {"FailureType", "RetryManager", "RetryPolicy"}:
        from agent_loop.retry_manager import FailureType, RetryManager, RetryPolicy

        return {"FailureType": FailureType, "RetryManager": RetryManager, "RetryPolicy": RetryPolicy}[name]
    if name in {"StateTracker", "TaskState"}:
        from agent_loop.state_tracker import StateTracker, TaskState

        return {"StateTracker": StateTracker, "TaskState": TaskState}[name]
    if name in {"ActionRequest", "ActionResult", "ObservationResult", "StepResult"}:
        from agent_loop.step_result import ActionRequest, ActionResult, ObservationResult, StepResult

        return {
            "ActionRequest": ActionRequest,
            "ActionResult": ActionResult,
            "ObservationResult": ObservationResult,
            "StepResult": StepResult,
        }[name]
    if name in {"ExpectedState", "TaskContext"}:
        from agent_loop.task_context import ExpectedState, TaskContext

        return {"ExpectedState": ExpectedState, "TaskContext": TaskContext}[name]
    raise AttributeError(f"module 'agent_loop' has no attribute {name!r}")
