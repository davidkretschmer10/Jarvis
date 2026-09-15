from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
import time
from typing import Any, Callable, Dict, List, Optional

from core.executor import Executor, StepExecutionStatus
from core.intents.fast_command_router import classify_routing_level, increment_router_stat
from core.lifecycle import (
    RequestContext,
    RequestStatus,
    cancel_current_request,
    complete_current_request,
    fail_current_request,
    get_current_request,
    reset_current_request,
    set_current_request,
)
from core.planner import Planner
from core.state import JarvisState
from core.task_memory import TaskMemory
from tools.base import ToolContext
from tools.registry import ToolRegistry, build_default_registry
from core.security_policy import ActionRisk, PolicyDecision, ResourceScope, SecurityPolicy, ToolCapability
from core.confirmation import ConfirmationManager, ConfirmationRequest, ConfirmationStatus
from core.action_audit import ActionAuditLogger, get_audit_logger


JSON = Dict[str, Any]
StepCallback = Callable[[int, str], None]
TaskStartCallback = Callable[[str, List[str]], None]


class RequestExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    PAUSED = "PAUSED"
    TIMEOUT = "TIMEOUT"
    REPLANNED = "REPLANNED"
    TERMINAL_ERROR = "TERMINAL_ERROR"
    CHAT_RESPONSE = "CHAT_RESPONSE"


@dataclass
class RequestResult:
    ok: bool
    goal: str
    route: str
    confidence: float
    steps: List[JSON] = field(default_factory=list)
    results: List[JSON] = field(default_factory=list)
    state: JarvisState = field(default_factory=JarvisState)
    summary: str = ""
    request_id: str = ""
    status: RequestExecutionStatus | str = RequestExecutionStatus.COMPLETED
    response_text: str = ""
    execution_result: Optional[List[JSON]] = None
    verification_summary: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    pending_confirmation: bool = False
    confirmation_message: str = ""
    fallback_occurred: bool = False
    fallback_reason: Optional[str] = None

    def __post_init__(self):
        if not self.response_text and self.summary:
            self.response_text = self.summary
        elif not self.summary and self.response_text:
            self.summary = self.response_text
        if self.execution_result is None and self.results:
            self.execution_result = self.results
        elif self.results is None and self.execution_result:
            self.results = self.execution_result
        if isinstance(self.status, RequestExecutionStatus):
            self.status = self.status.value


RuntimeResult = RequestResult


