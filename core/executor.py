from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Dict, List, Callable

from tools.base import ToolContext
from tools.registry import ToolRegistry

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

    def run_plan(self, steps: List[JSON]) -> List[JSON]:
        results: List[JSON] = []
        
        # If task memory is available, initialize/start task track
        if self.task_memory:
            # Convert planner steps format to task memory steps
            self.task_memory.start_task(self.state.last_output or "Spuštění úkolu", steps)

        for i, step in enumerate(steps):
            tool_name = str(step.get("tool", "")).strip()
            tool_input = step.get("input", {})
            if not isinstance(tool_input, dict):
                tool_input = {"value": tool_input}

            # Update status to in_progress
            if self.task_memory:
                self.task_memory.update_step_status(i, "in_progress")
            if self.on_step_update:
                self.on_step_update(i, "in_progress")

            # Allow the plan to reference previous outputs using templates
            tool_input = render_templates(tool_input, self.state)

            out = self.registry.run(tool_name, tool_input, self.ctx, self.state)

            # Check for failure and try to repair
            if not out.get("ok", False):
                error_msg = str(out.get("error", "Neznámá chyba"))
                
                # Check for VisionError
                if "VisionError" in error_msg:
                    import logging
                    logging.getLogger(__name__).error("Vision error during execution: %s", error_msg)
                    czech_msg = "Vision systém není dostupný. Zkontrolujte instalaci OCR."
                    if self.task_memory:
                        self.task_memory.update_step_status(i, "failed", czech_msg)
                    if self.on_step_update:
                        self.on_step_update(i, "failed")
                    self.state.data["user_help_required"] = czech_msg
                    
                    self._update_state_after_step(i, tool_name, tool_input, {"ok": False, "error": "VisionError", "result": czech_msg})
                    results.append({
                        "step": i + 1,
                        "tool": tool_name,
                        "input": tool_input,
                        "output": {"ok": False, "error": "VisionError", "result": czech_msg},
                        "state": self.state.snapshot(),
                    })
                    break

                # Check for CONFIRMATION_REQUIRED
                if error_msg == "CONFIRMATION_REQUIRED":
                    if self.task_memory:
                        self.task_memory.update_step_status(i, "paused")
                    if self.on_step_update:
                        self.on_step_update(i, "paused")
                    self.state.data["paused_step_index"] = i
                    self.state.data["user_help_required"] = out.get("message", "Akce vyžaduje potvrzení.")
                    
                    self._update_state_after_step(i, tool_name, tool_input, out)
                    results.append({
                        "step": i + 1,
                        "tool": tool_name,
                        "input": tool_input,
                        "output": out,
                        "state": self.state.snapshot(),
                    })
                    break

                # Try auto-repair
                repaired = self._attempt_repair(step, error_msg)
                if repaired:
                    out = {"ok": True, "result": f"Krok selhal s chybou '{error_msg}', ale byl úspěšně opraven automatickou akcí."}
                    if self.task_memory:
                        self.task_memory.update_step_status(i, "completed", str(out.get("result", "")))
                    if self.on_step_update:
                        self.on_step_update(i, "completed")
                else:
                    # Mark step as failed
                    if self.task_memory:
                        self.task_memory.update_step_status(i, "failed", error_msg)
                    if self.on_step_update:
                        self.on_step_update(i, "failed")
                    
                    # Store step results and break
                    self._update_state_after_step(i, tool_name, tool_input, out)
                    results.append({
                        "step": i + 1,
                        "tool": tool_name,
                        "input": tool_input,
                        "output": out,
                        "state": self.state.snapshot(),
                    })
                    break
            else:
                # Update status to completed
                if self.task_memory:
                    self.task_memory.update_step_status(i, "completed", str(out.get("result", "")))
                if self.on_step_update:
                    self.on_step_update(i, "completed")

            # State updates
            self._update_state_after_step(i, tool_name, tool_input, out)

            # Debug logging
            print(f"[STEP {i+1}] tool={tool_name}")
            print("[TOOL OUTPUT]", out)
            print("[STATE]", self.state.snapshot())

            results.append(
                {
                    "step": i + 1,
                    "tool": tool_name,
                    "input": tool_input,
                    "output": out,
                    "state": self.state.snapshot(),
                }
            )
        return results

    def _update_state_after_step(self, i: int, tool_name: str, tool_input: JSON, out: JSON) -> None:
        self.state.last_output = out.get("result") if isinstance(out.get("result"), str) else str(out)
        self.state.tool_results.append(
            {"step": i + 1, "tool": tool_name, "input": tool_input, "output": out}
        )
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
                elements_desc += f"- [{el.type}] text: \"{el.text}\" at [{el.x}, {el.y}, {el.width}, {el.height}]\n"
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
                self.state.data["user_help_required"] = repair_action.get("message", "Došlo k chybě a je vyžadována vaše pomoc.")
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
