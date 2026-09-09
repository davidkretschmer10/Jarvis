# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.event_bus import EventBus
from core.executor import Executor, StepExecutionStatus
from core.lifecycle import RequestContext, RequestStatus, reset_current_request
from core.observation import Observation, ObservationType
from core.runtime import JarvisRuntime
from core.state import JarvisState
from core.verification import (
    ApplicationVerifier,
    BaseVerifier,
    BrowserVerifier,
    DirectoryVerifier,
    FileVerifier,
    PassThroughVerifier,
    StepVerifierRegistry,
    UIInteractionVerifier,
    VerificationResult,
    VerificationStatus,
    _get_running_processes_windows,
)
from tools.base import ToolContext
from tools.registry import ToolRegistry


class TestObserveVerifyModels(unittest.TestCase):
    def test_observation_model(self):
        obs = Observation(
            source="test_source",
            type=ObservationType.PROCESS,
            data={"proc": "notepad.exe"},
            confidence=0.95,
            evidence={"pid": 1234},
        )
        d = obs.to_dict()
        self.assertEqual(d["source"], "test_source")
        self.assertEqual(d["type"], "PROCESS")
        self.assertEqual(d["data"], {"proc": "notepad.exe"})
        self.assertEqual(d["confidence"], 0.95)
        self.assertEqual(d["evidence"], {"pid": 1234})

    def test_verification_result_model(self):
        vr = VerificationResult(
            status=VerificationStatus.VERIFIED,
            verifier="ApplicationVerifier",
            expected="proc running",
            observed="proc detected",
            evidence={"found_proc": "calc.exe"},
            message="Active",
        )
        self.assertTrue(vr.is_verified())
        self.assertFalse(vr.is_failed())
        self.assertFalse(vr.is_unknown())
        self.assertFalse(vr.is_not_applicable())
        d = vr.to_dict()
        self.assertEqual(d["status"], "VERIFIED")
        self.assertEqual(d["verifier"], "ApplicationVerifier")

    def test_verifier_is_read_only(self):
        v = ApplicationVerifier()
        self.assertTrue(v.is_read_only)
        fv = FileVerifier()
        self.assertTrue(fv.is_read_only)
        dv = DirectoryVerifier()
        self.assertTrue(dv.is_read_only)
        bv = BrowserVerifier()
        self.assertTrue(bv.is_read_only)
        uv = UIInteractionVerifier()
        self.assertTrue(uv.is_read_only)
        pv = PassThroughVerifier()
        self.assertTrue(pv.is_read_only)


