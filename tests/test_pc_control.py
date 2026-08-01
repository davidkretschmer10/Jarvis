import unittest
from unittest.mock import Mock, patch

from tools.base import ToolContext
from tools.pc_control import ClickTool, HotkeyTool, ScreenshotTool, _post_agent


class PcControlToolTests(unittest.TestCase):
    def test_post_agent_marks_agent_error_as_not_ok(self):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {"ok": False, "result": "ERROR: missing app"}

        with patch("tools.pc_control.requests.post", return_value=response):
            result = _post_agent(ToolContext(), "open", "missing")

        self.assertFalse(result["ok"])

    def test_click_tool_sends_coordinates_when_present(self):
        with patch("tools.pc_control._post_agent", return_value={"ok": True}) as post:
            result = ClickTool().run({"x": 10, "y": 20, "button": "left", "clicks": 2}, ToolContext(), None)

        self.assertEqual(result["result"], {"ok": True})
        post.assert_called_once_with(
            unittest.mock.ANY,
            "click",
            {"x": 10, "y": 20, "button": "left", "clicks": 2},
        )

    def test_hotkey_tool_normalizes_single_value_to_list(self):
        with patch("tools.pc_control._post_agent", return_value={"ok": True}) as post:
            HotkeyTool().run({"keys": "enter"}, ToolContext(), None)

        post.assert_called_once_with(unittest.mock.ANY, "hotkey", ["enter"])

    def test_screenshot_tool_saves_path_to_state(self):
        agent_result = {"ok": True, "data": {"result": {"path": "screenshots/test.png"}}}
        with patch("tools.pc_control._post_agent", return_value=agent_result):
            result = ScreenshotTool().run({}, ToolContext(), None)

        self.assertEqual(result["created_files"], ["screenshots/test.png"])
        self.assertEqual(result["save_to_state"]["last_screenshot_path"], "screenshots/test.png")


if __name__ == "__main__":
    unittest.main()