class JarvisRuntime:
    """Single task runtime shared by CLI, GUI, and voice entry points."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        agent_base_url: str = "http://127.0.0.1:5000",
        workspace_root: Optional[str] = None,
        dry_run: bool = False,
        event_bus: Any = None,
        security_policy: Optional[SecurityPolicy] = None,
        confirmation_manager: Optional[ConfirmationManager] = None,
        audit_logger: Optional[ActionAuditLogger] = None,
    ) -> None:
        self.registry = registry or build_default_registry()
        self.agent_base_url = agent_base_url
        self.workspace_root = workspace_root or os.getcwd()
        self.dry_run = dry_run
        self.event_bus = event_bus
        self.security_policy = security_policy or SecurityPolicy()
        self.confirmation_manager = confirmation_manager or ConfirmationManager()
        self.audit_logger = audit_logger or get_audit_logger()

    def cancel_task(self, request_id: Optional[str] = None, reason: Optional[str] = None) -> None:
        """Cancel current or specified request and invalidate any pending confirmation tokens."""
        req_id = request_id or getattr(get_current_request(), "request_id", "")
        if req_id and hasattr(self, "confirmation_manager"):
            self.confirmation_manager.invalidate_request(req_id)
        cancel_current_request(reason=reason, event_bus=self.event_bus)

    def run_task(
        self,
        goal: str,
        state: Optional[JarvisState] = None,
        task_memory: Optional[TaskMemory] = None,
        on_step_update: Optional[StepCallback] = None,
        on_task_start: Optional[TaskStartCallback] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        reset_request: bool = True,
        request_context: Optional[RequestContext] = None,
    ) -> RequestResult:
        if request_context is not None:
            ctx = request_context
            set_current_request(ctx)
            if hasattr(ctx, "goal") and not ctx.goal:
                ctx.goal = goal
        elif reset_request:
            ctx = reset_current_request(goal=goal, source="runtime")
        else:
            ctx = get_current_request()
            if hasattr(ctx, "goal"):
                ctx.goal = goal

        request_id = getattr(ctx, "request_id", "")
        state = state or JarvisState()

        # Invariant: Do not execute if request context is already cancelled or terminal
        if (
            getattr(ctx, "is_cancelled", False) is True
            or getattr(ctx, "cancellation_requested", False) is True
            or getattr(ctx, "is_terminal", False) is True
            or getattr(ctx, "status", None) in (RequestStatus.CANCELLED, RequestStatus.COMPLETED, RequestStatus.FAILED)
        ):
            term_status = getattr(getattr(ctx, "status", None), "value", "CANCELLED")
            is_cancelled = (
                getattr(ctx, "is_cancelled", False) is True
                or getattr(ctx, "cancellation_requested", False) is True
                or "CANCEL" in term_status
            )
            cancel_msg = "Ukol byl pred zahajenim zrusen." if is_cancelled else f"Ukol byl odmitnut: request je jiz ve stavu {term_status}."
            return RequestResult(
                ok=False,
                goal=goal,
                route="CANCELLED",
                confidence=1.0,
                steps=[],
                results=[],
                state=state,
                summary=cancel_msg,
                request_id=request_id,
                status=RequestExecutionStatus.CANCELLED if is_cancelled else RequestExecutionStatus.FAILED,
                error=cancel_msg,
            )

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

            return RequestResult(
                ok=False,
                goal=goal,
                route=level,
                confidence=confidence,
                steps=[],
                results=[],
                state=state,
                summary=message,
                request_id=request_id,
                status=RequestExecutionStatus.WAITING_FOR_CONFIRMATION,
                response_text=message,
                pending_confirmation=True,
                confirmation_message=message,
            )

        # --- CHAT MODE (Pure conversational / inquiry request without tools) ---
        if level == "CHAT":
            self._emit("route_selected", {"route": "CHAT", "confidence": confidence})
            if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                try:
                    ctx.transition_to(RequestStatus.EXECUTING, event_bus=self.event_bus)
                except Exception:
                    pass

            full_reply = ""
            if on_chunk:
                from ai.engine import generate_stream
                try:
                    for chunk in generate_stream(goal):
                        if (
                            getattr(ctx, "is_cancelled", False) is True
                            or getattr(ctx, "cancellation_requested", False) is True
                        ):
                            break
                        full_reply += chunk
                        on_chunk(chunk)
                except Exception as e:
                    full_reply = f"Chyba při generování odpovědi: {e}"
            else:
                from ai.engine import ask_ai
                try:
                    full_reply = ask_ai(goal) or "Omlouvám se, nepodařilo se vygenerovat odpověď."
                except Exception as e:
                    full_reply = f"Chyba při komunikaci s AI: {e}"

            if getattr(ctx, "is_cancelled", False) is True or getattr(ctx, "cancellation_requested", False) is True:
                cancel_current_request(reason="Chat zrušen.", event_bus=self.event_bus)
                status = RequestExecutionStatus.CANCELLED
                ok = False
            else:
                complete_current_request(result=full_reply, event_bus=self.event_bus)
                status = RequestExecutionStatus.CHAT_RESPONSE
                ok = True

            result = RequestResult(
                ok=ok,
                goal=goal,
                route="CHAT",
                confidence=confidence,
                steps=[],
                results=[],
                state=state,
                summary=full_reply,
                request_id=request_id,
                status=status,
                response_text=full_reply,
                execution_result=[],
            )
            self._emit("task_finished", result)
            return result

        # --- PLANNING or DIRECT EXECUTING (Action / Mixed) ---
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

        if level in ("PLANNER_V2", "MIXED"):
            use_task_memory = True
            if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                try:
                    ctx.transition_to(RequestStatus.PLANNING, event_bus=self.event_bus)
                except Exception:
                    pass
            steps = Planner(registry=self.registry).plan(goal)

        if steps and level in ("MINI_PLANNER", "PLANNER_V2", "MIXED"):
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
            return RequestResult(
                ok=False,
                goal=goal,
                route=level,
                confidence=confidence,
                steps=[],
                results=[],
                state=state,
                summary=summary,
                request_id=request_id,
                status=RequestExecutionStatus.FAILED,
                error=summary,
                fallback_occurred=fallback_occurred,
                fallback_reason=fallback_reason,
            )

        ctx_tool = ToolContext(
            dry_run=self.dry_run,
            agent_base_url=self.agent_base_url,
            workspace_root=self.workspace_root,
            request_context=ctx if isinstance(ctx, RequestContext) else None,
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
            security_policy=self.security_policy,
            confirmation_manager=self.confirmation_manager,
            audit_logger=self.audit_logger,
        )
        results = executor.run_plan(steps)

        # --- VERIFYING ---
        if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
            if not ("paused_step_index" in state.data or state.data.get("user_help_required")):
                try:
                    ctx.transition_to(RequestStatus.VERIFYING, event_bus=self.event_bus)
                except Exception:
                    pass

        ok, summary, pending_confirmation = self._summarize_execution(results, state, len(steps), ctx=ctx)

        # --- COMPLETING / FAILING / WAITING / CANCELLING ---
        if pending_confirmation:
            confirmation_message = state.data.get("user_help_required", "Akce vyzaduje potvrzeni.")
            summary = confirmation_message
            status = RequestExecutionStatus.WAITING_FOR_CONFIRMATION
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
            status = RequestExecutionStatus.COMPLETED
        elif (
            getattr(ctx, "is_cancelled", False) is True
            or getattr(ctx, "cancellation_requested", False) is True
            or getattr(ctx, "status", None) == RequestStatus.CANCELLED
        ):
            cancel_current_request(reason=summary, event_bus=self.event_bus)
            status = RequestExecutionStatus.CANCELLED
        elif any(r.get("verification_status") == "UNKNOWN" or r.get("status") == "UNKNOWN" for r in results):
            fail_current_request(error=summary, event_bus=self.event_bus)
            status = RequestExecutionStatus.UNKNOWN
        else:
            fail_current_request(error=summary, event_bus=self.event_bus)
            status = RequestExecutionStatus.FAILED

        result = RequestResult(
            ok=ok,
            goal=goal,
            route=level,
            confidence=confidence,
            steps=steps,
            results=results,
            state=state,
            summary=summary,
            request_id=request_id,
            status=status,
            response_text=summary,
            execution_result=results,
            error=summary if not ok and status != RequestExecutionStatus.WAITING_FOR_CONFIRMATION else None,
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
        expected_request_id: Optional[str] = None,
        request_context: Optional[RequestContext] = None,
    ) -> RuntimeResult:
        if request_context is not None:
            ctx = request_context
            set_current_request(ctx)
        else:
            ctx = get_current_request()

        # Invariant: Terminal requests cannot be resumed
        if getattr(ctx, "is_terminal", False):
            raise RuntimeError(
                f"Cannot resume request '{getattr(ctx, 'request_id', '')}' in terminal state '{getattr(ctx, 'status', '')}'."
            )

        # Invariant: Validate confirmation binding
        pending_conf = state.data.get("pending_confirmation")
        req_id = expected_request_id or getattr(ctx, "request_id", "")
        if expected_request_id:
            if pending_conf and pending_conf.get("request_id") and pending_conf.get("request_id") != expected_request_id:
                raise ValueError(
                    f"Confirmation mismatch: expected request_id {expected_request_id}, "
                    f"but pending confirmation is for {pending_conf.get('request_id')}"
                )
            if getattr(ctx, "request_id", "") and getattr(ctx, "request_id", "") != expected_request_id:
                raise ValueError(
                    f"Confirmation mismatch: expected request_id {expected_request_id}, "
                    f"but current context request_id is {getattr(ctx, 'request_id', '')}"
                )

        remaining_steps = steps[start_index:]
        step_number = start_index + 1
        tool_name = remaining_steps[0].get("tool") if remaining_steps else None
        if not tool_name and pending_conf:
            tool_name = pending_conf.get("tool")

        # Authorize token in ConfirmationManager and check expiration
        if tool_name and req_id:
            conf = self.confirmation_manager.get_confirmation(req_id, step_number, tool_name)
            if conf:
                if conf.is_expired:
                    raise ValueError(f"Confirmation for step {step_number} has expired.")
                conf.approve()
            else:
                if pending_conf and pending_conf.get("expires_at"):
                    if time.time() >= pending_conf["expires_at"]:
                        raise ValueError(f"Confirmation for step {step_number} has expired.")
                self.confirmation_manager.create_confirmation(
                    request_id=req_id,
                    step_id=step_number,
                    tool=tool_name,
                    capability=ToolCapability.UNKNOWN,
                    risk=ActionRisk.HIGH,
                    resource=None,
                    summary="Approved via resume",
                ).approve()

        if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
            try:
                ctx.transition_to(RequestStatus.EXECUTING, event_bus=self.event_bus, start_index=start_index)
            except Exception:
                pass

        state.data["action_confirmed"] = True
        state.data["action_authorized"] = True
        state.data.pop("user_help_required", None)
        state.data.pop("paused_step_index", None)
        state.data.pop("pending_confirmation", None)

        if on_task_start:
            on_task_start(
                goal,
                [step.get("description") or f"Spustit tool {step.get('tool')}" for step in remaining_steps],
            )
        ctx_tool = ToolContext(
            dry_run=self.dry_run,
            agent_base_url=self.agent_base_url,
            workspace_root=self.workspace_root,
            request_context=ctx if isinstance(ctx, RequestContext) else None,
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
            security_policy=self.security_policy,
            confirmation_manager=self.confirmation_manager,
            audit_logger=self.audit_logger,
        )
        results = executor.run_plan(remaining_steps)

        if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
            if not ("paused_step_index" in state.data or state.data.get("user_help_required")):
                try:
                    ctx.transition_to(RequestStatus.VERIFYING, event_bus=self.event_bus)
                except Exception:
                    pass

        ok, summary, pending_confirmation = self._summarize_execution(results, state, len(steps), start_index, ctx=ctx)
        if pending_confirmation:
            if hasattr(ctx, "transition_to") and not getattr(ctx, "is_terminal", False):
                try:
                    ctx.transition_to(
                        RequestStatus.WAITING_FOR_USER,
                        event_bus=self.event_bus,
                        message=state.data.get("user_help_required", summary),
                    )
                except Exception:
                    pass
        if pending_confirmation:
            status = RequestExecutionStatus.WAITING_FOR_CONFIRMATION
        elif ok:
            complete_current_request(result=summary, event_bus=self.event_bus)
            status = RequestExecutionStatus.COMPLETED
        elif (
            getattr(ctx, "is_cancelled", False) is True
            or getattr(ctx, "cancellation_requested", False) is True
            or getattr(ctx, "status", None) == RequestStatus.CANCELLED
        ):
            cancel_current_request(reason=summary, event_bus=self.event_bus)
            status = RequestExecutionStatus.CANCELLED
        elif any(r.get("verification_status") == "UNKNOWN" or r.get("status") == "UNKNOWN" for r in results):
            fail_current_request(error=summary, event_bus=self.event_bus)
            status = RequestExecutionStatus.UNKNOWN
        else:
            fail_current_request(error=summary, event_bus=self.event_bus)
            status = RequestExecutionStatus.FAILED

        resp_text = summary if not pending_confirmation else state.data.get("user_help_required", summary)
        result = RuntimeResult(
            ok=ok,
            goal=goal,
            route="RESUME",
            confidence=1.0,
            steps=steps,
            results=results,
            state=state,
            summary=resp_text,
            request_id=getattr(ctx, "request_id", ""),
            status=status,
            response_text=resp_text,
            execution_result=results,
            error=summary if not ok and status != RequestExecutionStatus.WAITING_FOR_CONFIRMATION else None,
            pending_confirmation=pending_confirmation,
            confirmation_message=state.data.get("user_help_required", ""),
        )
        self._emit("task_finished", result)
        return result

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
        ctx: Optional[RequestContext] = None,
    ) -> tuple[bool, str, bool]:
        # 1. Check if request context is cancelled
        if ctx is not None:
            if (
                getattr(ctx, "is_cancelled", False) is True
                or getattr(ctx, "cancellation_requested", False) is True
                or getattr(ctx, "status", None) == RequestStatus.CANCELLED
            ):
                return False, "Ukol byl zrusen pred dokoncenim.", False

        # 2. Check if confirmation is pending or paused
        if "paused_step_index" in state.data:
            return False, state.data.get("user_help_required", "Akce vyzaduje potvrzeni."), True

        help_required = state.data.get("user_help_required")
        if help_required:
            return False, f"Chyba behem provadeni: {help_required}", False

        # 3. If no steps were executed or results is empty when steps were expected
        if total_steps > 0 and not results:
            return False, "Nebyly provedeny zadne kroky.", False

        # 4. Check if any executed step failed / cancelled / timed out or verification failed
        has_unknown = False
        for idx, res in enumerate(results):
            out = res.get("output", {})
            status = res.get("status")
            v_status = res.get("verification_status")

            if status in ("CANCELLED", StepExecutionStatus.CANCELLED.value):
                return False, f"Ukol byl zrusen na kroku {start_index + idx + 1}.", False
            if status in ("TIMEOUT", StepExecutionStatus.TIMEOUT.value):
                return False, f"Ukol vyprsel (timeout) na kroku {start_index + idx + 1}.", False
            if v_status == "FAILED" or status in ("FAILED", StepExecutionStatus.FAILED.value) or not out.get("ok", False):
                step_no = start_index + idx + 1
                error = out.get("error", "Overeni vysledku akce selhalo")
                return False, f"Ukol selhal na kroku {step_no}: {error}", False
            if v_status == "UNKNOWN" or status == "UNKNOWN":
                has_unknown = True

        # 5. Check completed count vs total planned steps
        executed_count = len(results)
        if total_steps > 0 and (start_index + executed_count) < total_steps:
            return False, f"Ukol nebyl dokoncen: provedeno {start_index + executed_count} z {total_steps} kroku.", False

        if has_unknown:
            return False, f"Ukol byl proveden, ale overeni kroku zustalo UNKNOWN. Provedeno {total_steps} kroku.", False
        return True, f"Ukol byl uspesne dokoncen a overen! Celkem provedeno {total_steps} kroku.", False

    def _emit(self, event_name: str, data: Any) -> None:
        if self.event_bus is not None:
            self.event_bus.emit(event_name, data)