class TestDeterministicVerifiers(unittest.TestCase):
    def test_file_verifier_create_success(self):
        fv = FileVerifier()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello jarvis")
            temp_path = f.name

        try:
            step = {"tool": "write_file", "args": {"file_path": temp_path, "content": "hello"}}
            res = fv.verify(step, {"ok": True})
            self.assertEqual(res.status, VerificationStatus.VERIFIED)
            self.assertTrue(res.is_verified())
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_file_verifier_create_missing_file_fails(self):
        fv = FileVerifier()
        non_existent = os.path.join(tempfile.gettempdir(), "jarvis_missing_test_12345.txt")
        if os.path.exists(non_existent):
            os.remove(non_existent)

        step = {"tool": "write_file", "args": {"file_path": non_existent}}
        res = fv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.FAILED)
        self.assertTrue(res.is_failed())

    def test_file_verifier_delete_success(self):
        fv = FileVerifier()
        non_existent = os.path.join(tempfile.gettempdir(), "jarvis_deleted_file_xyz.txt")
        if os.path.exists(non_existent):
            os.remove(non_existent)

        step = {"tool": "delete_file", "args": {"file_path": non_existent}}
        res = fv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.VERIFIED)

    def test_file_verifier_delete_failure_when_file_still_exists(self):
        fv = FileVerifier()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"still here")
            temp_path = f.name

        try:
            step = {"tool": "delete_file", "args": {"file_path": temp_path}}
            res = fv.verify(step, {"ok": True})
            self.assertEqual(res.status, VerificationStatus.FAILED)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_directory_verifier_create_and_delete(self):
        dv = DirectoryVerifier()
        temp_dir = os.path.join(tempfile.gettempdir(), "jarvis_test_dir_verify")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        try:
            step = {"tool": "create_directory", "args": {"path": temp_dir}}
            res = dv.verify(step, {"ok": True})
            self.assertEqual(res.status, VerificationStatus.VERIFIED)

            # Test delete
            os.rmdir(temp_dir)
            step_del = {"tool": "delete_directory", "args": {"path": temp_dir}}
            res_del = dv.verify(step_del, {"ok": True})
            self.assertEqual(res_del.status, VerificationStatus.VERIFIED)
        finally:
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)

    @patch("core.verification._get_running_processes_windows", return_value=["calculatorapp.exe"])
    @patch("core.verification._get_visible_window_titles_windows", return_value=["Calculator"])
    def test_application_verifier_success(self, mock_win, mock_proc):
        av = ApplicationVerifier()
        step = {"tool": "open_app", "args": {"app_name": "calculator"}}
        res = av.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.VERIFIED)

    @patch("core.verification._get_running_processes_windows", return_value=["cmd.exe"])
    @patch("core.verification._get_visible_window_titles_windows", return_value=[])
    def test_application_verifier_missing_process_fails(self, mock_win, mock_proc):
        av = ApplicationVerifier()
        step = {"tool": "open_app", "args": {"app_name": "calculator"}}
        res = av.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.FAILED)

    def test_ui_interaction_verifier_returns_unknown_without_delta(self):
        uv = UIInteractionVerifier()
        step = {"tool": "mouse_click", "args": {"x": 100, "y": 200}}
        res = uv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.UNKNOWN)
        # CRITICAL invariant: UNKNOWN must not be verified
        self.assertFalse(res.is_verified())

    def test_ui_interaction_verifier_returns_verified_with_explicit_delta(self):
        uv = UIInteractionVerifier()
        step = {"tool": "mouse_click", "args": {"x": 100, "y": 200}}
        res = uv.verify(step, {"ok": True, "observed_delta": True, "delta_evidence": "dialog opened"})
        self.assertEqual(res.status, VerificationStatus.VERIFIED)

    def test_passthrough_verifier_read_only(self):
        pv = PassThroughVerifier()
        step = {"tool": "system_info", "args": {}}
        res = pv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.NOT_APPLICABLE)


class DummyTool:
    def __init__(self, name: str, fn=None, description: str = "test tool", input_schema=None):
        self.name = name
        self.description = description
        self.input_schema = input_schema or {}
        self.fn = fn or (lambda inp, ctx, st: {"ok": True})

    def run(self, tool_input: dict, ctx: ToolContext, state: any) -> dict:
        return self.fn(tool_input, ctx, state)


