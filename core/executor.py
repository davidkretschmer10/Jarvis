from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import logging
import re
from typing import Any, Dict, List, Callable, Optional

from tools.base import ToolContext
from tools.registry import ToolRegistry

from core.lifecycle import RequestContext, RequestStatus
from core.state import JarvisState
from core.template import render_templates
from core.task_memory import TaskMemory
from core.verification import StepVerifierRegistry, VerificationStatus, VerificationResult
from core.observation import Observation, ObservationType

logger = logging.getLogger(__name__)

JSON = Dict[str, Any]


class StepExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    REPLANNED = "REPLANNED"
    TERMINAL_ERROR = "TERMINAL_ERROR"


class StepResult(dict):
    """
    Structured step result subclassing dict for 100% backwards compatibility
    with existing dict-based result consumers, while providing explicit
    execution statuses, verification tracking, and invariants.
    """

    def __init__(
        self,
        step_index: int,
        tool: str,
        input: Dict[str, Any],
        output: Dict[str, Any],
        status: StepExecutionStatus,
        execution_status: str,
        verification_status: str = "unverified",
        verification_evidence: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        state_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            step=step_index,
            tool=tool,
            input=input,
            output=output,
            status=status.value,
            execution_status=execution_status,
            verification_status=verification_status,
            verification_evidence=verification_evidence,
            error=error,
            state=state_snapshot,
        )
        self.step_index: int = step_index
        self.tool: str = tool
        self.tool_input: Dict[str, Any] = input
        self.output: Dict[str, Any] = output
        self.status: StepExecutionStatus = status
        self.execution_status: str = execution_status
        self.verification_status: str = verification_status
        self.verification_evidence: Optional[Dict[str, Any]] = verification_evidence
        self.error: Optional[str] = error
        self.state_snapshot: Optional[Dict[str, Any]] = state_snapshot

    @property
    def is_success(self) -> bool:
        return (
            self.status == StepExecutionStatus.SUCCESS
            and bool(self.output.get("ok", False))
            and self.verification_status != "FAILED"
        )


