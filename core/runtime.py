from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any, Callable, Dict, List, Optional

from core.executor import Executor
from core.intents.fast_command_router import classify_routing_level, increment_router_stat
from core.lifecycle import (
    RequestContext,
    RequestStatus,
    complete_current_request,
    fail_current_request,
    get_current_request,
    reset_current_request,
)
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
            ctx = reset_current_request(goal=goal, source="runtime")
        else:
            ctx = get_current_request()
            if hasattr(ctx, "goal"):
                ctx.goal = goal

        request_id = getattr(ctx, "request_id", "")
        state = state or JarvisState()

        self._emit("task_requested", {"goal": goal, "request_id": request_id})
        self._emit("request_created", {"goal": goal, "request_id": request_id})

        # --- ROUTING ---
        if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
            try:
                ctx.transition_to(RequestStatus.ROUTING, event_bus=self.event_bus)
            except Exception:
                pass

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

        self._emit(
            "routing_completed",
            {
                "request_id": request_id,
                "route": level,
                "confidence": confidence,
                "candidates": candidates,
            },
        )

        if confidence < 0.70 and candidates:
            message = "Nalezl jsem vice moznosti:\n" + "\n".join(f"* {c}" for c in candidates)
            state.data["router_candidates"] = list(candidates)
            if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                try:
                    ctx.transition_to(
                        RequestStatus.WAITING_FOR_USER,
                        event_bus=self.event_bus,
                        message=message,
                        candidates=candidates,
                    )
                except Exception:
                    pass

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

        # --- PLANNING or DIRECT EXECUTING ---
        if level == "FAST_COMMAND":
            if step:
                steps = [step]
                self._emit("route_selected", {"route": level, "confidence": confidence, "steps": steps})
                if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                    try:
                        ctx.transition_to(RequestStatus.EXECUTING, event_bus=self.event_bus)
                    except Exception:
                        pass
            else:
                level = "MINI_PLANNER"
                fallback_occurred = True
                fallback_reason = "FAST_COMMAND step was not generated"

        if level == "MINI_PLANNER":
            if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                try:
                    ctx.transition_to(RequestStatus.PLANNING, event_bus=self.event_bus)
                except Exception:
                    pass
            steps, level, fallback_occurred, fallback_reason = self._plan_with_fallback(
                goal, level, fallback_occurred, fallback_reason
            )

        if level == "PLANNER_V2":
            use_task_memory = True
            if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                try:
                    ctx.transition_to(RequestStatus.PLANNING, event_bus=self.event_bus)
                except Exception:
                    pass
            steps = Planner(registry=self.registry).plan(goal)

        if steps and level in ("MINI_PLANNER", "PLANNER_V2"):
            self._emit("planning_completed", {"request_id": request_id, "steps_count": len(steps), "steps": steps})
            if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                try:
                    ctx.transition_to(RequestStatus.EXECUTING, event_bus=self.event_bus)
                except Exception:
                    pass

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

        ctx_tool = ToolContext(
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

        planner_inst = Planner(registry=self.registry)

        # --- EXECUTING ---
        executor = Executor(
            registry=self.registry,
            ctx=ctx_tool,
            state=state,
            task_memory=task_memory,
            on_step_update=on_step_update,
            request_context=ctx if isinstance(ctx, RequestContext) else None,
            event_bus=self.event_bus,
            planner=planner_inst,
        )
        results = executor.run_plan(steps)


        # --- VERIFYING ---
        if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
            if not ("paused_step_index" in state.data or state.data.get("user_help_required")):
                try:
                    ctx.transition_to(RequestStatus.VERIFYING, event_bus=self.event_bus)
                except Exception:
                    pass

        ok, summary, pending_confirmation = self._summarize_execution(results, state, len(steps))

        # --- COMPLETING / FAILING / WAITING ---
        if pending_confirmation:
            confirmation_message = state.data.get("user_help_required", "Akce vyzaduje potvrzeni.")
            summary = confirmation_message
            if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                try:
                    ctx.transition_to(
                        RequestStatus.WAITING_FOR_USER,
                        event_bus=self.event_bus,
                        message=confirmation_message,
                    )
                except Exception:
                    pass
        elif ok:
            complete_current_request(result=summary, event_bus=self.event_bus)
        else:
            fail_current_request(error=summary, event_bus=self.event_bus)

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
        ctx = get_current_request()
        if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
            try:
                ctx.transition_to(RequestStatus.EXECUTING, event_bus=self.event_bus, start_index=start_index)
            except Exception:
                pass

        state.data["action_confirmed"] = True
        state.data.pop("user_help_required", None)
        state.data.pop("paused_step_index", None)

        remaining_steps = steps[start_index:]
        if on_task_start:
            on_task_start(
                goal,
                [step.get("description") or f"Spustit tool {step.get('tool')}" for step in remaining_steps],
            )
        ctx_tool = ToolContext(
            dry_run=self.dry_run,
            agent_base_url=self.agent_base_url,
            workspace_root=self.workspace_root,
        )
        planner_inst = Planner(registry=self.registry)
        executor = Executor(
            registry=self.registry,
            ctx=ctx_tool,
            state=state,
            task_memory=task_memory,
            on_step_update=on_step_update,
            request_context=ctx if isinstance(ctx, RequestContext) else None,
            event_bus=self.event_bus,
            planner=planner_inst,
        )
        results = executor.run_plan(remaining_steps)


        if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
            if not ("paused_step_index" in state.data or state.data.get("user_help_required")):
                try:
                    ctx.transition_to(RequestStatus.VERIFYING, event_bus=self.event_bus)
                except Exception:
                    pass

        ok, summary, pending_confirmation = self._summarize_execution(results, state, len(steps), start_index)
        if ok:
            complete_current_request(result=summary, event_bus=self.event_bus)
        elif not pending_confirmation:
            fail_current_request(error=summary, event_bus=self.event_bus)
        else:
            if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                try:
                    ctx.transition_to(
                        RequestStatus.WAITING_FOR_USER,
                        event_bus=self.event_bus,
                        message=state.data.get("user_help_required", summary),
                    )
                except Exception:
                    pass

        return RuntimeResult(
            ok=ok,
            goal=goal,
            route="RESUME",
            confidence=1.0,
            steps=steps,
            results=results,
            state=state,
            summary=summary if not pending_confirmation else state.data.get("user_help_required", summary),
            request_id=getattr(ctx, "request_id", ""),
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
