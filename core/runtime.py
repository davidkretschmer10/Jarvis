from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any, Callable, Dict, List, Optional

from ai.engine import (
    complete_current_request,
    fail_current_request,
    get_current_request,
    reset_current_request,
)
from core.executor import Executor
from core.intents.fast_command_router import classify_routing_level, increment_router_stat
from core.planner import Planner
from core.state import JarvisState
from core.task_memory import TaskMemory
from tools.base import ToolContext
from tools.registry import ToolRegistry, build_default_registry


JSON = Dict[str, Any]
StepCallback = Callable[[int, str], None]
TaskStartCallback = Callable[[str, List[str]], None]


@dataclass
class RuntimeResult:
    ok: bool
    goal: str
    route: str
    confidence: float
    steps: List[JSON]
    results: List[JSON]
    state: JarvisState
    summary: str
    request_id: str
    pending_confirmation: bool = False
    confirmation_message: str = ""
    fallback_occurred: bool = False
    fallback_reason: Optional[str] = None


class JarvisRuntime:
    """Single task runtime shared by CLI, GUI, and voice entry points."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        agent_base_url: str = "http://127.0.0.1:5000",
        workspace_root: Optional[str] = None,
        dry_run: bool = False,
        event_bus: Any = None,
    ) -> None:
        self.registry = registry or build_default_registry()
        self.agent_base_url = agent_base_url
        self.workspace_root = workspace_root or os.getcwd()
        self.dry_run = dry_run
        self.event_bus = event_bus

    def run_task(
        self,
        goal: str,
        state: Optional[JarvisState] = None,
        task_memory: Optional[TaskMemory] = None,
        on_step_update: Optional[StepCallback] = None,
        on_task_start: Optional[TaskStartCallback] = None,
        reset_request: bool = True,
    ) -> RuntimeResult:
        if reset_request:
            reset_current_request()

        state = state or JarvisState()
        request_id = get_current_request().request_id
        self._emit("task_requested", {"goal": goal, "request_id": request_id})

        started = time.perf_counter()
        route_info = classify_routing_level(goal)
        level = route_info["route"]
        confidence = route_info["confidence"]
        step = route_info["step"]
        candidates = route_info["candidates"]
        steps: List[JSON] = []
        fallback_occurred = False
        fallback_reason: Optional[str] = None
        use_task_memory = False

        if confidence < 0.70 and candidates:
            message = "Nalezl jsem vice moznosti:\n" + "\n".join(f"* {c}" for c in candidates)
            state.data["router_candidates"] = list(candidates)
            return RuntimeResult(
                ok=False,
                goal=goal,
                route=level,
                confidence=confidence,
                steps=[],
                results=[],
                state=state,
                summary=message,
                request_id=request_id,
                pending_confirmation=True,
                confirmation_message=message,
            )

        if level == "FAST_COMMAND":
            if step:
                steps = [step]
                self._emit("route_selected", {"route": level, "confidence": confidence, "steps": steps})
            else:
                level = "MINI_PLANNER"
                fallback_occurred = True
                fallback_reason = "FAST_COMMAND step was not generated"

        if level == "MINI_PLANNER":
            steps, level, fallback_occurred, fallback_reason = self._plan_with_fallback(
                goal, level, fallback_occurred, fallback_reason
            )

        if level == "PLANNER_V2":
            use_task_memory = True
            steps = Planner(registry=self.registry).plan(goal)

        elapsed = time.perf_counter() - started
        increment_router_stat(
            level=level,
            elapsed_time=elapsed,
            fallback=fallback_occurred,
            fallback_reason=fallback_reason,
        )

        if not steps:
            fail_current_request()
            summary = "Chyba: Nepodarilo se vygenerovat plan."
            return RuntimeResult(
                ok=False,
                goal=goal,
                route=level,
                confidence=confidence,
                steps=[],
                results=[],
                state=state,
                summary=summary,
                request_id=request_id,
                fallback_occurred=fallback_occurred,
                fallback_reason=fallback_reason,
            )

        ctx = ToolContext(
            dry_run=self.dry_run,
            agent_base_url=self.agent_base_url,
            workspace_root=self.workspace_root,
        )
        if on_task_start:
            on_task_start(
                goal,
                [step.get("description") or f"Spustit tool {step.get('tool')}" for step in steps],
            )
        if use_task_memory and task_memory is None:
            task_memory = TaskMemory()

        executor = Executor(
            registry=self.registry,
            ctx=ctx,
            state=state,
            task_memory=task_memory,
            on_step_update=on_step_update,
        )
        results = executor.run_plan(steps)
        ok, summary, pending_confirmation = self._summarize_execution(results, state, len(steps))

        if pending_confirmation:
            confirmation_message = state.data.get("user_help_required", "Akce vyzaduje potvrzeni.")
            summary = confirmation_message
        elif ok:
            complete_current_request()
        else:
            fail_current_request()

        result = RuntimeResult(
            ok=ok,
            goal=goal,
            route=level,
            confidence=confidence,
            steps=steps,
            results=results,
            state=state,
            summary=summary,
            request_id=request_id,
            pending_confirmation=pending_confirmation,
            confirmation_message=state.data.get("user_help_required", ""),
            fallback_occurred=fallback_occurred,
            fallback_reason=fallback_reason,
        )
        self._emit("task_finished", result)
        return result

    def resume_task(
        self,
        goal: str,
        steps: List[JSON],
        state: JarvisState,
        start_index: int,
        task_memory: Optional[TaskMemory] = None,
        on_step_update: Optional[StepCallback] = None,
        on_task_start: Optional[TaskStartCallback] = None,
    ) -> RuntimeResult:
        state.data["action_confirmed"] = True
        state.data.pop("user_help_required", None)
        state.data.pop("paused_step_index", None)

        remaining_steps = steps[start_index:]
        if on_task_start:
            on_task_start(
                goal,
                [step.get("description") or f"Spustit tool {step.get('tool')}" for step in remaining_steps],
            )
        ctx = ToolContext(
            dry_run=self.dry_run,
            agent_base_url=self.agent_base_url,
            workspace_root=self.workspace_root,
        )
        executor = Executor(self.registry, ctx, state, task_memory, on_step_update)
        results = executor.run_plan(remaining_steps)
        ok, summary, pending_confirmation = self._summarize_execution(results, state, len(steps), start_index)
        if ok:
            complete_current_request()
        elif not pending_confirmation:
            fail_current_request()

        return RuntimeResult(
            ok=ok,
            goal=goal,
            route="RESUME",
            confidence=1.0,
            steps=steps,
            results=results,
            state=state,
            summary=summary if not pending_confirmation else state.data.get("user_help_required", summary),
            request_id=get_current_request().request_id,
            pending_confirmation=pending_confirmation,
            confirmation_message=state.data.get("user_help_required", ""),
        )

    def _plan_with_fallback(
        self,
        goal: str,
        level: str,
        fallback_occurred: bool,
        fallback_reason: Optional[str],
    ) -> tuple[List[JSON], str, bool, Optional[str]]:
        try:
            steps = Planner(registry=self.registry).plan(goal)
            if len(steps) > 5 or not steps:
                return (
                    steps,
                    "PLANNER_V2",
                    True,
                    "plan contains more than 5 steps" if steps else "empty plan generated by MINI_PLANNER",
                )
            return steps, level, fallback_occurred, fallback_reason
        except Exception as exc:
            return [], "PLANNER_V2", True, f"MINI_PLANNER planning exception: {exc}"

    def _summarize_execution(
        self,
        results: List[JSON],
        state: JarvisState,
        total_steps: int,
        start_index: int = 0,
    ) -> tuple[bool, str, bool]:
        if "paused_step_index" in state.data:
            return False, state.data.get("user_help_required", "Akce vyzaduje potvrzeni."), True

        help_required = state.data.get("user_help_required")
        if help_required:
            return False, f"Chyba behem provadeni: {help_required}", False

        if results and not results[-1]["output"].get("ok", False):
            step_no = start_index + len(results)
            error = results[-1]["output"].get("error", "Neznama chyba")
            return False, f"Ukol selhal na kroku {step_no}: {error}", False

        return True, f"Ukol byl uspesne dokoncen! Celkem provedeno {total_steps} kroku.", False

    def _emit(self, event_name: str, data: Any) -> None:
        if self.event_bus is not None:
            self.event_bus.emit(event_name, data)
