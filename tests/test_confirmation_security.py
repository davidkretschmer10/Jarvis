"""Tests for Confirmation Security, Request Isolation, Expiration, and Invariants."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock

from core.confirmation import ConfirmationManager, ConfirmationRequest, ConfirmationStatus
from core.executor import Executor, StepExecutionStatus
from core.lifecycle import RequestContext, RequestStatus, reset_current_request
from core.runtime import JarvisRuntime, RequestExecutionStatus
from core.security_policy import ActionRisk, PolicyDecision, SecurityPolicy, ToolCapability
from core.state import JarvisState
from tools.base import ToolContext
from tools.registry import ToolRegistry


class DummyHighRiskTool:
    name = "dummy_high_tool"
    description = "A dummy high risk tool for testing."
    capability = ToolCapability.DELETE_FILE
    risk = ActionRisk.HIGH
    timeout = 10.0
    input_schema = {
        "type": "object",
        "properties": {"target": {"type": "string"}},
        "required": ["target"],
    }

    def run(self, tool_input, ctx, state):
        return {"ok": True, "result": f"Deleted {tool_input.get('target')}"}


class DummySafeTool:
    name = "dummy_safe_tool"
    description = "A dummy safe tool for testing."
    capability = ToolCapability.READ_FILE
    risk = ActionRisk.SAFE
    timeout = 10.0
    input_schema = {
        "type": "object",
        "properties": {"target": {"type": "string"}},
        "required": ["target"],
    }

    def run(self, tool_input, ctx, state):
        return {"ok": True, "result": f"Read {tool_input.get('target')}"}


class TestConfirmationSecurity(unittest.TestCase):
    def setUp(self):
        self.cm = ConfirmationManager(default_ttl_seconds=300.0)
        self.registry = ToolRegistry()
        self.registry.register(DummyHighRiskTool())
        self.registry.register(DummySafeTool())

    # 7. confirmation required
    def test_07_confirmation_required(self):
        conf = self.cm.create_confirmation(
            request_id="req_123",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="important.txt",
            summary="Nevratne smazani",
        )
        self.assertEqual(conf.status, ConfirmationStatus.PENDING)
        self.assertTrue(conf.is_valid_pending)
        self.assertFalse(conf.is_approved)

    # 8. confirmation approved
    def test_08_confirmation_approved(self):
        self.cm.create_confirmation(
            request_id="req_123",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="important.txt",
            summary="Nevratne smazani",
        )
        ok = self.cm.approve("req_123", 1, "dummy_high_tool")
        self.assertTrue(ok)
        conf = self.cm.get_confirmation("req_123", 1, "dummy_high_tool")
        self.assertIsNotNone(conf)
        self.assertTrue(conf.is_approved)
        self.assertEqual(conf.status, ConfirmationStatus.APPROVED)

    # 9. confirmation denied
    def test_09_confirmation_denied(self):
        self.cm.create_confirmation(
            request_id="req_123",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="important.txt",
            summary="Nevratne smazani",
        )
        ok = self.cm.deny("req_123", 1, "dummy_high_tool")
        self.assertTrue(ok)
        conf = self.cm.get_confirmation("req_123", 1, "dummy_high_tool")
        self.assertEqual(conf.status, ConfirmationStatus.DENIED)
        self.assertFalse(conf.is_approved)

    # 10. confirmation expired
    def test_10_confirmation_expired(self):
        conf = self.cm.create_confirmation(
            request_id="req_123",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="important.txt",
            summary="Nevratne smazani",
            ttl_seconds=0.01,  # Expire almost instantly
        )
        time.sleep(0.05)
        self.assertTrue(conf.is_expired)
        # Cannot approve an expired confirmation
        self.assertFalse(conf.approve())
        self.assertEqual(conf.status, ConfirmationStatus.EXPIRED)

    # 11. confirmation request_id mismatch
    def test_11_confirmation_request_id_mismatch(self):
        self.cm.create_confirmation(
            request_id="req_AAA",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="important.txt",
            summary="Nevratne smazani",
        )
        # Attempt to approve with wrong request_id
        ok = self.cm.approve("req_BBB", 1, "dummy_high_tool")
        self.assertFalse(ok)
        conf = self.cm.get_confirmation("req_AAA", 1, "dummy_high_tool")
        self.assertEqual(conf.status, ConfirmationStatus.PENDING)

    # 12. confirmation step_id mismatch
    def test_12_confirmation_step_id_mismatch(self):
        self.cm.create_confirmation(
            request_id="req_AAA",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="important.txt",
            summary="Nevratne smazani",
        )
        ok = self.cm.approve("req_AAA", 2, "dummy_high_tool")
        self.assertFalse(ok)

    # 13. confirmation tool mismatch
    def test_13_confirmation_tool_mismatch(self):
        self.cm.create_confirmation(
            request_id="req_AAA",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="important.txt",
            summary="Nevratne smazani",
        )
        ok = self.cm.approve("req_AAA", 1, "other_tool")
        self.assertFalse(ok)

    # 14. Request A confirmation cannot authorize B
    def test_14_request_a_cannot_authorize_b(self):
        self.cm.create_confirmation(
            request_id="req_A",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="file_a.txt",
            summary="Delete file A",
        )
        self.cm.create_confirmation(
            request_id="req_B",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="file_b.txt",
            summary="Delete file B",
        )

        # Approve A
        self.cm.approve("req_A", 1, "dummy_high_tool")

        conf_a = self.cm.get_confirmation("req_A", 1, "dummy_high_tool")
        conf_b = self.cm.get_confirmation("req_B", 1, "dummy_high_tool")
        self.assertTrue(conf_a.is_approved)
        self.assertEqual(conf_b.status, ConfirmationStatus.PENDING)
        self.assertFalse(conf_b.is_approved)

    # 15. unknown tool -> denied in executor
    def test_15_unknown_tool_rejected_in_executor(self):
        state = JarvisState()
        ctx = ToolContext()
        req_ctx = reset_current_request("test_unknown", source="test")
        executor = Executor(
            registry=self.registry,
            ctx=ctx,
            state=state,
            request_context=req_ctx,
            confirmation_manager=self.cm,
        )
        results = executor.run_plan([{"tool": "completely_unknown_tool", "input": {}}])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, StepExecutionStatus.TERMINAL_ERROR)
        self.assertIn("Unknown tool", results[0].error)

    # 16. invalid tool arguments -> denied in executor
    def test_16_invalid_arguments_rejected_in_executor(self):
        state = JarvisState()
        ctx = ToolContext()
        req_ctx = reset_current_request("test_invalid_args", source="test")
        executor = Executor(
            registry=self.registry,
            ctx=ctx,
            state=state,
            request_context=req_ctx,
            confirmation_manager=self.cm,
        )
        # DummyHighRiskTool requires 'target' parameter
        results = executor.run_plan([{"tool": "dummy_high_tool", "input": {}}])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, StepExecutionStatus.TERMINAL_ERROR)
        self.assertIn("Invalid tool arguments", results[0].error)

    # 18 & 19. Planner cannot bypass security & Executor enforces security
    def test_18_19_executor_enforces_security_planner_cannot_bypass(self):
        state = JarvisState()
        ctx = ToolContext()
        req_ctx = reset_current_request("test_security_gate", source="test")
        executor = Executor(
            registry=self.registry,
            ctx=ctx,
            state=state,
            request_context=req_ctx,
            confirmation_manager=self.cm,
        )
        # High risk tool without confirmation must pause with WAITING_FOR_CONFIRMATION
        results = executor.run_plan([{"tool": "dummy_high_tool", "input": {"target": "critical.txt"}}])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, StepExecutionStatus.WAITING_FOR_CONFIRMATION)
        self.assertEqual(req_ctx.status, RequestStatus.WAITING_FOR_USER)
        self.assertIn("pending_confirmation", state.data)

        # Now approve with exact binding and resume
        self.cm.approve(req_ctx.request_id, 1, "dummy_high_tool")
        runtime = JarvisRuntime(registry=self.registry, confirmation_manager=self.cm)
        res = runtime.resume_task(
            goal="test_security_gate",
            steps=[{"tool": "dummy_high_tool", "input": {"target": "critical.txt"}}],
            state=state,
            start_index=0,
            expected_request_id=req_ctx.request_id,
            request_context=req_ctx,
        )
        self.assertTrue(res.ok)
        self.assertEqual(res.status, RequestExecutionStatus.COMPLETED)

    # 25. cancellation invalidates pending confirmation
    def test_25_cancellation_invalidates_pending_confirmation(self):
        conf = self.cm.create_confirmation(
            request_id="req_to_cancel",
            step_id=1,
            tool="dummy_high_tool",
            capability=ToolCapability.DELETE_FILE,
            risk=ActionRisk.HIGH,
            resource="file.txt",
            summary="Delete",
        )
        self.assertEqual(conf.status, ConfirmationStatus.PENDING)
        runtime = JarvisRuntime(registry=self.registry, confirmation_manager=self.cm)
        runtime.cancel_task(request_id="req_to_cancel", reason="Cancelled by user")

        conf_after = self.cm.get_confirmation("req_to_cancel", 1, "dummy_high_tool")
        self.assertEqual(conf_after.status, ConfirmationStatus.DENIED)
        self.assertFalse(conf_after.is_approved)

    # 34. concurrent confirmations stay isolated
    def test_34_concurrent_confirmations_isolated(self):
        # 10 concurrent requests
        for i in range(10):
            self.cm.create_confirmation(
                request_id=f"req_{i}",
                step_id=1,
                tool="dummy_high_tool",
                capability=ToolCapability.DELETE_FILE,
                risk=ActionRisk.HIGH,
                resource=f"file_{i}.txt",
                summary=f"Delete file {i}",
            )

        # Only approve even requests
        for i in range(0, 10, 2):
            self.cm.approve(f"req_{i}", 1, "dummy_high_tool")

        for i in range(10):
            conf = self.cm.get_confirmation(f"req_{i}", 1, "dummy_high_tool")
            if i % 2 == 0:
                self.assertTrue(conf.is_approved)
            else:
                self.assertEqual(conf.status, ConfirmationStatus.PENDING)
                self.assertFalse(conf.is_approved)

    # Architecture Invariants: GUI / Voice / CLI / HTTP all use same policy
    def test_architecture_invariants_runtime_gateway(self):
        runtime = JarvisRuntime(registry=self.registry, confirmation_manager=self.cm)
        # All entry points go through runtime.run_task / resume_task
        self.assertIsInstance(runtime.security_policy, SecurityPolicy)
        self.assertIsInstance(runtime.confirmation_manager, ConfirmationManager)


if __name__ == "__main__":
    unittest.main()
