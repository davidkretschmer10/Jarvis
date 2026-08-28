# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from core.event_bus import EventBus
from core.lifecycle import (
    InvalidStateTransitionError,
    RequestContext,
    RequestStatus,
    cancel_current_request,
    check_request_context_block,
    complete_current_request,
    fail_current_request,
    get_current_request,
    reset_current_request,
    set_current_request,
)
from core.runtime import JarvisRuntime
from core.state import JarvisState
from tools.base import ToolContext
from tools.registry import ToolRegistry


class DummyStepTool:
    name = "dummy_step"
    description = "Dummy test tool"
    input_schema = {}

    def run(self, input_data, ctx, state):
        step_id = input_data.get("id", 1)
        if input_data.get("fail", False):
            return {"ok": False, "error": f"Intentional failure at step {step_id}"}
        if input_data.get("ask_confirm", False):
            return {
                "ok": False,
                "error": "CONFIRMATION_REQUIRED",
                "message": "Potvrďte prosím tuto akci.",
            }
        return {"ok": True, "result": f"Step {step_id} executed successfully"}


class DummyOpenAppTool:
    name = "open_app"
    description = "Dummy open app tool"
    input_schema = {}

    def run(self, input_data, ctx, state):
        return {"ok": True, "result": "calculator opened successfully"}


