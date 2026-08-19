import unittest
from unittest.mock import patch

from core.runtime import JarvisRuntime
from core.state import JarvisState
from tools.registry import ToolRegistry


class CaptureTool:
    name = "open_app"
    description = "Capture opened app."
    input_schema = {}

    def run(self, tool_input, ctx, state):
        state.data["opened"] = tool_input["name"]
        return {"ok": True, "result": tool_input["name"]}


class WebsiteTool:
    name = "open_website"
    description = "Capture opened URL."
    input_schema = {}

    def run(self, tool_input, ctx, state):
        state.data["url"] = tool_input["url"]
        return {"ok": True, "result": tool_input["url"]}


class ScreenshotTool:
    name = "screenshot"
    description = "Capture screenshot request."
    input_schema = {}

    def run(self, tool_input, ctx, state):
        return {"ok": True, "result": "screenshot"}


class ReadScreenTool:
    name = "read_screen"
    description = "Capture read screen request."
    input_schema = {}

    def run(self, tool_input, ctx, state):
        state.data["screen_text"] = "visible text"
        return {"ok": True, "result": "visible text"}


class RuntimeTests(unittest.TestCase):
    def make_runtime(self):
        registry = ToolRegistry()
        registry.register(CaptureTool())
        registry.register(WebsiteTool())
        registry.register(ScreenshotTool())
        registry.register(ReadScreenTool())
        return JarvisRuntime(registry=registry, dry_run=True)

    @patch("core.runtime.increment_router_stat")
    @patch("core.runtime.complete_current_request")
    @patch("core.runtime.reset_current_request")
    @patch("core.runtime.get_current_request")
    @patch("core.intents.fast_command_router.resolve_app_from_cache_with_score")
    def test_fast_command_open_app_uses_shared_state(self, resolve_app, request, reset, complete, stats):
        request.return_value.request_id = "req1"
        resolve_app.return_value = ("chrome", "C:/Apps/chrome.exe", 100)
        state = JarvisState()

        result = self.make_runtime().run_task("otevri Chrome", state=state)

        self.assertTrue(result.ok)
        self.assertEqual(result.route, "FAST_COMMAND")
        self.assertEqual(state.data["opened"], "chrome")

    @patch("core.runtime.increment_router_stat")
    @patch("core.runtime.complete_current_request")
    @patch("core.runtime.reset_current_request")
    @patch("core.runtime.get_current_request")
    def test_fast_command_search_uses_open_website(self, request, reset, complete, stats):
        request.return_value.request_id = "req2"

        result = self.make_runtime().run_task("vyhledej Nvidia")

        self.assertTrue(result.ok)
        self.assertEqual(result.steps[0]["tool"], "open_website")
        self.assertIn("nvidia", result.state.data["url"])

    @patch("core.runtime.increment_router_stat")
    @patch("core.runtime.complete_current_request")
    @patch("core.runtime.reset_current_request")
    @patch("core.runtime.get_current_request")
    def test_fast_command_screenshot_uses_registry_tool(self, request, reset, complete, stats):
        request.return_value.request_id = "req3"

        result = self.make_runtime().run_task("screenshot")

        self.assertTrue(result.ok)
        self.assertEqual(result.steps[0]["tool"], "screenshot")

    @patch("core.runtime.increment_router_stat")
    @patch("core.runtime.complete_current_request")
    @patch("core.runtime.reset_current_request")
    @patch("core.runtime.get_current_request")
    def test_fast_command_read_screen_uses_registry_tool(self, request, reset, complete, stats):
        request.return_value.request_id = "req4"

        result = self.make_runtime().run_task("precti obrazovku")

        self.assertTrue(result.ok)
        self.assertEqual(result.steps[0]["tool"], "read_screen")
        self.assertEqual(result.state.data["screen_text"], "visible text")

    @patch("core.runtime.Planner.plan")
    @patch("core.runtime.increment_router_stat")
    @patch("core.runtime.complete_current_request")
    @patch("core.runtime.reset_current_request")
    @patch("core.runtime.get_current_request")
    def test_compound_command_uses_planner_then_registry(self, request, reset, complete, stats, plan):
        request.return_value.request_id = "req5"
        plan.return_value = [
            {"tool": "open_app", "input": {"name": "chrome"}},
            {"tool": "open_website", "input": {"url": "https://www.google.com/search?q=Nvidia"}},
        ]

        result = self.make_runtime().run_task("otevri Chrome a vyhledej Nvidia")

        self.assertTrue(result.ok)
        self.assertEqual(result.route, "MINI_PLANNER")
        self.assertEqual(result.steps[0]["tool"], "open_app")
        self.assertEqual(result.steps[1]["tool"], "open_website")


if __name__ == "__main__":
    unittest.main()
