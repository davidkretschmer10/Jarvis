# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from core.event_bus import EventBus
from core.executor import Executor, StepExecutionStatus, StepResult
from core.lifecycle import (
    InvalidStateTransitionError,
    RequestContext,
    RequestStatus,
    get_current_request,
    reset_current_request,
    set_current_request,
)
from core.runtime import JarvisRuntime
from core.state import JarvisState
from tools.base import Tool, ToolContext
from tools.registry import ToolRegistry


class MockTool:
    def __init__(self, name: str, behavior=None):
        self.name = name
        self.description = f"Mock tool {name}"
        self.input_schema = {}
        self.calls = []
        self.behavior = behavior or (lambda tool_input, ctx, state: {"ok": True, "result": "mock_success"})

    def run(self, tool_input, ctx, state):
        self.calls.append({"input": tool_input, "state_data": dict(state.data)})
        if callable(self.behavior):
            return self.behavior(tool_input, ctx, state)
        return self.behavior


class TestExecutionSafetyKernel(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.state = JarvisState()
        self.event_bus = EventBus()
        self.ctx_tool = ToolContext(dry_run=True)

    # --------------------------------------------------------------------------
    # 1. Successful step
    # --------------------------------------------------------------------------
    def test_01_successful_step(self):
        tool = MockTool("test_tool", lambda i, c, s: {"ok": True, "result": "done"})
        self.registry.register(tool)
        req_ctx = RequestContext(goal="test success")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
        )
        results = executor.run_plan([{"tool": "test_tool", "input": {"x": 1}}])

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.status, StepExecutionStatus.SUCCESS)
        self.assertTrue(res.is_success)
        self.assertTrue(res["output"]["ok"])
        self.assertEqual(len(tool.calls), 1)

    # --------------------------------------------------------------------------
    # 2. Failed step
    # --------------------------------------------------------------------------
    def test_02_failed_step(self):
        tool = MockTool("fail_tool", lambda i, c, s: {"ok": False, "error": "Disk full"})
        self.registry.register(tool)
        req_ctx = RequestContext(goal="test failure")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            max_repairs=0,
            max_replans=0,
        )
        results = executor.run_plan([{"tool": "fail_tool", "input": {}}])

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.status, StepExecutionStatus.FAILED)
        self.assertFalse(res.is_success)
        self.assertFalse(res["output"]["ok"])
        self.assertEqual(req_ctx.status, RequestStatus.FAILED)

    # --------------------------------------------------------------------------
    # 3. Confirmation pause
    # --------------------------------------------------------------------------
    def test_03_confirmation_pause(self):
        def conf_tool(i, c, s):
            return {"ok": False, "error": "CONFIRMATION_REQUIRED", "message": "Potvrdit smazani?"}

        self.registry.register(MockTool("delete_tool", conf_tool))
        self.registry.register(MockTool("next_tool", lambda i, c, s: {"ok": True}))
        req_ctx = RequestContext(goal="test confirmation")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
        )
        results = executor.run_plan([
            {"tool": "delete_tool", "input": {"file": "a.txt"}},
            {"tool": "next_tool", "input": {}},
        ])

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.status, StepExecutionStatus.WAITING_FOR_CONFIRMATION)
        self.assertEqual(self.state.data["paused_step_index"], 0)
        self.assertEqual(req_ctx.status, RequestStatus.WAITING_FOR_USER)
        # Verify next step was NOT executed
        self.assertEqual(len(results), 1)

    # --------------------------------------------------------------------------
    # 4. Confirmation denied
    # --------------------------------------------------------------------------
    def test_04_confirmation_denied(self):
        req_ctx = RequestContext(goal="test confirmation denied")
        req_ctx.transition_to(RequestStatus.EXECUTING)
        req_ctx.transition_to(RequestStatus.WAITING_FOR_USER)

        req_ctx.cancel(reason="Uzivatel odmitl potvrzeni")
        self.assertEqual(req_ctx.status, RequestStatus.CANCELLED)
        self.assertTrue(req_ctx.is_cancelled)

    # --------------------------------------------------------------------------
    # 5. Confirmation resume
    # --------------------------------------------------------------------------
    @patch("core.runtime.Planner.plan")
    def test_05_confirmation_resume(self, mock_plan):
        mock_plan.return_value = [{"tool": "guarded_tool", "input": {}}]
        called = []

        def tool_fn(i, c, s):
            if not s.data.get("action_confirmed"):
                return {"ok": False, "error": "CONFIRMATION_REQUIRED", "message": "Potvrdit?"}
            called.append(True)
            return {"ok": True, "result": "action done"}

        self.registry.register(MockTool("guarded_tool", tool_fn))
        runtime = JarvisRuntime(registry=self.registry, dry_run=True)

        # 1. First run triggers confirmation
        res1 = runtime.run_task("Spust guarded_tool")
        self.assertTrue(res1.pending_confirmation)
        self.assertEqual(res1.state.data["paused_step_index"], 0)

        # 2. Resume with confirmation
        res2 = runtime.resume_task(
            goal=res1.goal,
            steps=res1.steps,
            state=res1.state,
            start_index=0,
            expected_request_id=res1.request_id,
        )
        self.assertTrue(res2.ok)
        self.assertFalse(res2.pending_confirmation)
        self.assertTrue(len(called) > 0)

    # --------------------------------------------------------------------------
    # 6. Cancellation before execution
    # --------------------------------------------------------------------------
    def test_06_cancellation_before_execution(self):
        tool = MockTool("tool1")
        self.registry.register(tool)
        req_ctx = RequestContext(goal="test cancel before")
        req_ctx.cancel(reason="User abort")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
        )
        results = executor.run_plan([{"tool": "tool1", "input": {}}])

        self.assertEqual(len(results), 0)
        self.assertEqual(len(tool.calls), 0)

    # --------------------------------------------------------------------------
    # 7. Cancellation between steps
    # --------------------------------------------------------------------------
    def test_07_cancellation_between_steps(self):
        req_ctx = RequestContext(goal="test cancel between")

        def step1_fn(i, c, s):
            req_ctx.cancel("Cancelled inside step 1")
            return {"ok": True, "result": "step 1 completed"}

        self.registry.register(MockTool("step1", step1_fn))
        step2 = MockTool("step2")
        self.registry.register(step2)

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
        )
        results = executor.run_plan([
            {"tool": "step1", "input": {}},
            {"tool": "step2", "input": {}},
        ])

        self.assertEqual(len(results), 1)
        self.assertEqual(len(step2.calls), 0)
        self.assertTrue(req_ctx.is_cancelled)

    # --------------------------------------------------------------------------
    # 8. Cancellation during retry
    # --------------------------------------------------------------------------
    def test_08_cancellation_during_retry(self):
        req_ctx = RequestContext(goal="test cancel retry")
        attempts = []

        def retry_tool(i, c, s):
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                req_ctx.cancel("Cancelled during retry attempt 1")
            return {"ok": False, "error": "Network timeout"}

        self.registry.register(MockTool("retry_tool", retry_tool))

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            max_retries=3,
        )
        results = executor.run_plan([{"tool": "retry_tool", "input": {}}])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, StepExecutionStatus.CANCELLED)
        # Should not exhaust all 4 attempts (1 initial + 3 retries)
        self.assertLess(len(attempts), 4)

    # --------------------------------------------------------------------------
    # 9. Failure during repair
    # --------------------------------------------------------------------------
    def test_09_failure_during_repair(self):
        self.registry.register(MockTool("fail_tool", lambda i, c, s: {"ok": False, "error": "Element missing"}))
        req_ctx = RequestContext(goal="test repair fail")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            max_repairs=1,
            max_replans=0,
        )
        # Mock _attempt_repair to return False (repair failed)
        executor._attempt_repair = MagicMock(return_value=False)

        results = executor.run_plan([{"tool": "fail_tool", "input": {}}])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, StepExecutionStatus.FAILED)
        self.assertEqual(req_ctx.status, RequestStatus.FAILED)

    # --------------------------------------------------------------------------
    # 10. Failure during replan
    # --------------------------------------------------------------------------
    def test_10_failure_during_replan(self):
        self.registry.register(MockTool("fail_tool", lambda i, c, s: {"ok": False, "error": "App crashed"}))
        req_ctx = RequestContext(goal="test replan fail")

        mock_planner = MagicMock()
        mock_planner.replan.return_value = []  # replan returned no steps

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            planner=mock_planner,
            max_repairs=0,
            max_replans=1,
        )
        results = executor.run_plan([{"tool": "fail_tool", "input": {}}])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, StepExecutionStatus.FAILED)
        self.assertEqual(req_ctx.status, RequestStatus.FAILED)

    # --------------------------------------------------------------------------
    # 11. Retry limit
    # --------------------------------------------------------------------------
    def test_11_retry_limit(self):
        calls = []

        def failing_tool(i, c, s):
            calls.append(True)
            return {"ok": False, "error": "Transient glitch"}

        self.registry.register(MockTool("retry_lim_tool", failing_tool))
        req_ctx = RequestContext(goal="test retry limit")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            max_retries=2,
            max_repairs=0,
            max_replans=0,
        )
        executor.run_plan([{"tool": "retry_lim_tool", "input": {}}])

        # 1 initial + 2 retries = 3 calls
        self.assertEqual(len(calls), 3)

    # --------------------------------------------------------------------------
    # 12. Repair limit
    # --------------------------------------------------------------------------
    def test_12_repair_limit(self):
        self.registry.register(MockTool("fail_tool", lambda i, c, s: {"ok": False, "error": "Not clickable"}))
        req_ctx = RequestContext(goal="test repair limit")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            max_repairs=1,
            max_replans=0,
        )
        repair_calls = []

        def mock_repair(step, err):
            repair_calls.append(True)
            return False

        executor._attempt_repair = mock_repair
        executor.run_plan([{"tool": "fail_tool", "input": {}}])

        self.assertEqual(len(repair_calls), 1)

    # --------------------------------------------------------------------------
    # 13. Replan limit
    # --------------------------------------------------------------------------
    def test_13_replan_limit(self):
        self.registry.register(MockTool("fail_tool", lambda i, c, s: {"ok": False, "error": "Persistent error"}))
        req_ctx = RequestContext(goal="test replan limit")

        mock_planner = MagicMock()
        mock_planner.replan.return_value = [{"tool": "fail_tool", "input": {}}]

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            planner=mock_planner,
            max_repairs=0,
            max_replans=2,
        )
        executor.run_plan([{"tool": "fail_tool", "input": {}}])

        self.assertEqual(mock_planner.replan.call_count, 2)

    # --------------------------------------------------------------------------
    # 14. Terminal state cannot continue
    # --------------------------------------------------------------------------
    def test_14_terminal_state_cannot_continue(self):
        req_ctx = RequestContext(goal="test terminal stop")
        req_ctx.transition_to(RequestStatus.EXECUTING)
        req_ctx.transition_to(RequestStatus.COMPLETED)

        tool = MockTool("tool_after_term")
        self.registry.register(tool)

        runtime = JarvisRuntime(registry=self.registry, dry_run=True)
        # Attempting to run task with completed context
        res = runtime.run_task("Execute after complete", request_context=req_ctx)
        self.assertFalse(res.ok)
        self.assertEqual(len(tool.calls), 0)

    # --------------------------------------------------------------------------
    # 15. Terminal state cannot be overwritten
    # --------------------------------------------------------------------------
    def test_15_terminal_state_cannot_be_overwritten(self):
        req_ctx = RequestContext(goal="test terminal immutable")
        req_ctx.transition_to(RequestStatus.EXECUTING)
        req_ctx.transition_to(RequestStatus.COMPLETED)

        # Illegal transition directly
        with self.assertRaises(InvalidStateTransitionError):
            req_ctx.transition_to(RequestStatus.EXECUTING)

        # Illegal override via property setter
        with self.assertRaises(InvalidStateTransitionError):
            req_ctx.completed = False

        self.assertEqual(req_ctx.status, RequestStatus.COMPLETED)

    # --------------------------------------------------------------------------
    # 16. Paused request cannot execute next step
    # --------------------------------------------------------------------------
    def test_16_paused_request_cannot_execute_next_step(self):
        def pausing_tool(i, c, s):
            return {"ok": False, "error": "CONFIRMATION_REQUIRED", "message": "Confirm?"}

        self.registry.register(MockTool("pause_tool", pausing_tool))
        next_tool = MockTool("step_after_pause")
        self.registry.register(next_tool)

        req_ctx = RequestContext(goal="test pause barrier")
        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
        )
        results = executor.run_plan([
            {"tool": "pause_tool", "input": {}},
            {"tool": "step_after_pause", "input": {}},
        ])

        self.assertEqual(len(results), 1)
        self.assertEqual(len(next_tool.calls), 0)
        self.assertEqual(req_ctx.status, RequestStatus.WAITING_FOR_USER)

    # --------------------------------------------------------------------------
    # 17. Same request_id across worker thread
    # --------------------------------------------------------------------------
    def test_17_same_request_id_across_worker_thread(self):
        main_ctx = reset_current_request(goal="multi-thread test", source="test_main")
        observed_id_in_thread = []

        def worker():
            main_ctx.copy_to_thread()
            thread_ctx = get_current_request()
            observed_id_in_thread.append(thread_ctx.request_id)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        self.assertEqual(len(observed_id_in_thread), 1)
        self.assertEqual(observed_id_in_thread[0], main_ctx.request_id)

    # --------------------------------------------------------------------------
    # 18. Two concurrent requests have different request_id
    # --------------------------------------------------------------------------
    def test_18_two_concurrent_requests_have_different_request_id(self):
        ctx_a = RequestContext(goal="req A")
        ctx_b = RequestContext(goal="req B")

        self.assertNotEqual(ctx_a.request_id, ctx_b.request_id)

    # --------------------------------------------------------------------------
    # 19. Confirmation for request A cannot resume request B
    # --------------------------------------------------------------------------
    def test_19_confirmation_for_a_cannot_resume_b(self):
        runtime = JarvisRuntime(registry=self.registry, dry_run=True)
        self.state.data["pending_confirmation"] = {
            "request_id": "REQUEST_A_ID",
            "step_index": 0,
            "tool": "some_tool",
        }
        ctx_b = RequestContext(request_id="REQUEST_B_ID", goal="Task B")

        with self.assertRaises(ValueError):
            runtime.resume_task(
                goal="Task B",
                steps=[{"tool": "some_tool", "input": {}}],
                state=self.state,
                start_index=0,
                expected_request_id="REQUEST_B_ID",
                request_context=ctx_b,
            )

    # --------------------------------------------------------------------------
    # 20. Tool failure is not marked as successful step
    # --------------------------------------------------------------------------
    def test_20_tool_failure_is_not_marked_as_successful_step(self):
        self.registry.register(MockTool("broken_tool", lambda i, c, s: {"ok": False, "error": "Access denied"}))
        req_ctx = RequestContext(goal="test failure step")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            max_repairs=0,
            max_replans=0,
        )
        results = executor.run_plan([{"tool": "broken_tool", "input": {}}])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].is_success)
        self.assertEqual(results[0].status, StepExecutionStatus.FAILED)

    # --------------------------------------------------------------------------
    # 21. Failed step does not increment completed steps in memory
    # --------------------------------------------------------------------------
    def test_21_failed_step_does_not_increment_completed_steps(self):
        from core.task_memory import TaskMemory

        task_mem = TaskMemory()
        self.registry.register(MockTool("fail_tool", lambda i, c, s: {"ok": False, "error": "Hardware fail"}))
        req_ctx = RequestContext(goal="test task memory fail")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            task_memory=task_mem,
            request_context=req_ctx,
            event_bus=self.event_bus,
            max_repairs=0,
            max_replans=0,
        )
        executor.run_plan([{"tool": "fail_tool", "input": {}}])

        self.assertTrue(len(task_mem.steps) > 0)
        self.assertEqual(task_mem.steps[0]["status"], "failed")

    # --------------------------------------------------------------------------
    # 22. Cancelled step does not increment completed steps in memory
    # --------------------------------------------------------------------------
    def test_22_cancelled_step_does_not_increment_completed_steps(self):
        from core.task_memory import TaskMemory

        task_mem = TaskMemory()
        req_ctx = RequestContext(goal="test task memory cancel")
        req_ctx.cancel("Pre-cancel")

        self.registry.register(MockTool("tool1"))
        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            task_memory=task_mem,
            request_context=req_ctx,
            event_bus=self.event_bus,
        )
        executor.run_plan([{"tool": "tool1", "input": {}}])

        if task_mem.steps:
            self.assertNotEqual(task_mem.steps[0]["status"], "completed")

    # --------------------------------------------------------------------------
    # 23. Timeout does not continue execution
    # --------------------------------------------------------------------------
    def test_23_timeout_does_not_continue_execution(self):
        calls = []

        def infinite_tool(i, c, s):
            calls.append(len(calls))
            return {"ok": True, "result": "step executed"}

        self.registry.register(MockTool("loop_tool", infinite_tool))
        req_ctx = RequestContext(goal="test timeout")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            max_steps=3,
        )
        # 5 planned steps, max_steps = 3
        results = executor.run_plan([{"tool": "loop_tool", "input": {}} for _ in range(5)])

        self.assertEqual(len(calls), 3)
        self.assertEqual(len(results), 3)
        self.assertEqual(req_ctx.status, RequestStatus.FAILED)
        self.assertIn("maximální počet kroků", self.state.data.get("user_help_required", ""))

    # --------------------------------------------------------------------------
    # 24. No infinite retry/repair/replan loop
    # --------------------------------------------------------------------------
    def test_24_no_infinite_loop(self):
        calls = []

        def failing_tool(i, c, s):
            calls.append(True)
            return {"ok": False, "error": "Permanent failure"}

        self.registry.register(MockTool("fail_tool", failing_tool))
        req_ctx = RequestContext(goal="test no infinite loop")

        mock_planner = MagicMock()
        # Planner keeps returning failing tool
        mock_planner.replan.return_value = [{"tool": "fail_tool", "input": {}}]

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx_tool,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            planner=mock_planner,
            max_retries=1,
            max_repairs=1,
            max_replans=2,
            max_steps=10,
        )
        executor._attempt_repair = MagicMock(return_value=False)

        start_t = time.time()
        results = executor.run_plan([{"tool": "fail_tool", "input": {}}])
        duration = time.time() - start_t

        self.assertLess(duration, 5.0)  # Must finish rapidly
        self.assertEqual(results[-1].status, StepExecutionStatus.FAILED)
        self.assertEqual(req_ctx.status, RequestStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
