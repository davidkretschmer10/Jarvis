import unittest

from tools.base import ToolContext
from tools.registry import ToolRegistry


class DummyTool:
    name = "dummy"
    description = "Dummy tool for registry tests."
    input_schema = {}

    def run(self, tool_input, ctx, state):
        return {"result": tool_input.get("value", "ok")}


class ToolRegistryTests(unittest.TestCase):
    def test_register_and_run_tool(self):
        registry = ToolRegistry()
        registry.register(DummyTool())

        result = registry.run("dummy", {"value": "done"}, ToolContext(dry_run=True), None)

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "done")

    def test_duplicate_tool_is_rejected(self):
        registry = ToolRegistry()
        registry.register(DummyTool())
        registry.register(DummyTool())
        self.assertEqual(len(registry.list()), 1)

    def test_unknown_tool_returns_error(self):
        result = ToolRegistry().run("missing", {}, ToolContext(dry_run=True), None)

        self.assertFalse(result["ok"])
        self.assertIn("Unknown tool", result["error"])


if __name__ == "__main__":
    unittest.main()
