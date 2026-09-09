# -*- coding: utf-8 -*-
"""
Tests for ONE TRUE RUNTIME architecture.
Verifies that all input paths (GUI chat, GUI action, Voice, CLI, HTTP, AutonomousAgent)
route exclusively through JarvisRuntime.run_task() with unified RequestContext,
RequestResult, and single authoritative execution pipeline.
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from core.executor import Executor
from core.intents.intent_types import IntentType
from core.intents.parsed_command import ParsedCommand
from core.lifecycle import (
    RequestContext,
    RequestStatus,
    get_current_request,
    reset_current_request,
)
from core.planner import Planner
from core.runtime import (
    JarvisRuntime,
    RequestExecutionStatus,
    RequestResult,
    RuntimeResult,
)
from core.state import JarvisState
from tools.registry import ToolRegistry


class TestOneTrueRuntime(unittest.TestCase):
    def setUp(self):
        self.mock_state = JarvisState()
        self.dummy_result = RequestResult(
            ok=True,
            goal="test goal",
            route="FAST_COMMAND",
            confidence=0.98,
            steps=[{"tool": "open_app", "input": {"name": "chrome"}}],
            results=[{"ok": True, "result": "Opened chrome", "verification_status": "VERIFIED"}],
            state=self.mock_state,
            summary="Chrome je otevřený.",
            request_id="req-test-123",
            status=RequestExecutionStatus.COMPLETED,
            response_text="Chrome je otevřený.",
        )

    # 1. GUI chat -> Runtime
    def test_01_gui_chat_routes_to_runtime(self):
        from interfaces.gui_controller import GuiController

        bus = MagicMock()
        gui = GuiController(event_bus=bus)
        gui.runtime = MagicMock()
        chat_result = RequestResult(
            ok=True,
            goal="Jak se máš?",
            route="CHAT",
            confidence=1.0,
            steps=[],
            results=[],
            state=self.mock_state,
            summary="Mám se skvěle, děkuji!",
            request_id="req-chat-01",
            status=RequestExecutionStatus.COMPLETED,
            response_text="Mám se skvěle, děkuji!",
        )
        gui.runtime.run_task.return_value = chat_result

        with patch.object(gui, "clear_input"), patch("interfaces.gui_controller.update_profile"):
            t = gui.process_request("Jak se máš?", source="gui_chat")
            t.join(timeout=2)

        gui.runtime.run_task.assert_called_once()
        self.assertEqual(gui.runtime.run_task.call_args[0][0], "Jak se máš?")

    # 2. GUI action -> Runtime
    def test_02_gui_action_routes_to_runtime(self):
        from interfaces.gui_controller import GuiController

        bus = MagicMock()
        gui = GuiController(event_bus=bus)
        gui.runtime = MagicMock()
        gui.runtime.run_task.return_value = self.dummy_result

        parsed = ParsedCommand(intent=IntentType.OPEN_APP, target="chrome", original_text="otevri chrome")
        with patch.object(gui, "clear_input"), patch("interfaces.gui_controller.update_profile"):
            t = gui.process_agent_request(parsed)
            t.join(timeout=2)

        gui.runtime.run_task.assert_called_once()
        self.assertEqual(gui.runtime.run_task.call_args[0][0], "otevri chrome")

    # 3. Voice command -> Runtime
    def test_03_voice_command_routes_to_runtime(self):
        from interfaces.gui_controller import GuiController

        bus = MagicMock()
        gui = GuiController(event_bus=bus)
        gui.current_chat = "default"
        gui.chats = {"default": {"messages": []}}
        gui.runtime = MagicMock()
        gui.runtime.run_task.return_value = self.dummy_result

        with patch.object(gui, "clear_input"), patch("interfaces.gui_controller.update_profile"):
            t = gui.handle_voice_text("otevri chrome")
            if t:
                t.join(timeout=2)

        gui.runtime.run_task.assert_called_once()
        self.assertEqual(gui.runtime.run_task.call_args[0][0], "otevri chrome")

    # 4. CLI command -> Runtime
    def test_04_cli_command_routes_to_runtime(self):
        import run

        with patch.object(sys, "argv", ["run.py", "otevri", "notepad"]), \
             patch.object(JarvisRuntime, "run_task", return_value=self.dummy_result) as mock_run:
            run.main()

        mock_run.assert_called_once_with("otevri notepad")

    # 5. HTTP /task -> Runtime
    def test_05_http_task_routes_to_runtime(self):
        from core import agent

        with agent.app.test_client() as client, \
             patch.object(JarvisRuntime, "run_task", return_value=self.dummy_result) as mock_run:
            resp = client.post("/task", json={"goal": "otevri kalkulacku"})
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["request_id"], "req-test-123")
            self.assertEqual(data["status"], RequestExecutionStatus.COMPLETED.value)
            mock_run.assert_called_once_with("otevri kalkulacku")

    # 6. AutonomousAgent -> Runtime
    def test_06_autonomous_agent_routes_to_runtime(self):
        from core.autonomous_agent import AutonomousAgent

        agent = AutonomousAgent()
        with patch.object(JarvisRuntime, "run_task", return_value=self.dummy_result) as mock_run:
            res = agent.run("spusť spotify")
            mock_run.assert_called_once_with("spusť spotify")
            self.assertTrue(res["ok"])
            self.assertEqual(res["goal"], "spusť spotify")
            self.assertEqual(res["request_id"], "req-test-123")

    # 7. Chat request does not call Executor
    def test_07_chat_request_does_not_call_executor(self):
        runtime = JarvisRuntime()
        with patch("ai.engine.ask_ai", return_value="Gravitace je přitažlivá síla."), \
             patch.object(Executor, "run_plan") as mock_executor, \
             patch.object(Planner, "plan") as mock_planner:
            result = runtime.run_task("Co je gravitace?")

            self.assertTrue(result.ok)
            self.assertEqual(result.route, "CHAT")
            self.assertEqual(result.response_text, "Gravitace je přitažlivá síla.")
            self.assertEqual(result.status, RequestExecutionStatus.CHAT_RESPONSE.value)
            mock_executor.assert_not_called()
            mock_planner.assert_not_called()

    # 8. Action request calls Planner + Executor
    def test_08_action_request_calls_planner_and_executor(self):
        runtime = JarvisRuntime()
        planned_steps = [{"tool": "open_app", "input": {"name": "chrome"}}]
        executed_results = [{"ok": True, "output": {"ok": True, "result": "Done"}, "verification_status": "VERIFIED"}]

        with patch.object(Planner, "plan", return_value=planned_steps) as mock_planner, \
             patch.object(Executor, "run_plan", return_value=executed_results) as mock_executor:
            # "otevři chrome a napiš text" triggers PLANNER_V2
            result = runtime.run_task("otevři chrome a napiš text")

            self.assertTrue(result.ok)
            mock_planner.assert_called_once()
            mock_executor.assert_called_once()

    # 9. Mixed request uses single Runtime
    def test_09_mixed_request_uses_single_runtime(self):
        runtime = JarvisRuntime()
        planned_steps = [{"tool": "open_app", "input": {"name": "chrome"}}]
        executed_results = [{"ok": True, "output": {"ok": True, "result": "Done"}, "verification_status": "VERIFIED"}]

        with patch.object(Planner, "plan", return_value=planned_steps) as mock_planner, \
             patch.object(Executor, "run_plan", return_value=executed_results) as mock_executor:
            # Multi-intent mixed request
            result = runtime.run_task("Řekni mi kolik je hodin a potom otevři Chrome")

            self.assertEqual(result.route, "MIXED")
            self.assertTrue(result.ok)
            mock_planner.assert_called_once()
            mock_executor.assert_called_once()

    # 10. request_id remains the same across pipeline
    def test_10_request_id_remains_same_throughout(self):
        runtime = JarvisRuntime()
        custom_ctx = reset_current_request(goal="otevři kalkulačku", source="cli")
        fixed_req_id = custom_ctx.request_id

        observed_ctx_ids = []

        def fake_run_plan(steps):
            cur = get_current_request()
            observed_ctx_ids.append(cur.request_id)
            return [{"ok": True, "output": {"ok": True, "result": "Launched"}, "verification_status": "VERIFIED"}]

        with patch.object(Executor, "run_plan", side_effect=fake_run_plan):
            res = runtime.run_task("otevři kalkulačku", request_context=custom_ctx, reset_request=False)

            self.assertEqual(res.request_id, fixed_req_id)
            self.assertEqual(observed_ctx_ids, [fixed_req_id])
            self.assertEqual(get_current_request().request_id, fixed_req_id)

    # 11. cancellation works via adapter
    def test_11_cancellation_propagates_to_request_result(self):
        runtime = JarvisRuntime()
        ctx = reset_current_request(goal="dlouhy ukol", source="gui")
        ctx.request_cancellation(reason="User clicked Stop")

        res = runtime.run_task("dlouhy ukol", request_context=ctx, reset_request=False)

        self.assertFalse(res.ok)
        self.assertEqual(res.status, RequestExecutionStatus.CANCELLED.value)
        self.assertIn("zrusen", res.summary.lower())

    # 12. confirmation works via adapter
    def test_12_confirmation_flow_preserves_context(self):
        runtime = JarvisRuntime()
        state = JarvisState()
        state.data["paused_step_index"] = 1
        state.data["user_help_required"] = "Potvrdit smazani?"

        steps = [
            {"tool": "open_app", "input": {"name": "chrome"}},
            {"tool": "close_window", "input": {"title": "chrome"}},
        ]
        results = [{"ok": True, "output": {"ok": True, "result": "Opened"}, "verification_status": "VERIFIED"}]

        with patch.object(Planner, "plan", return_value=steps), \
             patch.object(Executor, "run_plan", return_value=results):
            res = runtime.run_task("smaz data", state=state)
            self.assertFalse(res.ok)
            self.assertTrue(res.pending_confirmation)
            self.assertEqual(res.status, RequestExecutionStatus.WAITING_FOR_CONFIRMATION.value)

    # 13. verification works via adapter
    def test_13_verification_status_recorded_in_results(self):
        runtime = JarvisRuntime()
        steps = [{"tool": "open_app", "input": {"name": "notepad"}}]
        results = [{
            "ok": True,
            "output": {"ok": True, "result": "Started"},
            "verification_status": "VERIFIED",
            "observation": {"window_found": True},
        }]

        with patch.object(Planner, "plan", return_value=steps), \
             patch.object(Executor, "run_plan", return_value=results):
            res = runtime.run_task("otevři notepad")
            self.assertTrue(res.ok)
            self.assertEqual(res.status, RequestExecutionStatus.COMPLETED.value)
            self.assertIn("overen", res.summary.lower())

    # 14. failed action is not marked completed
    def test_14_failed_action_not_marked_completed(self):
        runtime = JarvisRuntime()
        steps = [{"tool": "open_app", "input": {"name": "broken_app"}}]
        results = [{
            "ok": False,
            "output": {"ok": False, "error": "Process crashed"},
            "verification_status": "FAILED",
        }]

        with patch.object(Planner, "plan", return_value=steps), \
             patch.object(Executor, "run_plan", return_value=results):
            res = runtime.run_task("otevři nefunkční aplikaci")
            self.assertFalse(res.ok)
            self.assertEqual(res.status, RequestExecutionStatus.FAILED.value)
            self.assertIn("selhal", res.summary.lower())
            self.assertIsNotNone(res.error)

    # 15. voice pipeline does not create its own agent loop
    def test_15_voice_pipeline_is_adapter_without_agent_loop(self):
        from Voice.pipeline.realtime_pipeline import RealtimeVoicePipeline
        from Voice.voice_manager import VoiceManager

        # Verify RealtimeVoicePipeline and VoiceManager do not have their own Planner/Executor
        self.assertFalse(hasattr(RealtimeVoicePipeline, "planner"))
        self.assertFalse(hasattr(RealtimeVoicePipeline, "executor"))
        self.assertFalse(hasattr(RealtimeVoicePipeline, "run_plan"))
        self.assertFalse(hasattr(RealtimeVoicePipeline, "run_task"))

        self.assertFalse(hasattr(VoiceManager, "planner"))
        self.assertFalse(hasattr(VoiceManager, "executor"))
        self.assertFalse(hasattr(VoiceManager, "run_plan"))

    # 16. AutonomousAgent has no parallel execution loop
    def test_16_autonomous_agent_has_no_parallel_execution_loop(self):
        from core.autonomous_agent import AutonomousAgent

        agent = AutonomousAgent()
        with patch.object(JarvisRuntime, "run_task") as mock_run_task, \
             patch.object(agent, "plan") as mock_agent_plan:
            mock_run_task.return_value = self.dummy_result
            res = agent.run("otevři chrome")
            mock_run_task.assert_called_once_with("otevři chrome")
            mock_agent_plan.assert_not_called()
            self.assertTrue(res["ok"])

    # 17. AI engine is not an independent agent brain
    def test_17_ai_engine_is_provider_not_agent_orchestrator(self):
        import ai.engine as ai_engine
        # Ensure engine is a model/provider layer and does not orchestrate Planner or Executor
        self.assertFalse(hasattr(ai_engine, "Planner"))
        self.assertFalse(hasattr(ai_engine, "Executor"))
        self.assertFalse(hasattr(ai_engine, "JarvisRuntime"))

    # 18. legacy router delegates to authoritative router
    def test_18_legacy_router_delegates_to_runtime(self):
        from core.intents.command_router import route_and_execute_command

        cmd = ParsedCommand(intent=IntentType.OPEN_APP, target="notepad", original_text="otevri notepad")
        with patch.object(JarvisRuntime, "run_task", return_value=self.dummy_result) as mock_run:
            summary = route_and_execute_command(cmd)
            mock_run.assert_called_once_with("otevri notepad")
            self.assertEqual(summary, self.dummy_result.summary)

    # 19. Architecture test: detects parallel execution systems
    def test_19_architecture_no_parallel_execution_loops(self):
        """
        Architecture invariant:
        When GUI, Voice, or AutonomousAgent processes a request, Planner and Executor
        must NEVER be invoked directly by the adapter. They must ONLY be invoked
        via JarvisRuntime.run_task().
        """
        from interfaces.gui_controller import GuiController
        from core.autonomous_agent import AutonomousAgent

        bus = MagicMock()
        gui = GuiController(event_bus=bus)

        with patch.object(Executor, "run_plan") as mock_exec_run, \
             patch.object(Planner, "plan") as mock_plan_run, \
             patch.object(gui.runtime, "run_task", return_value=self.dummy_result) as mock_runtime_run:

            # GUI request
            with patch.object(gui, "clear_input"), patch("interfaces.gui_controller.update_profile"):
                t = gui.process_request("otevři chrome", source="gui")
                t.join(timeout=2)

            # Assert runtime.run_task was called, but Planner/Executor were NOT called directly by GUI
            mock_runtime_run.assert_called_once()
            mock_exec_run.assert_not_called()
            mock_plan_run.assert_not_called()

        # AutonomousAgent request
        agent = AutonomousAgent()
        with patch.object(Executor, "run_plan") as mock_exec_run, \
             patch.object(Planner, "plan") as mock_plan_run, \
             patch.object(JarvisRuntime, "run_task", return_value=self.dummy_result) as mock_runtime_run:

            agent.run("otevři chrome")
            mock_runtime_run.assert_called_once_with("otevři chrome")
            mock_exec_run.assert_not_called()
            mock_plan_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
