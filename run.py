from __future__ import annotations

import argparse
import json

from core.runtime import JarvisRuntime
from tools.registry import ToolRegistry, build_default_registry


def build_registry() -> ToolRegistry:
    return build_default_registry()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("goal", nargs="*", help="Goal for Jarvis to achieve")
    ap.add_argument("--dry-run", action="store_true", help="Plan and simulate tool calls only")
    ap.add_argument("--agent-url", default="http://127.0.0.1:5000", help="Local agent base URL")
    args = ap.parse_args()

    goal = " ".join(args.goal).strip()
    if not goal:
        raise SystemExit('Missing goal. Example: python run.py "otevri chrome"')

    runtime = JarvisRuntime(
        registry=build_registry(),
        dry_run=bool(args.dry_run),
        agent_base_url=str(args.agent_url),
    )
    result = runtime.run_task(goal)

    print(f"[ROUTER] {result.route}")
    print(result.summary)
    print("=== PLAN ===")
    print(json.dumps(result.steps, ensure_ascii=False, indent=2))
    print("=== RESULTS ===")
    print(json.dumps(result.results, ensure_ascii=False, indent=2))
    print("=== FINAL STATE ===")
    print(json.dumps(result.state.snapshot(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
