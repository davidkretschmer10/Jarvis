import unittest
from unittest.mock import patch
import io
import sys
from run import build_registry
from tools.registry import ToolRegistry
from tools.base import ToolContext, JSON

class TestPhase2_8(unittest.TestCase):
    def test_tool_registry_validation(self):
        # Build registry of all standard tools
        reg = build_registry()
        tools = reg.list()

        # Gather tool names to verify uniqueness
        names = []
        for tool in tools:
            # Verify name exists and is not empty
            name = getattr(tool, "name", None)
            self.assertIsNotNone(name, f"Tool {tool.__class__.__name__} is missing name")
            self.assertNotEqual(name, "", f"Tool {tool.__class__.__name__} has empty name")
            names.append(name)

            # Verify description exists
            description = getattr(tool, "description", None)
            self.assertIsNotNone(description, f"Tool {name} is missing description")
            self.assertNotEqual(description, "", f"Tool {name} has empty description")

            # Verify input_schema exists
            input_schema = getattr(tool, "input_schema", None)
            self.assertIsNotNone(input_schema, f"Tool {name} is missing input_schema")

        # Verify uniqueness of names
        self.assertEqual(len(names), len(set(names)), f"Tool names are not unique: {names}")

    def test_invalid_tool_bypassed_safely(self):
        # Create an invalid tool (missing name)
        class InvalidTool:
            description = "Test invalid tool"
            input_schema = {}
            def run(self, tool_input: JSON, ctx: ToolContext, state: any) -> JSON:
                return {}

        reg = ToolRegistry()
        
        # Capture stdout to verify printed warning
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            reg.register(InvalidTool())
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        
        # Verify it skipped registration without throwing ValueError
        self.assertEqual(len(reg.list()), 0)
        self.assertIn("Invalid tool:", output)
        self.assertIn("InvalidTool", output)
        self.assertIn("empty name", output)

if __name__ == "__main__":
    unittest.main()