class TestRequestLifecycle(unittest.TestCase):

    def setUp(self):
        self.bus = EventBus()
        self.registry = ToolRegistry()
        self.registry.register(DummyStepTool())
        self.registry.register(DummyOpenAppTool())

    # 1. Test request creation
    def test_request_creation(self):
        ctx = RequestContext(goal="Otevři kalkulačku", source="gui")
        self.assertIsNotNone(ctx.request_id)
        self.assertEqual(len(ctx.request_id), 8)
        self.assertEqual(ctx.goal, "Otevři kalkulačku")
        self.assertEqual(ctx.source, "gui")
        self.assertEqual(ctx.status, RequestStatus.CREATED)
        self.assertGreater(ctx.created_at, 0)
        self.assertIsNone(ctx.started_at)
        self.assertIsNone(ctx.completed_at)
        self.assertEqual(ctx.current_step, 0)
        self.assertEqual(ctx.total_steps, 0)
        self.assertFalse(ctx.cancellation_requested)
        self.assertFalse(ctx.waiting_for_user)
        self.assertFalse(ctx.completed)
        self.assertFalse(ctx.cancelled)
        self.assertFalse(ctx.failed)

    # 2. Test valid state transition sequence
    def test_state_transition_sequence(self):
        ctx = RequestContext(goal="Test goal")
        self.assertEqual(ctx.status, RequestStatus.CREATED)

        ctx.transition_to(RequestStatus.ROUTING)
        self.assertEqual(ctx.status, RequestStatus.ROUTING)
        self.assertIsNotNone(ctx.started_at)

        ctx.transition_to(RequestStatus.PLANNING)
        self.assertEqual(ctx.status, RequestStatus.PLANNING)

        ctx.transition_to(RequestStatus.EXECUTING)
        self.assertEqual(ctx.status, RequestStatus.EXECUTING)

        ctx.transition_to(RequestStatus.VERIFYING)
        self.assertEqual(ctx.status, RequestStatus.VERIFYING)

        ctx.transition_to(RequestStatus.COMPLETED, result="Task finished successfully")
        self.assertEqual(ctx.status, RequestStatus.COMPLETED)
        self.assertTrue(ctx.completed)
        self.assertIsNotNone(ctx.completed_at)
        self.assertEqual(ctx.result, "Task finished successfully")

    # 3. Test invalid state transition
    def test_invalid_state_transition(self):
        ctx = RequestContext()
        ctx.transition_to(RequestStatus.ROUTING)
        ctx.transition_to(RequestStatus.PLANNING)
        ctx.transition_to(RequestStatus.EXECUTING)
        ctx.transition_to(RequestStatus.VERIFYING)
        ctx.transition_to(RequestStatus.COMPLETED)

        # COMPLETED is terminal; cannot transition to EXECUTING or ROUTING or PLANNING
        with self.assertRaises(InvalidStateTransitionError):
            ctx.transition_to(RequestStatus.EXECUTING)

        with self.assertRaises(InvalidStateTransitionError):
            ctx.transition_to(RequestStatus.ROUTING)

        with self.assertRaises(InvalidStateTransitionError):
            ctx.transition_to(RequestStatus.PLANNING)

    # 4. Test completion flow
    def test_completion_flow(self):
        ctx = reset_current_request(goal="Test completion")
        self.assertFalse(ctx.completed)
        ctx.transition_to(RequestStatus.ROUTING)
        ctx.transition_to(RequestStatus.EXECUTING)
        complete_current_request(result="Success message")
        self.assertEqual(ctx.status, RequestStatus.COMPLETED)
        self.assertTrue(ctx.completed)
        self.assertIsNotNone(ctx.completed_at)
        self.assertGreaterEqual(ctx.duration, 0.0)
        self.assertEqual(ctx.result, "Success message")

    # 5. Test failure flow
    def test_failure_flow(self):
        ctx = reset_current_request(goal="Test failure")
        ctx.transition_to(RequestStatus.ROUTING)
        fail_current_request(error="Something went wrong")
        self.assertEqual(ctx.status, RequestStatus.FAILED)
        self.assertTrue(ctx.failed)
        self.assertEqual(ctx.error, "Something went wrong")
        self.assertIsNotNone(ctx.completed_at)

    # 6. Test cancellation flow
    def test_cancellation_flow(self):
        ctx = reset_current_request(goal="Test cancellation")
        ctx.transition_to(RequestStatus.ROUTING)
        cancel_current_request(reason="User clicked cancel")
        self.assertEqual(ctx.status, RequestStatus.CANCELLED)
        self.assertTrue(ctx.cancelled)
        self.assertTrue(ctx.cancellation_requested)

    # 7. Test waiting for user flow
    def test_waiting_for_user_flow(self):
        ctx = RequestContext(goal="Test waiting")
        ctx.transition_to(RequestStatus.ROUTING)
        ctx.transition_to(RequestStatus.WAITING_FOR_USER)
        self.assertEqual(ctx.status, RequestStatus.WAITING_FOR_USER)
        self.assertTrue(ctx.waiting_for_user)

    # 8. Test resume flow
    def test_resume_flow(self):
        ctx = RequestContext(goal="Test resume")
        ctx.transition_to(RequestStatus.ROUTING)
        ctx.transition_to(RequestStatus.WAITING_FOR_USER)
        self.assertTrue(ctx.waiting_for_user)

        # Resume from waiting_for_user -> executing
        ctx.transition_to(RequestStatus.EXECUTING)
        self.assertEqual(ctx.status, RequestStatus.EXECUTING)
        self.assertFalse(ctx.waiting_for_user)

        ctx.transition_to(RequestStatus.VERIFYING)
        ctx.transition_to(RequestStatus.COMPLETED)
        self.assertEqual(ctx.status, RequestStatus.COMPLETED)

    # 9. Test progress reporting
    def test_progress_reporting(self):
        ctx = RequestContext(goal="Test progress")
        ctx.transition_to(RequestStatus.ROUTING)
        ctx.transition_to(RequestStatus.PLANNING)
        ctx.transition_to(RequestStatus.EXECUTING)

        ctx.total_steps = 3
        ctx.current_step = 1
        self.assertEqual(ctx.current_step, 1)
        self.assertEqual(ctx.total_steps, 3)

        d = ctx.to_dict()
        self.assertEqual(d["current_step"], 1)
        self.assertEqual(d["total_steps"], 3)
        self.assertEqual(d["status"], "EXECUTING")

    # 10. Test request_id uniqueness and propagation
    def test_request_id_uniqueness(self):
        ids = {RequestContext().request_id for _ in range(50)}
        self.assertEqual(len(ids), 50)

    # 11. Test concurrent independent requests
    def test_concurrent_independent_requests(self):
        ctx1 = RequestContext(goal="Task 1", source="gui")
        ctx2 = RequestContext(goal="Task 2", source="voice")

        ctx1.transition_to(RequestStatus.ROUTING)
        ctx2.transition_to(RequestStatus.ROUTING)

        ctx1.transition_to(RequestStatus.PLANNING)
        ctx1.transition_to(RequestStatus.EXECUTING)
        ctx1.transition_to(RequestStatus.VERIFYING)
        ctx1.transition_to(RequestStatus.COMPLETED, result="Task 1 Done")

        ctx2.transition_to(RequestStatus.FAILED, error="Task 2 Failed")

        self.assertEqual(ctx1.status, RequestStatus.COMPLETED)
        self.assertEqual(ctx1.result, "Task 1 Done")
        self.assertEqual(ctx2.status, RequestStatus.FAILED)
        self.assertEqual(ctx2.error, "Task 2 Failed")

    # 12. Test EventBus lifecycle events
    def test_event_bus_lifecycle_events(self):
        events_received = []

        self.bus.on("routing_started", lambda d: events_received.append(("routing_started", d)))
        self.bus.on("planning_started", lambda d: events_received.append(("planning_started", d)))
        self.bus.on("execution_started", lambda d: events_received.append(("execution_started", d)))
        self.bus.on("verification_started", lambda d: events_received.append(("verification_started", d)))
        self.bus.on("request_completed", lambda d: events_received.append(("request_completed", d)))

        ctx = RequestContext(goal="Test events")
        ctx.transition_to(RequestStatus.ROUTING, event_bus=self.bus)
        ctx.transition_to(RequestStatus.PLANNING, event_bus=self.bus)
        ctx.transition_to(RequestStatus.EXECUTING, event_bus=self.bus)
        ctx.transition_to(RequestStatus.VERIFYING, event_bus=self.bus)
        ctx.transition_to(RequestStatus.COMPLETED, event_bus=self.bus, result="OK")

        event_names = [e[0] for e in events_received]
        self.assertIn("routing_started", event_names)
        self.assertIn("planning_started", event_names)
        self.assertIn("execution_started", event_names)
        self.assertIn("verification_started", event_names)
        self.assertIn("request_completed", event_names)

        # Check payload
        last_event = events_received[-1][1]
        self.assertEqual(last_event["request_id"], ctx.request_id)
        self.assertEqual(last_event["status"], "COMPLETED")
        self.assertEqual(last_event["result"], "OK")

    # 13. Test FAST_COMMAND lifecycle in JarvisRuntime
    @patch("core.runtime.increment_router_stat")
    @patch("core.intents.fast_command_router.resolve_app_from_cache_with_score")
    def test_fast_command_lifecycle(self, mock_resolve, mock_stats):
        mock_resolve.return_value = ("calculator", "C:\\Windows\\System32\\calc.exe", 100)
        events = []
        self.bus.on("routing_completed", lambda d: events.append("routing_completed"))
        self.bus.on("request_completed", lambda d: events.append("request_completed"))

        runtime = JarvisRuntime(registry=self.registry, dry_run=True, event_bus=self.bus)
        result = runtime.run_task("otevři kalkulačku")

        self.assertTrue(result.ok)
        self.assertEqual(result.route, "FAST_COMMAND")
        ctx = get_current_request()
        self.assertEqual(ctx.status, RequestStatus.COMPLETED)
        self.assertTrue(ctx.completed)
        self.assertIn("routing_completed", events)
        self.assertIn("request_completed", events)

    # 14. Test Planner lifecycle in JarvisRuntime
    @patch("core.runtime.increment_router_stat")
    @patch("core.runtime.Planner")
    def test_planner_lifecycle(self, mock_planner_cls, mock_stats):
        mock_planner = MagicMock()
        mock_planner.plan.return_value = [
            {"tool": "dummy_step", "input": {"id": 1}, "description": "Step 1"},
            {"tool": "dummy_step", "input": {"id": 2}, "description": "Step 2"},
        ]
        mock_planner_cls.return_value = mock_planner

        events = []
        self.bus.on("planning_started", lambda d: events.append("planning_started"))
        self.bus.on("planning_completed", lambda d: events.append("planning_completed"))
        self.bus.on("execution_started", lambda d: events.append("execution_started"))
        self.bus.on("request_completed", lambda d: events.append("request_completed"))

        runtime = JarvisRuntime(registry=self.registry, dry_run=True, event_bus=self.bus)
        result = runtime.run_task("vytvor prezentaci o AI")

        self.assertTrue(result.ok)
        self.assertEqual(result.route, "PLANNER_V2")
        ctx = get_current_request()
        self.assertEqual(ctx.status, RequestStatus.COMPLETED)
        self.assertIn("planning_started", events)
        self.assertIn("planning_completed", events)
        self.assertIn("execution_started", events)
        self.assertIn("request_completed", events)

    # 15. Test backward compatibility properties
    def test_backward_compatibility_properties(self):
        ctx = RequestContext()
        self.assertFalse(ctx.completed)
        self.assertFalse(ctx.cancelled)
        self.assertFalse(ctx.failed)

        # Property setter completed
        ctx.transition_to(RequestStatus.ROUTING)
        ctx.transition_to(RequestStatus.EXECUTING)
        ctx.completed = True
        self.assertEqual(ctx.status, RequestStatus.COMPLETED)
        self.assertTrue(ctx.completed)

        # check_request_context_block
        set_current_request(ctx)
        self.assertTrue(check_request_context_block())

        # Active count tracking
        active = RequestContext.get_active_count()
        self.assertGreater(active, 0)


if __name__ == "__main__":
    unittest.main()