class TestObserveVerifyExecutionFlow(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.ctx = ToolContext()
        self.state = JarvisState()
        self.event_bus = EventBus()

    def test_test1_open_app_verified(self):
        """TEST 1: open app -> verify process exists -> VERIFIED"""
        self.registry.register(DummyTool("open_app", lambda inp, ctx, st: {"ok": True, "result": "Launched app"}))
        req_ctx = RequestContext(goal="Open calculator", request_id="req-test-1")

        mock_verifier = StepVerifierRegistry(verifiers=[])
        mock_v = MagicMock()
        mock_v.can_verify.return_value = True
        mock_v.verify.return_value = VerificationResult(
            status=VerificationStatus.VERIFIED,
            verifier="MockAppVerifier",
            expected="Calculator running",
            observed="Process found",
            evidence={"found_proc": "calc.exe"},
        )
        mock_verifier.register_verifier(mock_v)

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            verifier=mock_verifier,
        )

        steps = [{"tool": "open_app", "args": {"app_name": "calculator"}}]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], StepExecutionStatus.SUCCESS.value)
        self.assertEqual(results[0]["verification_status"], "VERIFIED")
        self.assertTrue(results[0].is_success)

    def test_test2_tool_ok_true_but_verification_failed_not_success(self):
        """TEST 2: Tool claims ok=True, but verification detects process missing -> FAILED, no success."""
        self.registry.register(DummyTool("open_app", lambda inp, ctx, st: {"ok": True, "result": "Process spawned"}))
        req_ctx = RequestContext(goal="Open missing app", request_id="req-test-2")

        mock_verifier = StepVerifierRegistry(verifiers=[])
        mock_v = MagicMock()
        mock_v.can_verify.return_value = True
        mock_v.verify.return_value = VerificationResult(
            status=VerificationStatus.FAILED,
            verifier="MockAppVerifier",
            expected="Process running",
            observed="Process missing in tasklist",
            evidence={"found_proc": None},
            message="Process not found",
        )
        mock_verifier.register_verifier(mock_v)

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            verifier=mock_verifier,
            max_repairs=0,
            max_replans=0,
        )

        steps = [{"tool": "open_app", "args": {"app_name": "phantom_app"}}]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 1)
        # MUST NOT be marked as SUCCESS
        self.assertFalse(results[0].is_success)
        self.assertEqual(results[0]["status"], StepExecutionStatus.FAILED.value)
        self.assertEqual(results[0]["verification_status"], "FAILED")

    def test_test3_create_file_verified(self):
        """TEST 3: File creation and verified on disk."""
        with tempfile.TemporaryDirectory() as td:
            target_path = os.path.join(td, "jarvis_created.txt")

            def do_create(inp, ctx, st):
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write("content")
                return {"ok": True, "result": "created"}

            self.registry.register(DummyTool("write_file", do_create))
            req_ctx = RequestContext(goal="Create file", request_id="req-test-3")

            executor = Executor(
                registry=self.registry,
                ctx=self.ctx,
                state=self.state,
                request_context=req_ctx,
                event_bus=self.event_bus,
            )

            steps = [{"tool": "write_file", "args": {"file_path": target_path, "content": "content"}}]
            results = executor.run_plan(steps)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["verification_status"], "VERIFIED")
            self.assertTrue(results[0].is_success)

    def test_test4_delete_file_verified(self):
        """TEST 4: Delete file and verified no longer existing."""
        with tempfile.TemporaryDirectory() as td:
            target_path = os.path.join(td, "jarvis_to_delete.txt")
            with open(target_path, "w") as f:
                f.write("delete me")

            def do_delete(inp, ctx, st):
                if os.path.exists(target_path):
                    os.remove(target_path)
                return {"ok": True, "result": "deleted"}

            self.registry.register(DummyTool("delete_file", do_delete))
            req_ctx = RequestContext(goal="Delete file", request_id="req-test-4")

            executor = Executor(
                registry=self.registry,
                ctx=self.ctx,
                state=self.state,
                request_context=req_ctx,
                event_bus=self.event_bus,
            )

            steps = [{"tool": "delete_file", "args": {"file_path": target_path}}]
            results = executor.run_plan(steps)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["verification_status"], "VERIFIED")
            self.assertTrue(results[0].is_success)

    def test_test5_verification_failed_triggers_replan(self):
        """TEST 5: Verification FAILED triggers replan instead of proceeding blindly."""
        self.registry.register(DummyTool("flake_tool", lambda inp, ctx, st: {"ok": True}))
        self.registry.register(DummyTool("recovery_tool", lambda inp, ctx, st: {"ok": True}))

        req_ctx = RequestContext(goal="Test replan", request_id="req-test-5")

        mock_verifier = StepVerifierRegistry(verifiers=[])
        mock_v = MagicMock()
        mock_v.can_verify.return_value = True
        # First check fails, second check (for recovery_tool) succeeds
        mock_v.verify.side_effect = [
            VerificationResult(status=VerificationStatus.FAILED, verifier="MockV", message="Check failed"),
            VerificationResult(status=VerificationStatus.VERIFIED, verifier="MockV", message="Recovery verified"),
        ]
        mock_verifier.register_verifier(mock_v)

        mock_planner = MagicMock()
        mock_planner.replan.return_value = [{"tool": "recovery_tool", "args": {}}]

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            verifier=mock_verifier,
            planner=mock_planner,
            max_repairs=0,
            max_replans=1,
        )

        steps = [{"tool": "flake_tool", "args": {}}]
        results = executor.run_plan(steps)

        mock_planner.replan.assert_called_once()
        call_kwargs = mock_planner.replan.call_args[1]
        self.assertIn("observation", call_kwargs)
        self.assertIn("verification_result", call_kwargs)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["tool"], "recovery_tool")
        self.assertEqual(results[0]["verification_status"], "VERIFIED")

    def test_test6_verification_unknown_not_converted_to_verified(self):
        """TEST 6: UNKNOWN verification status must never be reported as VERIFIED."""
        self.registry.register(DummyTool("type_text", lambda inp, ctx, st: {"ok": True, "result": "Typed text"}))
        req_ctx = RequestContext(goal="Type blind text", request_id="req-test-6")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
        )

        steps = [{"tool": "type_text", "args": {"text": "hello"}}]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["verification_status"], "UNKNOWN")
        self.assertNotEqual(results[0]["verification_status"], "VERIFIED")

    def test_test7_verification_failed_during_repair_reaches_terminal_state(self):
        """TEST 7: Verification FAILED during repair -> terminal state according to budgets."""
        self.registry.register(DummyTool("bad_tool", lambda inp, ctx, st: {"ok": True}))
        req_ctx = RequestContext(goal="Fail repair", request_id="req-test-7")

        mock_verifier = StepVerifierRegistry(verifiers=[])
        mock_v = MagicMock()
        mock_v.can_verify.return_value = True
        # Always fails verification
        mock_v.verify.return_value = VerificationResult(
            status=VerificationStatus.FAILED, verifier="StrictMock", message="Permanent failure"
        )
        mock_verifier.register_verifier(mock_v)

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            verifier=mock_verifier,
            max_repairs=1,
            max_replans=0,
        )
        # Mock _attempt_repair to claim repair ran, but re-verification will catch it!
        executor._attempt_repair = MagicMock(return_value=True)

        steps = [{"tool": "bad_tool", "args": {}}]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], StepExecutionStatus.FAILED.value)
        self.assertEqual(results[0]["verification_status"], "FAILED")
        self.assertFalse(results[0].is_success)

    def test_test8_cancellation_during_verification(self):
        """TEST 8: Cancellation during verification results in CANCELLED status, no replan."""
        self.registry.register(DummyTool("tool_run", lambda inp, ctx, st: {"ok": True}))
        req_ctx = RequestContext(goal="Cancel verify", request_id="req-test-8")

        mock_verifier = StepVerifierRegistry(verifiers=[])
        mock_v = MagicMock()
        mock_v.can_verify.return_value = True

        def cancel_in_verify(*args, **kwargs):
            req_ctx.cancellation_requested = True
            req_ctx.is_cancelled = True
            req_ctx.status = RequestStatus.CANCELLED
            return VerificationResult(status=VerificationStatus.VERIFIED, verifier="CancelMock")

        mock_v.verify.side_effect = cancel_in_verify
        mock_verifier.register_verifier(mock_v)

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            verifier=mock_verifier,
            max_repairs=1,
            max_replans=1,
        )

        steps = [{"tool": "tool_run", "args": {}}]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], StepExecutionStatus.CANCELLED.value)

    def test_test9_timeout_during_verification(self):
        """TEST 9: Timeout in context results in verification FAILED and aborted task."""
        self.registry.register(DummyTool("tool_run", lambda inp, ctx, st: {"ok": True}))
        req_ctx = RequestContext(goal="Timeout verify", request_id="req-test-9")
        req_ctx.is_timed_out = True

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            max_repairs=0,
            max_replans=0,
        )

        steps = [{"tool": "tool_run", "args": {}}]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], StepExecutionStatus.FAILED.value)
        self.assertEqual(results[0]["verification_status"], "FAILED")

    def test_test10_multistep_barrier_no_continuation_after_unverified_failure(self):
        """TEST 10: Multi-step task: if step 1 fails verification, step 2 and step 3 must NEVER run."""
        step2_ran = False
        step3_ran = False

        def step1_exec(inp, ctx, st):
            return {"ok": True}

        def step2_exec(inp, ctx, st):
            nonlocal step2_ran
            step2_ran = True
            return {"ok": True}

        def step3_exec(inp, ctx, st):
            nonlocal step3_ran
            step3_ran = True
            return {"ok": True}

        self.registry.register(DummyTool("step1_tool", step1_exec))
        self.registry.register(DummyTool("step2_tool", step2_exec))
        self.registry.register(DummyTool("step3_tool", step3_exec))

        mock_verifier = StepVerifierRegistry(verifiers=[])
        mock_v = MagicMock()
        mock_v.can_verify.return_value = True
        mock_v.verify.return_value = VerificationResult(
            status=VerificationStatus.FAILED, verifier="BlockerMock", message="Step 1 verification failed"
        )
        mock_verifier.register_verifier(mock_v)

        req_ctx = RequestContext(goal="Multi-step barrier", request_id="req-test-10")
        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            verifier=mock_verifier,
            max_repairs=0,
            max_replans=0,
        )

        steps = [
            {"tool": "step1_tool", "args": {}},
            {"tool": "step2_tool", "args": {}},
            {"tool": "step3_tool", "args": {}},
        ]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 1)
        self.assertFalse(step2_ran, "Step 2 should NEVER execute when step 1 verification failed!")
        self.assertFalse(step3_ran, "Step 3 should NEVER execute when step 1 verification failed!")
        self.assertEqual(results[0]["status"], StepExecutionStatus.FAILED.value)

    def test_request_id_consistency_across_layers(self):
        """Verify request_id is consistently propagated through the entire loop and events."""
        received_events = []
        self.event_bus.on("verification_started", lambda d: received_events.append(("v_start", d)))
        self.event_bus.on("verification_completed", lambda d: received_events.append(("v_comp", d)))
        self.event_bus.on("step_completed", lambda d: received_events.append(("step_comp", d)))

        self.registry.register(DummyTool("test_tool", lambda inp, ctx, st: {"ok": True}))
        req_ctx = RequestContext(goal="Check request_id", request_id="req-consistent-999")

        mock_verifier = StepVerifierRegistry(verifiers=[])
        mock_v = MagicMock()
        mock_v.can_verify.return_value = True
        mock_v.verify.return_value = VerificationResult(
            status=VerificationStatus.VERIFIED, verifier="IdMock"
        )
        mock_verifier.register_verifier(mock_v)

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            verifier=mock_verifier,
        )

        steps = [{"tool": "test_tool", "args": {}}]
        executor.run_plan(steps)

        for ev_name, payload in received_events:
            self.assertEqual(
                payload.get("request_id"),
                "req-consistent-999",
                f"Event {ev_name} had inconsistent request_id: {payload}",
            )


