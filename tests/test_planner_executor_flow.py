import unittest
from unittest.mock import patch

from core.executor import Executor
from core.planner import Planner
from core.state import JarvisState
from tools.base import ToolContext
from tools.registry import ToolRegistry


class SaveTool:
    name = "save_value"
    description = "Save a value to state."
    input_schema = {}

    def run(self, tool_input, ctx, state):
        return {
            "ok": True,
            "result": tool_input["value"],
            "save_to_state": {"saved": tool_input["value"]},
        }


class EchoTool:
    name = "echo"
    description = "Echo a value."
    input_schema = {}

    def run(self, tool_input, ctx, state):
        return {"ok": True, "result": tool_input["value"]}


class PlannerExecutorFlowTests(unittest.TestCase):
    def test_planner_extracts_json_steps(self):
        registry = ToolRegistry()
        registry.register(EchoTool())

        with patch("ai.engine.ask_ai", return_value='plan:\n[{"tool":"echo","input":{"value":"hi"}}]'):
            steps = Planner(registry).plan("say hi")

        self.assertEqual(steps, [{"tool": "echo", "input": {"value": "hi"}}])

    def test_executor_renders_state_templates_between_steps(self):
        registry = ToolRegistry()
        registry.register(SaveTool())
        registry.register(EchoTool())
        state = JarvisState()
        executor = Executor(registry, ToolContext(dry_run=True), state)

        results = executor.run_plan(
            [
                {"tool": "save_value", "input": {"value": "first"}},
                {"tool": "echo", "input": {"value": "{{state.data.saved}}"}},
            ]
        )

        self.assertEqual(results[-1]["output"]["result"], "first")
        self.assertEqual(state.data["saved"], "first")
        self.assertEqual(len(state.tool_results), 2)


if __name__ == "__main__":
    unittest.main()
