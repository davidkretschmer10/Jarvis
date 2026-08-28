from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Dict, List, Callable, Optional

from tools.base import ToolContext
from tools.registry import ToolRegistry

from core.lifecycle import RequestContext, RequestStatus
from core.state import JarvisState
from core.template import render_templates
from core.task_memory import TaskMemory

JSON = Dict[str, Any]


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
    max_steps: int = 15
    max_retries: int = 0
    max_repairs: int = 1
    max_replans: int = 2


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

        while step_idx < len(current_steps):
            if total_executed_steps >= self.max_steps:
                err_msg = f"Překročen maximální počet kroků ({self.max_steps})."
                print(f"[EXECUTOR] {err_msg}")
                if self.request_context and not self.request_context.is_terminal:
                    self.request_context.transition_to(RequestStatus.FAILED, error=err_msg, event_bus=self.event_bus)
                self.state.data["user_help_required"] = err_msg
                break

            if self.request_context and (self.request_context.cancellation_requested or self.request_context.status == RequestStatus.CANCELLED):
                print(f"[EXECUTOR] Execution cancelled at step {step_idx+1}")
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

            # 1. Execute tool with retry for transient errors
            out = None
            for attempt in range(1 + self.max_retries):
                out = self.registry.run(tool_name, tool_input, self.ctx, self.state)
                if out.get("ok", False):
                    break
                err = str(out.get("error", ""))
                if "CONFIRMATION_REQUIRED" in err or "VisionError" in err:
                    break
                if attempt < self.max_retries:
                    print(f"[EXECUTOR] Step {step_idx+1} tool '{tool_name}' failed attempt {attempt+1}. Retrying...")

            # 2. Check execution outcome
            if not out.get("ok", False):
                error_msg = str(out.get("error", "Neznámá chyba"))

                # VisionError handling
                if "VisionError" in error_msg:
                    import logging
                    logging.getLogger(__name__).error("Vision error during execution: %s", error_msg)
                    czech_msg = "Vision systém není dostupný. Zkontrolujte instalaci OCR."
                    if self.task_memory:
                        self.task_memory.update_step_status(step_idx, "failed", czech_msg)
                    if self.on_step_update:
                        self.on_step_update(step_idx, "failed")
                    if self.request_context and not self.request_context.is_terminal:
                        self.request_context.transition_to(RequestStatus.FAILED, error=czech_msg, event_bus=self.event_bus)
                    self.state.data["user_help_required"] = czech_msg

                    self._update_state_after_step(
                        step_idx, tool_name, tool_input, {"ok": False, "error": "VisionError", "result": czech_msg}
                    )
                    results.append(
                        {
                            "step": step_idx + 1,
                            "tool": tool_name,
                            "input": tool_input,
                            "output": {"ok": False, "error": "VisionError", "result": czech_msg},
                            "state": self.state.snapshot(),
                        }
                    )
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

                # CONFIRMATION_REQUIRED handling
                if error_msg == "CONFIRMATION_REQUIRED":
                    if self.task_memory:
                        self.task_memory.update_step_status(step_idx, "paused")
                    if self.on_step_update:
                        self.on_step_update(step_idx, "paused")
                    if self.request_context and not self.request_context.is_terminal:
                        self.request_context.transition_to(
                            RequestStatus.WAITING_FOR_USER,
                            event_bus=self.event_bus,
                            message=out.get("message", "Akce vyžaduje potvrzení."),
                        )
                    self.state.data["paused_step_index"] = step_idx
                    self.state.data["user_help_required"] = out.get("message", "Akce vyžaduje potvrzení.")

                    self._update_state_after_step(step_idx, tool_name, tool_input, out)
                    results.append(
                        {
                            "step": step_idx + 1,
                            "tool": tool_name,
                            "input": tool_input,
                            "output": out,
                            "state": self.state.snapshot(),
                        }
                    )
                    if self.event_bus:
                        self.event_bus.emit(
                            "step_completed",
                            {
                                "request_id": self.request_context.request_id if self.request_context else "",
                                "step_index": step_idx + 1,
                                "tool": tool_name,
                                "ok": False,
                                "status": "paused",
                            },
                        )
                    break

                # 3. Auto-repair
                repaired = self._attempt_repair(step, error_msg)
                if repaired:
                    out = {
                        "ok": True,
                        "result": f"Krok selhal s chybou '{error_msg}', ale byl úspěšně opraven automatickou akcí.",
                    }
                    if self.task_memory:
                        self.task_memory.update_step_status(step_idx, "completed", str(out.get("result", "")))
                    if self.on_step_update:
                        self.on_step_update(step_idx, "completed")
                else:
                    # 4. Replanning fallback if repair failed
                    if replans_count < self.max_replans and self.planner and hasattr(self.planner, "replan"):
                        print(f"[EXECUTOR] Attempting replan ({replans_count + 1}/{self.max_replans})...")
                        goal_str = getattr(self.request_context, "goal", "") or self.state.last_output
                        new_sub_steps = self.planner.replan(goal_str, step, error_msg, self.state)
                        if new_sub_steps:
                            replans_count += 1
                            print(f"[EXECUTOR] Replan produced {len(new_sub_steps)} new steps.")
                            current_steps = current_steps[:step_idx] + new_sub_steps
                            if self.request_context:
                                self.request_context.total_steps = len(current_steps)
                            if self.task_memory:
                                self.task_memory.start_task(goal_str, current_steps)
                            if self.event_bus:
                                self.event_bus.emit("replanning_completed", {"new_steps": new_sub_steps, "replans_count": replans_count})
                            continue

                    # Mark step as failed if repair and replan failed
                    if self.task_memory:
                        self.task_memory.update_step_status(step_idx, "failed", error_msg)
                    if self.on_step_update:
                        self.on_step_update(step_idx, "failed")
                    if self.request_context and not self.request_context.is_terminal:
                        self.request_context.transition_to(RequestStatus.FAILED, error=error_msg, event_bus=self.event_bus)

                    self._update_state_after_step(step_idx, tool_name, tool_input, out)
                    results.append(
                        {
                            "step": step_idx + 1,
                            "tool": tool_name,
                            "input": tool_input,
                            "output": out,
                            "state": self.state.snapshot(),
                        }
                    )
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
                # Update status to completed
                if self.task_memory:
                    self.task_memory.update_step_status(step_idx, "completed", str(out.get("result", "")))
                if self.on_step_update:
                    self.on_step_update(step_idx, "completed")

            # State updates
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
                    },
                )

            # Debug logging
            print(f"[STEP {step_idx+1}] tool={tool_name}")
            print("[TOOL OUTPUT]", out)
            print("[STATE]", self.state.snapshot())

            results.append(
                {
                    "step": step_idx + 1,
                    "tool": tool_name,
                    "input": tool_input,
                    "output": out,
                    "state": self.state.snapshot(),
                }
            )
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
