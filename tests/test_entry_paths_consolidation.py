# -*- coding: utf-8 -*-
import sys
import unittest
from unittest.mock import MagicMock, patch

from core import agent
from core.intents.command_router import route_and_execute_command
from core.intents.intent_types import IntentType
from core.intents.parsed_command import ParsedCommand
from core.runtime import JarvisRuntime, RuntimeResult
import run


class TestEntryPathsConsolidation(unittest.TestCase):
    def setUp(self):
        mock_state = MagicMock()
        mock_state.snapshot.return_value = {"files": [], "last_output": "Opened chrome", "data": {}, "tool_results": []}
        self.dummy_result = RuntimeResult(
            ok=True,
            goal="test goal",
            route="FAST_COMMAND",
            confidence=0.98,
            steps=[{"tool": "open_app", "input": {"name": "chrome"}}],
            results=[{"ok": True, "result": "Opened chrome"}],
            state=mock_state,
            summary="Chrome je otevřený.",
            request_id="req-123",
        )


    def test_legacy_command_router_delegates_to_runtime(self):
        """Verify legacy route_and_execute_command delegates to JarvisRuntime.run_task."""
        parsed = ParsedCommand(
            intent=IntentType.OPEN_APP,
            target="chrome",
            original_text="otevri chrome",
        )

        with patch.object(JarvisRuntime, "run_task", return_value=self.dummy_result) as mock_run_task:
            summary = route_and_execute_command(parsed)

            mock_run_task.assert_called_once_with("otevri chrome")
            self.assertEqual(summary, "Chrome je otevřený.")

    def test_gui_request_uses_runtime(self):
        """Verify GUI controller delegates text requests to JarvisRuntime.run_task."""
        from interfaces.gui_controller import GuiController

        mock_event_bus = MagicMock()
        gui = GuiController(event_bus=mock_event_bus)
        gui.runtime = MagicMock()
        gui.runtime.run_task.return_value = self.dummy_result

        parsed = ParsedCommand(
            intent=IntentType.OPEN_APP,
            target="chrome",
            original_text="zapni chrome",
        )

        # Call process_agent_request in thread and wait for completion
        thread = gui.process_agent_request(parsed)
        thread.join(timeout=2)

        gui.runtime.run_task.assert_called_once()
        call_args = gui.runtime.run_task.call_args
        self.assertEqual(call_args[0][0], "zapni chrome")

    def test_voice_request_uses_runtime(self):
        """Verify voice input (via handle_user_message) routes through process_agent_request to JarvisRuntime.run_task."""
        from interfaces.gui_controller import GuiController

        mock_event_bus = MagicMock()
        gui = GuiController(event_bus=mock_event_bus)
        gui.current_chat = "default"
        gui.chats = {"default": {"messages": []}}
        gui.runtime = MagicMock()
        gui.runtime.run_task.return_value = self.dummy_result

        with patch.object(gui, "clear_input"):
            gui.handle_user_message("spust calculator")

        # Wait for background thread
        import time
        time.sleep(0.1)

        gui.runtime.run_task.assert_called_once()
        self.assertEqual(gui.runtime.run_task.call_args[0][0], "spust calculator")

    def test_cli_request_uses_runtime(self):
        """Verify CLI entrypoint in run.py delegates to JarvisRuntime.run_task."""
        with patch.object(sys, "argv", ["run.py", "spust", "notepad"]), \
             patch.object(JarvisRuntime, "run_task", return_value=self.dummy_result) as mock_run_task:
            run.main()

            mock_run_task.assert_called_once_with("spust notepad")

    def test_http_high_level_request_uses_runtime(self):
        """Verify Flask /task and /command task actions delegate to JarvisRuntime.run_task."""
        with agent.app.test_client() as client, \
             patch.object(JarvisRuntime, "run_task", return_value=self.dummy_result) as mock_run_task:

            # Test /task endpoint
            resp1 = client.post("/task", json={"goal": "otevri calc"})
            self.assertEqual(resp1.status_code, 200)
            self.assertTrue(resp1.get_json()["ok"])

            # Test /command endpoint with action="task"
            resp2 = client.post("/command", json={"action": "task", "value": "otevri calc"})
            self.assertEqual(resp2.status_code, 200)
            self.assertTrue(resp2.get_json()["ok"])

            self.assertEqual(mock_run_task.call_count, 2)


if __name__ == "__main__":
    unittest.main()
