# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from core.executor import Executor
from core.lifecycle import RequestContext, RequestStatus, reset_current_request
from core.planner import Planner
from core.runtime import JarvisRuntime
from core.state import JarvisState
from tools.base import Tool, ToolContext
from tools.registry import ToolRegistry


class DummySuccessTool(Tool):
    name = "dummy_success"
    description = "Dummy success tool"
    input_schema = {}

    def run(self, tool_input, ctx, state):
        return {"ok": True, "result": "success"}


class DummyFailingTool(Tool):
    name = "dummy_fail"
    description = "Dummy failing tool"
    input_schema = {}

    def run(self, tool_input, ctx, state):
        return {"ok": False, "error": "Simulated tool error"}


class TestUnifiedAgentLoop(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(DummySuccessTool())
        self.registry.register(DummyFailingTool())
        self.ctx = ToolContext(dry_run=True)
        self.state = JarvisState()

    def test_max_steps_limit(self):
        """Verify that Executor respects max_steps limit and stops."""
        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            max_steps=3,
        )
        steps = [{"tool": "dummy_success", "input": {}} for _ in range(10)]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 3)
        self.assertIn("user_help_required", self.state.data)
        self.assertIn("Překročen maximální počet kroků", self.state.data["user_help_required"])

    def test_cancellation_during_execution(self):
        """Verify that Executor stops when cancellation is requested."""
        req_ctx = reset_current_request(goal="Test cancellation")
        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
        )
        steps = [
            {"tool": "dummy_success", "input": {}},
            {"tool": "dummy_success", "input": {}},
        ]
        req_ctx.cancellation_requested = True
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 0)

    def test_transient_retry(self):
        """Verify that Executor retries failed steps up to max_retries."""
        mock_tool = MagicMock()
        mock_tool.name = "mock_retry"
        mock_tool.description = "Mock retry tool"
        mock_tool.input_schema = {}
        # First call fails, second succeeds
        mock_tool.run.side_effect = [
            {"ok": False, "error": "Temporary connection reset"},
            {"ok": True, "result": "Recovered on retry"},
        ]
        self.registry.register(mock_tool)

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            max_retries=2,
        )
        steps = [{"tool": "mock_retry", "input": {}}]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["output"]["ok"])
        self.assertEqual(mock_tool.run.call_count, 2)

    def test_replan_on_step_failure(self):
        """Verify that Executor attempts Planner.replan when step fails and repair fails."""
        mock_planner = MagicMock()
        mock_planner.replan.return_value = [
            {"tool": "dummy_success", "input": {}, "description": "Replanned fallback step"}
        ]

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            planner=mock_planner,
            max_repairs=0,
            max_replans=1,
        )
        steps = [{"tool": "dummy_fail", "input": {}}]

        with patch.object(executor, "_attempt_repair", return_value=False):
            results = executor.run_plan(steps)

        mock_planner.replan.assert_called_once()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["output"]["ok"])

    def test_autonomous_agent_wrapper_delegation(self):
        """Verify that AutonomousAgent delegates execution to JarvisRuntime."""
        from core.autonomous_agent import AutonomousAgent

        agent = AutonomousAgent()
        with patch.object(JarvisRuntime, "run_task") as mock_run_task:
            mock_result = MagicMock()
            mock_result.ok = True
            mock_result.summary = "Success"
            mock_result.steps = [{"tool": "open_app", "input": {"name": "chrome"}}]
            mock_result.results = [{"output": {"ok": True, "result": "Opened"}}]
            mock_run_task.return_value = mock_result

            res = agent.run("zapni chrome")

            mock_run_task.assert_called_once_with("zapni chrome")
            self.assertTrue(res["ok"])
            self.assertEqual(res["goal"], "zapni chrome")


if __name__ == "__main__":
    unittest.main()