@dataclass
class Executor:
    registry: ToolRegistry
    ctx: ToolContext
    state: JarvisState
    task_memory: TaskMemory | None = None
    on_step_update: Callable[[int, str], None] | None = None
    request_context: RequestContext | None = None
    event_bus: Any = None
    planner: Any = None
    verifier: Any = None
    max_steps: int = 15
    max_retries: int = 0
    max_repairs: int = 1
    max_replans: int = 2

    def _is_cancelled(self) -> bool:
        if not self.request_context:
            return False
        return bool(
            getattr(self.request_context, "cancellation_requested", False) is True
            or getattr(self.request_context, "is_cancelled", False) is True
            or getattr(self.request_context, "status", None) == RequestStatus.CANCELLED
        )

    def run_plan(self, steps: List[JSON]) -> List[JSON]:
        results: List[JSON] = []

        if self.request_context:
            self.request_context.total_steps = len(steps)

        # If task memory is available, initialize/start task track
        if self.task_memory:
            self.task_memory.start_task(self.state.last_output or "Spuštění úkolu", steps)

        current_steps = list(steps)
        step_idx = 0
        total_executed_steps = 0
        replans_count = 0
        repairs_count = 0

        while step_idx < len(current_steps):
            # 1. Check maximum executed step limit (Timeout / Runaway safeguard)
            if total_executed_steps >= self.max_steps:
                err_msg = f"Překročen maximální počet kroků ({self.max_steps})."
                print(f"[EXECUTOR] {err_msg}")
                if self.request_context and not self.request_context.is_terminal:
                    self.request_context.transition_to(RequestStatus.FAILED, error=err_msg, event_bus=self.event_bus)
                self.state.data["user_help_required"] = err_msg
                break

            # 2. Check cancellation before step execution
            if self._is_cancelled():
                print(f"[EXECUTOR] Execution cancelled at step {step_idx+1}")
                if self.task_memory:
                    self.task_memory.update_step_status(step_idx, "cancelled")
                if self.on_step_update:
                    self.on_step_update(step_idx, "cancelled")
                if self.event_bus:
                    self.event_bus.emit(
                        "step_completed",
                        {
                            "request_id": self.request_context.request_id if self.request_context else "",
                            "step_index": step_idx + 1,
                            "tool": str(current_steps[step_idx].get("tool", "")),
                            "ok": False,
                            "status": "cancelled",
                            "error": "Request cancelled",
                        },
                    )
                break

            step = current_steps[step_idx]
            if self.request_context:
                self.request_context.current_step = step_idx + 1

            tool_name = str(step.get("tool", "")).strip()
            tool_input = step.get("input", {})
            if not isinstance(tool_input, dict):
                tool_input = {"value": tool_input}

            # Update status to in_progress
            if self.task_memory:
                self.task_memory.update_step_status(step_idx, "in_progress")
            if self.on_step_update:
                self.on_step_update(step_idx, "in_progress")
            if self.event_bus:
                self.event_bus.emit(
                    "step_started",
                    {
                        "request_id": self.request_context.request_id if self.request_context else "",
                        "step_index": step_idx + 1,
                        "tool": tool_name,
                        "description": step.get("description", ""),
                    },
                )

            # Render input templates
            tool_input = render_templates(tool_input, self.state)
            total_executed_steps += 1

            # 3. Execute tool with cooperative retry
            out = None
            cancelled_during_run = False

            for attempt in range(1 + self.max_retries):
                if self._is_cancelled():
                    cancelled_during_run = True
                    break

                out = self.registry.run(tool_name, tool_input, self.ctx, self.state)
                if out.get("ok", False):
                    break

                err = str(out.get("error", ""))
                if "CONFIRMATION_REQUIRED" in err or "VisionError" in err:
                    break

                if attempt < self.max_retries:
                    if self._is_cancelled():
                        cancelled_during_run = True
                        break
                    print(f"[EXECUTOR] Step {step_idx+1} tool '{tool_name}' failed attempt {attempt+1}. Retrying...")
                    if self.event_bus:
                        self.event_bus.emit(
                            "step_retry",
                            {
                                "request_id": self.request_context.request_id if self.request_context else "",
                                "step_index": step_idx + 1,
                                "tool": tool_name,
                                "attempt": attempt + 1,
                                "max_retries": self.max_retries,
                                "error": err,
                            },
                        )

            # Check if cancelled during tool execution / retry
            if cancelled_during_run or self._is_cancelled():
                print(f"[EXECUTOR] Execution cancelled during/after tool run at step {step_idx+1}")
                if self.task_memory:
                    self.task_memory.update_step_status(step_idx, "cancelled")
                if self.on_step_update:
                    self.on_step_update(step_idx, "cancelled")
                step_res = StepResult(
                    step_index=step_idx + 1,
                    tool=tool_name,
                    input=tool_input,
                    output=out or {"ok": False, "error": "Cancelled"},
                    status=StepExecutionStatus.CANCELLED,
                    execution_status="cancelled",
                    error="Execution cancelled",
                    state_snapshot=self.state.snapshot(),
                )
                results.append(step_res)
                if self.event_bus:
                    self.event_bus.emit(
                        "step_completed",
                        {
                            "request_id": self.request_context.request_id if self.request_context else "",
                            "step_index": step_idx + 1,
                            "tool": tool_name,
                            "ok": False,
                            "status": "cancelled",
                            "error": "Request cancelled",
                        },
                    )
                break

            out = out or {"ok": False, "error": "No output produced"}

            # 4. Observe & Verify (if tool execution succeeded)
            verification_status = "unverified"
            verification_evidence = None
            verification_result_obj = None
            step_observation = None

            if out.get("ok", False):
                if self._is_cancelled():
                    cancelled_during_run = True
                else:
                    if self.verifier is None:
                        self.verifier = StepVerifierRegistry()

                    req_id = self.request_context.request_id if self.request_context else ""
                    if self.event_bus:
                        self.event_bus.emit(
                            "verification_started",
                            {
                                "request_id": req_id,
                                "step_index": step_idx + 1,
                                "tool": tool_name,
                            },
                        )

                    v_res: VerificationResult = self.verifier.verify_step(
                        step, out, state=self.state, ctx=self.request_context
                    )
                    verification_result_obj = v_res

                    if self._is_cancelled():
                        cancelled_during_run = True
                    else:
                        if v_res.is_verified():
                            verification_status = "VERIFIED"
                            verification_evidence = v_res.evidence
                            if self.event_bus:
                                self.event_bus.emit(
                                    "verification_completed",
                                    {
                                        "request_id": req_id,
                                        "step_index": step_idx + 1,
                                        "tool": tool_name,
                                        "status": "VERIFIED",
                                        "message": v_res.message,
                                        "evidence": v_res.evidence,
                                    },
                                )
                        elif v_res.is_not_applicable():
                            verification_status = "NOT_APPLICABLE"
                            verification_evidence = v_res.evidence
                            if self.event_bus:
                                self.event_bus.emit(
                                    "verification_completed",
                                    {
                                        "request_id": req_id,
                                        "step_index": step_idx + 1,
                                        "tool": tool_name,
                                        "status": "NOT_APPLICABLE",
                                        "message": v_res.message,
                                    },
                                )
                        elif v_res.is_unknown():
                            # CRITICAL: UNKNOWN must NEVER be converted to VERIFIED
                            verification_status = "UNKNOWN"
                            verification_evidence = v_res.evidence
                            if self.event_bus:
                                self.event_bus.emit(
                                    "verification_completed",
                                    {
                                        "request_id": req_id,
                                        "step_index": step_idx + 1,
                                        "tool": tool_name,
                                        "status": "UNKNOWN",
                                        "message": v_res.message,
                                    },
                                )
                        elif v_res.is_failed():
                            # Verification FAILED! The tool claimed ok=True, but reality check failed!
                            verification_status = "FAILED"
                            verification_evidence = v_res.evidence
                            if self.event_bus:
                                self.event_bus.emit(
                                    "verification_failed",
                                    {
                                        "request_id": req_id,
                                        "step_index": step_idx + 1,
                                        "tool": tool_name,
                                        "status": "FAILED",
                                        "expected": v_res.expected,
                                        "observed": v_res.observed,
                                        "evidence": v_res.evidence,
                                        "message": v_res.message,
                                    },
                                )
                            # Step outcome is now FAILED
                            out = {
                                "ok": False,
                                "error": f"Verification failed: {v_res.message or v_res.observed}",
                                "verification": v_res.to_dict(),
                            }
                            step_observation = Observation(
                                source=v_res.verifier,
                                type=ObservationType.SYSTEM,
                                data={"expected": v_res.expected, "observed": v_res.observed},
                                evidence=v_res.evidence,
                            )

            # Check if cancelled during verification
            if cancelled_during_run or self._is_cancelled():
                print(f"[EXECUTOR] Execution cancelled during/after verification at step {step_idx+1}")
                if self.task_memory:
                    self.task_memory.update_step_status(step_idx, "cancelled")
                if self.on_step_update:
                    self.on_step_update(step_idx, "cancelled")
                step_res = StepResult(
                    step_index=step_idx + 1,
                    tool=tool_name,
                    input=tool_input,
                    output=out or {"ok": False, "error": "Cancelled"},
                    status=StepExecutionStatus.CANCELLED,
                    execution_status="cancelled",
                    verification_status=verification_status,
                    verification_evidence=verification_evidence,
                    error="Execution cancelled",
                    state_snapshot=self.state.snapshot(),
                )
                results.append(step_res)
                if self.event_bus:
                    self.event_bus.emit(
                        "step_completed",
                        {
                            "request_id": self.request_context.request_id if self.request_context else "",
                            "step_index": step_idx + 1,
                            "tool": tool_name,
                            "ok": False,
                            "status": "cancelled",
                            "error": "Request cancelled",
                        },
                    )
                break

            # 5. Check outcome & handle repair/replan if execution or verification failed
            if not out.get("ok", False):
                error_msg = str(out.get("error", "Neznámá chyba"))

                # Case A: VisionError handling
                if "VisionError" in error_msg:
                    logger.error("Vision error during execution: %s", error_msg)
                    czech_msg = "Vision systém není dostupný. Zkontrolujte instalaci OCR."
                    if self.task_memory:
                        self.task_memory.update_step_status(step_idx, "failed", czech_msg)
                    if self.on_step_update:
                        self.on_step_update(step_idx, "failed")
                    if self.request_context and not self.request_context.is_terminal:
                        self.request_context.transition_to(RequestStatus.FAILED, error=czech_msg, event_bus=self.event_bus)
                    self.state.data["user_help_required"] = czech_msg

                    failed_out = {"ok": False, "error": "VisionError", "result": czech_msg}
                    self._update_state_after_step(step_idx, tool_name, tool_input, failed_out)
                    step_res = StepResult(
                        step_index=step_idx + 1,
                        tool=tool_name,
                        input=tool_input,
                        output=failed_out,
                        status=StepExecutionStatus.FAILED,
                        execution_status="failed",
                        verification_status=verification_status,
                        verification_evidence=verification_evidence,
                        error=czech_msg,
                        state_snapshot=self.state.snapshot(),
                    )
                    results.append(step_res)
                    if self.event_bus:
                        self.event_bus.emit(
                            "step_completed",
                            {
                                "request_id": self.request_context.request_id if self.request_context else "",
                                "step_index": step_idx + 1,
                                "tool": tool_name,
                                "ok": False,
                                "error": czech_msg,
                            },
                        )
                    break

                # Case B: CONFIRMATION_REQUIRED handling
                if error_msg == "CONFIRMATION_REQUIRED":
                    req_id = self.request_context.request_id if self.request_context else ""
                    conf_message = out.get("message", "Akce vyžaduje potvrzení.")

                    if self.task_memory:
                        self.task_memory.update_step_status(step_idx, "paused")
                    if self.on_step_update:
                        self.on_step_update(step_idx, "paused")
                    if self.request_context and not self.request_context.is_terminal:
                        self.request_context.transition_to(
                            RequestStatus.WAITING_FOR_USER,
                            event_bus=self.event_bus,
                            message=conf_message,
                        )

                    self.state.data["paused_step_index"] = step_idx
                    self.state.data["user_help_required"] = conf_message
                    self.state.data["pending_confirmation"] = {
                        "request_id": req_id,
                        "step_index": step_idx,
                        "tool": tool_name,
                        "action": tool_input.get("action", ""),
                        "message": conf_message,
                    }

                    self._update_state_after_step(step_idx, tool_name, tool_input, out)
                    step_res = StepResult(
                        step_index=step_idx + 1,
                        tool=tool_name,
                        input=tool_input,
                        output=out,
                        status=StepExecutionStatus.WAITING_FOR_CONFIRMATION,
                        execution_status="waiting_for_confirmation",
                        verification_status=verification_status,
                        verification_evidence=verification_evidence,
                        error="CONFIRMATION_REQUIRED",
                        state_snapshot=self.state.snapshot(),
                    )
                    results.append(step_res)
                    if self.event_bus:
                        self.event_bus.emit(
                            "step_completed",
                            {
                                "request_id": req_id,
                                "step_index": step_idx + 1,
                                "tool": tool_name,
                                "ok": False,
                                "status": "paused",
                            },
                        )
                    break

                # Case C: Auto-repair (with cancellation & hard limit check)
                repaired = False
                if not self._is_cancelled() and repairs_count < self.max_repairs:
                    repairs_count += 1
                    if self.event_bus:
                        self.event_bus.emit(
                            "step_repair",
                            {
                                "request_id": self.request_context.request_id if self.request_context else "",
                                "step_index": step_idx + 1,
                                "repairs_count": repairs_count,
                                "max_repairs": self.max_repairs,
                                "error": error_msg,
                            },
                        )
                    repaired = self._attempt_repair(step, error_msg)

                    # CRITICAL: Re-verify after repair!
                    if repaired and not self._is_cancelled():
                        if self.verifier is None:
                            self.verifier = StepVerifierRegistry()
                        re_v_res = self.verifier.verify_step(step, out, state=self.state, ctx=self.request_context)
                        if re_v_res.is_failed():
                            repaired = False
                            error_msg = f"Re-verification failed after repair: {re_v_res.message or re_v_res.observed}"
                            verification_status = "FAILED"
                            verification_evidence = re_v_res.evidence
                            verification_result_obj = re_v_res
                            step_observation = Observation(
                                source=re_v_res.verifier,
                                type=ObservationType.SYSTEM,
                                data={"expected": re_v_res.expected, "observed": re_v_res.observed},
                                evidence=re_v_res.evidence,
                            )
                        elif re_v_res.is_verified():
                            verification_status = "VERIFIED"
                            verification_evidence = re_v_res.evidence
                        elif re_v_res.is_not_applicable():
                            verification_status = "NOT_APPLICABLE"
                        elif re_v_res.is_unknown():
                            verification_status = "UNKNOWN"
                            verification_evidence = re_v_res.evidence

                if self._is_cancelled():
                    print(f"[EXECUTOR] Execution cancelled after repair attempt at step {step_idx+1}")
                    if self.task_memory:
                        self.task_memory.update_step_status(step_idx, "cancelled")
                    if self.on_step_update:
                        self.on_step_update(step_idx, "cancelled")
                    step_res = StepResult(
                        step_index=step_idx + 1,
                        tool=tool_name,
                        input=tool_input,
                        output={"ok": False, "error": "Cancelled"},
                        status=StepExecutionStatus.CANCELLED,
                        execution_status="cancelled",
                        verification_status=verification_status,
                        verification_evidence=verification_evidence,
                        error="Execution cancelled",
                        state_snapshot=self.state.snapshot(),
                    )
                    results.append(step_res)
                    break

                if repaired:
                    out = {
                        "ok": True,
                        "result": f"Krok selhal s chybou '{error_msg}', ale byl úspěšně opraven a ověřen automatickou akcí.",
                    }
                    if self.task_memory:
                        self.task_memory.update_step_status(step_idx, "completed", str(out.get("result", "")))
                    if self.on_step_update:
                        self.on_step_update(step_idx, "completed")
                else:
                    # Case D: Replanning fallback (with cancellation & hard limit check)
                    if (
                        not self._is_cancelled()
                        and replans_count < self.max_replans
                        and self.planner
                        and hasattr(self.planner, "replan")
                    ):
                        print(f"[EXECUTOR] Attempting replan ({replans_count + 1}/{self.max_replans})...")
                        goal_str = getattr(self.request_context, "goal", "") or self.state.last_output
                        if self.event_bus:
                            self.event_bus.emit(
                                "replanning_started",
                                {
                                    "request_id": self.request_context.request_id if self.request_context else "",
                                    "step_index": step_idx + 1,
                                    "replans_count": replans_count + 1,
                                },
                            )
                        new_sub_steps = self.planner.replan(
                            goal_str,
                            step,
                            error_msg,
                            current_state=self.state,
                            observation=step_observation,
                            verification_result=verification_result_obj,
                            budget_info={
                                "repairs_remaining": self.max_repairs - repairs_count,
                                "replans_remaining": self.max_replans - replans_count,
                            },
                        )
                        if self._is_cancelled():
                            print(f"[EXECUTOR] Execution cancelled during replan at step {step_idx+1}")
                            break

                        if new_sub_steps:
                            replans_count += 1
                            print(f"[EXECUTOR] Replan produced {len(new_sub_steps)} new steps.")
                            current_steps = current_steps[:step_idx] + new_sub_steps
                            if self.request_context:
                                self.request_context.total_steps = len(current_steps)
                            if self.task_memory:
                                self.task_memory.start_task(goal_str, current_steps)
                            if self.event_bus:
                                self.event_bus.emit(
                                    "replanning_completed",
                                    {"new_steps": new_sub_steps, "replans_count": replans_count},
                                )
                            continue

                    # Case E: Terminal failure when repair and replan cannot recover
                    if self.task_memory:
                        self.task_memory.update_step_status(step_idx, "failed", error_msg)
                    if self.on_step_update:
                        self.on_step_update(step_idx, "failed")
                    if self.request_context and not self.request_context.is_terminal:
                        self.request_context.transition_to(RequestStatus.FAILED, error=error_msg, event_bus=self.event_bus)

                    self._update_state_after_step(step_idx, tool_name, tool_input, out)
                    step_res = StepResult(
                        step_index=step_idx + 1,
                        tool=tool_name,
                        input=tool_input,
                        output=out,
                        status=StepExecutionStatus.FAILED,
                        execution_status="failed",
                        verification_status=verification_status,
                        verification_evidence=verification_evidence,
                        error=error_msg,
                        state_snapshot=self.state.snapshot(),
                    )
                    results.append(step_res)
                    if self.event_bus:
                        self.event_bus.emit(
                            "step_completed",
                            {
                                "request_id": self.request_context.request_id if self.request_context else "",
                                "step_index": step_idx + 1,
                                "tool": tool_name,
                                "ok": False,
                                "error": error_msg,
                            },
                        )
                    break
            else:
                # Step was successful without repair
                if self.task_memory:
                    self.task_memory.update_step_status(step_idx, "completed", str(out.get("result", "")))
                if self.on_step_update:
                    self.on_step_update(step_idx, "completed")

            # Invariant check: only reached if step succeeded natively or was successfully auto-repaired
            if self._is_cancelled():
                print(f"[EXECUTOR] Execution cancelled right after step completion at step {step_idx+1}")
                break

            # State updates for successful step
            self._update_state_after_step(step_idx, tool_name, tool_input, out)

            if self.event_bus:
                self.event_bus.emit(
                    "step_completed",
                    {
                        "request_id": self.request_context.request_id if self.request_context else "",
                        "step_index": step_idx + 1,
                        "tool": tool_name,
                        "ok": True,
                        "result": out.get("result", ""),
                        "verification_status": verification_status,
                    },
                )

            # Debug logging
            print(f"[STEP {step_idx+1}] tool={tool_name}")
            print("[TOOL OUTPUT]", out)
            print("[STATE]", self.state.snapshot())

            step_res = StepResult(
                step_index=step_idx + 1,
                tool=tool_name,
                input=tool_input,
                output=out,
                status=StepExecutionStatus.SUCCESS,
                execution_status="completed",
                verification_status=verification_status,
                verification_evidence=verification_evidence,
                state_snapshot=self.state.snapshot(),
            )
            results.append(step_res)
            step_idx += 1
        return results


    def _update_state_after_step(self, i: int, tool_name: str, tool_input: JSON, out: JSON) -> None:
        self.state.last_output = out.get("result") if isinstance(out.get("result"), str) else str(out)
        self.state.tool_results.append({"step": i + 1, "tool": tool_name, "input": tool_input, "output": out})
        save = out.get("save_to_state")
        if isinstance(save, dict):
            self.state.data.update(save)
        created = out.get("created_files")
        if isinstance(created, list):
            for p in created:
                if isinstance(p, str) and p and p not in self.state.files:
                    self.state.files.append(p)

    def _attempt_repair(self, failed_step: JSON, error_msg: str) -> bool:
        """
        Queries Llama 3 to analyze the failed step and layout, and attempts to execute a repair action.
        Returns True if the repair succeeded and we can continue the plan.
        """
        if self._is_cancelled():
            return False
        print(f"[REPAIR] Step failed: {failed_step.get('tool')}. Error: {error_msg}")

        # 1. Capture screen and run UI detector
        from vision.ui_detector import UIDetector, VisionError

        try:
            detector = UIDetector()
            ui_response = detector.detect_screen()
            elements_desc = ""
            for el in ui_response.elements:
                elements_desc += f'- [{el.type}] text: "{el.text}" at [{el.x}, {el.y}, {el.width}, {el.height}]\n'
        except VisionError as ve:
            print(f"[REPAIR] VisionError during UI Detection: {ve}")
            self.state.data["user_help_required"] = "Vision systém není dostupný. Zkontrolujte instalaci OCR."
            return False
        except Exception as e:
            print(f"[REPAIR] UI Detection failed: {e}")
            elements_desc = "OCR/UI Elements info not available"

        # 2. Query Llama 3 for repair suggestion
        prompt = f"""Jsi modul pro automatickou opravu chyb v autonomním agentovi Jarvis.
Během plnění úkolu došlo k chybě. Tvým úkolem je analyzovat situaci a navrhnout jednu opravnou akci.

Krok, který selhal: {json.dumps(failed_step, ensure_ascii=False)}
Chybová zpráva: "{error_msg}"

Aktuální prvky detekované na obrazovce:
{elements_desc}

Pravidla pro opravu:
1. Pokud je problém v tom, že tlačítko nebylo nalezeno nebo má jiný text, můžeš navrhnout smart_click s jiným textem nebo jiným prvkem.
2. Pokud se okno nenačetlo, můžeš zkusit chvíli počkat (press_key na klávesu "null" nebo zopakovat krok).
3. Pokud navrhneš opravnou akci, vrať ji jako validní JSON objekt: {{"tool": "<název_toolu>", "input": {{...}}, "description": "Opravný krok: <popis>"}}
4. Pokud je chyba neopravitelná bez pomoci uživatele (např. vyžaduje zadání hesla, které neznáš, nebo došlo k fatální chybě), vrať JSON: {{"unrecoverable": true, "message": "<české vysvětlení pro uživatele a žádost o pomoc>"}}

Vrať POUZE validní JSON bez markdown uvozovek.
"""
        from ai.engine import ask_ai

        raw_res = ask_ai(prompt, chat_model="llama3")

        # Parse Llama response
        try:
            cleaned = raw_res.strip()
            # Find the JSON block
            json_match = re.search(r"(\{.*\})", cleaned, flags=re.DOTALL)
            if not json_match:
                print(f"[REPAIR] No JSON object found in response: {raw_res}")
                return False

            repair_action = json.loads(json_match.group(1))

            # Validate JSON object structure
            if not isinstance(repair_action, dict):
                print(f"[REPAIR] Parsed JSON is not a dictionary: {repair_action}")
                return False

            if repair_action.get("unrecoverable"):
                self.state.data["user_help_required"] = repair_action.get(
                    "message", "Došlo k chybě a je vyžadována vaše pomoc."
                )
                return False

            if "tool" not in repair_action:
                print(f"[REPAIR] Missing 'tool' key in repair action: {repair_action}")
                return False

            repair_tool = repair_action["tool"]
            # Validate that tool matches a registered tool name in the registry
            if not self.registry.get(repair_tool):
                print(f"[REPAIR] Tool '{repair_tool}' is not registered in registry.")
                return False

        except Exception as e:
            print(f"[REPAIR] Failed to parse/validate repair JSON: {e}. Raw: {raw_res}")
            return False

        print(f"[REPAIR] Running repair action: {repair_tool}")
        repair_input = repair_action.get("input", {})

        # Run repair action
        out = self.registry.run(repair_tool, repair_input, self.ctx, self.state)
        if out.get("ok"):
            print("[REPAIR] Repair action succeeded!")
            return True
        else:
            print(f"[REPAIR] Repair action failed: {out.get('error')}")
            return False
