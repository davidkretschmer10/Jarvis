from __future__ import annotations

import argparse
import json
import os

from core.executor import Executor
from core.planner import Planner
from tools.base import ToolContext
from tools.registry import ToolRegistry
from tools.pc_control import (
    AgentHealthTool,
    ClickTool,
    HotkeyTool,
    OpenAppTool,
    OpenWebsiteTool,
    PressKeyTool,
    ReadScreenTool,
    ScreenshotTool,
    WriteTextTool,
    SmartClickTool,
    SmartWriteTool,
    SmartCheckboxTool,
    CloseWindowTool,
    ConfirmDialogTool,
    CancelDialogTool,
    OpenSearchResultTool,
)
from tools.file_manager import ListDirTool, ReadTextFileTool, WriteTextFileTool
from core.state import JarvisState


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    # PC control tools (calls existing Flask agent on main PC)
    reg.register(AgentHealthTool())
    reg.register(OpenAppTool())
    reg.register(WriteTextTool())
    reg.register(ClickTool())
    reg.register(OpenWebsiteTool())
    reg.register(PressKeyTool())
    reg.register(HotkeyTool())
    reg.register(ScreenshotTool())
    reg.register(ReadScreenTool())
    # Smart PC control tools
    reg.register(SmartClickTool())
    reg.register(SmartWriteTool())
    reg.register(SmartCheckboxTool())
    reg.register(CloseWindowTool())
    reg.register(ConfirmDialogTool())
    reg.register(CancelDialogTool())
    reg.register(OpenSearchResultTool())
    # File tools (brain-side utility)
    reg.register(ListDirTool())
    reg.register(ReadTextFileTool())
    reg.register(WriteTextFileTool())
    from tools.pc_control import RefreshAppsTool
    reg.register(RefreshAppsTool())
    return reg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("goal", nargs="*", help="Goal for Jarvis to achieve")
    ap.add_argument("--dry-run", action="store_true", help="Plan and simulate tool calls only")
    ap.add_argument("--agent-url", default="http://127.0.0.1:5000", help="Local agent base URL")
    args = ap.parse_args()

    goal = " ".join(args.goal).strip()
    if not goal:
        raise SystemExit("Missing goal. Example: python run.py \"otevři chrome\"")

    from ai.engine import reset_current_request
    reset_current_request()

    reg = build_registry()
    planner = Planner(registry=reg)
    
    import time
    from core.intents.fast_command_router import (
        classify_routing_level,
        increment_router_stat,
        save_user_preference
    )
    from core.intents.target_extractor import normalize_text

    # 1. Routing classification
    start_time = time.perf_counter()
    route_info = classify_routing_level(goal)
    level = route_info["route"]
    confidence = route_info["confidence"]
    step = route_info["step"]
    candidates = route_info["candidates"]

    print(f"[ROUTER] {level}")

    # Handle confidence < 0.70 confirmation request
    if confidence < 0.70 and candidates:
        print(f"Nalezl jsem více možností:\n" + "\n".join([f"* {c}" for c in candidates]))
        try:
            import sys
            if sys.stdin.isatty():
                choice = input("Který chceš otevřít? ").strip()
                matched_candidate = None
                for cand in candidates:
                    if normalize_text(cand) in normalize_text(choice) or normalize_text(choice) in normalize_text(cand):
                        matched_candidate = cand
                        break
                if matched_candidate:
                    query_key = "prohlizec" if "prohlizec" in normalize_text(goal) else "browser"
                    save_user_preference(query_key, matched_candidate.lower())
                    print(f"Uložena preference: {matched_candidate}")
                    # re-classify
                    route_info = classify_routing_level(goal)
                    level = route_info["route"]
                    confidence = route_info["confidence"]
                    step = route_info["step"]
                else:
                    print("Neplatná volba.")
                    return
            else:
                print("Spusťte příkaz v interaktivním terminálu nebo nejprve zadejte konkrétnější název.")
                return
        except Exception as e:
            print(f"Chyba při vstupu: {e}")
            return

    steps = []
    use_task_memory = False
    fallback_occurred = False
    fallback_reason = None

    if level == "FAST_COMMAND":
        if step:
            steps = [step]
            from ai.engine import get_current_request
            req_id = get_current_request().request_id
            app_name = step["input"].get("name") or step["input"].get("url") or goal
            print(f"[FAST_COMMAND]\nSTART\n\nTool:\n{step['tool']}\n\nApplication:\n{app_name}\n\nConfidence:\n{confidence:.2f}\n\nRequest ID:\n{req_id}\n")
        else:
            level = "MINI_PLANNER"
            fallback_occurred = True
            fallback_reason = "FAST_COMMAND step was not generated"
            print(f"[ROUTER] FALLBACK FAST_COMMAND -> MINI_PLANNER: {fallback_reason}")

    if level == "MINI_PLANNER":
        try:
            steps = planner.plan(goal)
            if len(steps) > 5 or not steps:
                level = "PLANNER_V2"
                fallback_occurred = True
                fallback_reason = "plan contains more than 5 steps" if steps else "empty plan generated by MINI_PLANNER"
                print(f"[ROUTER] FALLBACK MINI_PLANNER -> PLANNER_V2: {fallback_reason}")
        except Exception as e:
            level = "PLANNER_V2"
            fallback_occurred = True
            fallback_reason = f"MINI_PLANNER planning exception: {e}"
            print(f"[ROUTER] FALLBACK MINI_PLANNER -> PLANNER_V2: {fallback_reason}")

    if level == "PLANNER_V2":
        use_task_memory = True
        steps = planner.plan(goal)

    if not steps:
        print("Chyba: Nepodařilo se vygenerovat plán.")
        return

    # Log metrics
    elapsed = time.perf_counter() - start_time
    tool_names = ", ".join([s.get("tool", "") for s in steps])
    print(f"[ROUTER]\n{level}\n\nTool:\n{tool_names}\n\nTime:\n{elapsed:.2f}s")

    # Increment statistics
    increment_router_stat(
        level=level,
        elapsed_time=elapsed,
        fallback=fallback_occurred,
        fallback_reason=fallback_reason
    )

    print("=== PLAN ===")
    print(json.dumps(steps, ensure_ascii=False, indent=2))

    ctx = ToolContext(
        dry_run=bool(args.dry_run),
        agent_base_url=str(args.agent_url),
        workspace_root=os.getcwd(),
    )
    state = JarvisState()
    
    # In run.py CLI, we can initialize TaskMemory only if use_task_memory is True
    task_memory = None
    if use_task_memory:
        from core.task_memory import TaskMemory
        task_memory = TaskMemory()
        
    executor = Executor(registry=reg, ctx=ctx, state=state, task_memory=task_memory)
    fast_duration = 0.0
    if level == "FAST_COMMAND":
        fast_start = time.perf_counter()
        
    results = executor.run_plan(steps)
    
    if level == "FAST_COMMAND":
        fast_duration = time.perf_counter() - fast_start
        success = results and not results[-1].get("output", {}).get("error") and results[-1].get("output", {}).get("ok", False)
        if success:
            from ai.engine import complete_current_request, get_current_request
            complete_current_request()
            req_id = get_current_request().request_id
            print(f"[FAST_COMMAND]\nEXECUTION_COMPLETE\n\nRequest ID:\n{req_id}\n\nDuration:\n{fast_duration:.2f}s\n\nResult:\nSUCCESS\n")
        else:
            from ai.engine import fail_current_request
            fail_current_request()

    print("=== RESULTS ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    print("=== FINAL STATE ===")
    print(json.dumps(state.snapshot(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