class TestRealWindowsIntegration(unittest.TestCase):
    def test_real_windows_processes_inspection(self):
        """Tests that _get_running_processes_windows successfully reads the real Windows process table."""
        if os.name != "nt":
            self.skipTest("Windows-only test")

        procs = _get_running_processes_windows()
        self.assertIsInstance(procs, list)
        self.assertGreater(len(procs), 0)
        # explorer.exe is guaranteed to run in any standard user desktop session
        self.assertTrue(
            any("explorer" in p for p in procs),
            f"explorer.exe expected in running processes on Windows, got sample: {procs[:10]}",
        )

    def test_real_windows_temp_file_verification(self):
        """Real file creation and verification on Windows filesystem."""
        fv = FileVerifier()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Jarvis real windows test content")
            real_path = f.name

        try:
            step = {"tool": "write_file", "args": {"file_path": real_path, "content": "Jarvis real windows"}}
            res = fv.verify(step, {"ok": True})
            self.assertEqual(res.status, VerificationStatus.VERIFIED)
            self.assertTrue(res.is_verified())
        finally:
            if os.path.exists(real_path):
                os.remove(real_path)

        # Verify deletion on real filesystem
        step_del = {"tool": "delete_file", "args": {"file_path": real_path}}
        res_del = fv.verify(step_del, {"ok": True})
        self.assertEqual(res_del.status, VerificationStatus.VERIFIED)


if __name__ == "__main__":
    unittest.main()
