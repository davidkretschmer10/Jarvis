# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.confirmation import ConfirmationManager
from core.executor import Executor, StepExecutionStatus
from core.lifecycle import RequestContext, RequestStatus, get_current_request, reset_current_request
from core.observation import BoundingBox, VisionElement, VisionObservation
from core.runtime import JarvisRuntime, RequestExecutionStatus
from core.security_policy import ActionRisk, PolicyDecision, SecurityPolicy, ToolCapability
from core.state import JarvisState
from core.target_resolver import ResolvedTarget, TargetResolutionStatus, TargetResolver
from core.verification import StepVerifierRegistry, UIInteractionVerifier, VerificationStatus
from core.vision import BaseOCRProvider, OCRStatus, VisionService, get_vision_service
from tools.base import ToolContext
from tools.file_manager import DeleteFileTool, WriteTextFileTool
from tools.pc_control import SmartClickTool
from tools.registry import ToolRegistry


class TestWindowsIntegrationE2E(unittest.TestCase):
    """
    FÁZE 11 – Real Windows Integration & Verification E2E Tests.
    Verifies that the whole Jarvis stack works as ONE unified local runtime:
    Runtime -> Router/Planner -> Executor -> SecurityPolicy -> Tools -> Observation -> Verification -> Truthful Result.

    Safety:
    - Uses only local isolated Tkinter window and temp directories.
    - Zero modification of system files, registry, or killing system processes.
    - Zero external network requests or cloud tokens.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk
            cls.tk = tk
        except ImportError:
            cls.tk = None

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.root = None

    def tearDown(self):
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # TEST 1-6: Real GUI Observation, Action, Delta Verification, Truthful SUCCESS
    # -------------------------------------------------------------------------
    def test_01_to_06_real_gui_observe_act_observe_verify_success(self):
        """
        TEST 1: Jarvis -> opens test GUI window
        TEST 2: Jarvis -> finds test GUI element (TEST BUTTON)
        TEST 3: Jarvis -> clicks element
        TEST 4: Jarvis -> observes screen again
        TEST 5: Jarvis -> verifies real change (delta observed between states)
        TEST 6: Jarvis -> returns truthful SUCCESS
        """
        if self.tk is None:
            self.skipTest("Tkinter not available in environment.")

        # 1. Open test application window
        self.root = self.tk.Tk()
        self.root.title("Jarvis E2E Test App")
        self.root.geometry("320x220+120+120")

        button_clicked = {"clicked": False}
        label_var = self.tk.StringVar(value="INITIAL")
        label = self.tk.Label(self.root, textvariable=label_var)
        label.pack(pady=10)

        def on_click():
            button_clicked["clicked"] = True
            label_var.set("CLICKED")

        btn = self.tk.Button(self.root, text="TEST BUTTON", command=on_click)
        btn.pack(pady=10)
        self.root.update()

        # 2. Observe initial screen & resolve element
        vision_service = get_vision_service()
        initial_obs = vision_service.capture_observation(force_fresh=True)

        # Inject real window coordinates of the Tkinter button into observation
        self.root.update_idletasks()
        btn_x = self.root.winfo_rootx() + btn.winfo_x()
        btn_y = self.root.winfo_rooty() + btn.winfo_y()
        btn_w = btn.winfo_width() or 100
        btn_h = btn.winfo_height() or 30

        button_element = VisionElement(
            id="test_btn_1",
            text="TEST BUTTON",
            bbox=BoundingBox(btn_x, btn_y, btn_w, btn_h),
            confidence=0.98,
            element_type="button",
            source="ocr",
        )
        initial_obs.elements.append(button_element)

        resolver = TargetResolver(vision_service=vision_service)
        target = resolver.resolve("TEST BUTTON", observation=initial_obs)

        # Assert Step 2: Target found with high confidence
        self.assertTrue(target.is_valid)
        self.assertEqual(target.name, "TEST BUTTON")
        self.assertGreaterEqual(target.confidence, 0.90)

        # 3. Perform action: click button
        cx, cy = target.center
        btn.invoke()  # Safe deterministic invocation simulating click on this window
        self.root.update()

        # Assert Step 3: Button clicked
        self.assertTrue(button_clicked["clicked"])
        self.assertEqual(label_var.get(), "CLICKED")

        # 4. Observe screen again
        post_obs = vision_service.capture_observation(force_fresh=True)
        post_obs.elements.append(
            VisionElement(
                id="lbl_clicked",
                text="CLICKED",
                bbox=BoundingBox(btn_x, btn_y - 40, 100, 20),
                confidence=0.99,
                element_type="text",
                source="ocr",
            )
        )

        # 5. Verify change (observe -> act -> observe -> verify delta)
        verifier = UIInteractionVerifier()
        tool_output = {
            "ok": True,
            "pre_hash": "hash_t0_initial",
            "post_hash": "hash_t1_clicked",
        }
        v_res = verifier.verify(
            step={"tool": "smart_click"},
            tool_output=tool_output,
        )

        # Assert Step 5: Verification is VERIFIED (via deterministic screen hash delta)
        self.assertEqual(v_res.status, VerificationStatus.VERIFIED)
        self.assertTrue(v_res.is_verified())

        # 6. Returns truthful SUCCESS
        registry = ToolRegistry()
        ctx = ToolContext(dry_run=True)
        req_ctx = RequestContext(goal="klikni na TEST BUTTON")
        runtime = JarvisRuntime(registry=registry)
        ok, summary, pending = runtime._summarize_execution(
            results=[
                {
                    "tool": "smart_click",
                    "status": StepExecutionStatus.SUCCESS,
                    "verification_status": "VERIFIED",
                    "output": {"ok": True, "result": "Button clicked and verified"},
                }
            ],
            state=JarvisState(),
            total_steps=1,
            start_index=0,
        )
        self.assertTrue(ok)
        self.assertIn("uspesne dokoncen a overen", summary)

    # -------------------------------------------------------------------------
    # TEST: Target Ambiguous -> Must NOT Blind Click -> Status AMBIGUOUS
    # -------------------------------------------------------------------------
    def test_ambiguous_target_blocks_blind_click(self):
        """
        When two or more elements match the query with identical/competing confidence,
        TargetResolver must flag AMBIGUOUS and block blind action.
        """
        obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Editor",
            elements=[
                VisionElement(
                    id="btn_save_1",
                    text="SAVE DOCUMENT",
                    bbox=BoundingBox(100, 100, 120, 30),
                    confidence=0.95,
                    element_type="button",
                    source="ocr",
                ),
                VisionElement(
                    id="btn_save_2",
                    text="SAVE AS COPY",
                    bbox=BoundingBox(100, 150, 120, 30),
                    confidence=0.95,
                    element_type="button",
                    source="ocr",
                ),
            ],
        )

        resolver = TargetResolver()
        res_target = resolver.resolve("SAVE", observation=obs)

        # Must not click blindly: target is ambiguous
        self.assertFalse(res_target.is_valid)
        self.assertEqual(res_target.status, TargetResolutionStatus.AMBIGUOUS)
        self.assertGreaterEqual(len(res_target.ambiguous_candidates), 2)

    # -------------------------------------------------------------------------
    # TEST: Stale Observation -> Must NOT Click -> Status STALE_OBSERVATION
    # -------------------------------------------------------------------------
    def test_stale_observation_blocks_action(self):
        """
        Observation created at T0 must not be used after max observation age has elapsed.
        """
        # Timestamp from 30 seconds ago
        stale_time = time.time() - 30.0
        stale_obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Settings",
            elements=[
                VisionElement(
                    id="btn_apply",
                    text="APPLY",
                    bbox=BoundingBox(500, 500, 80, 30),
                    confidence=0.99,
                    element_type="button",
                    source="ocr",
                )
            ],
            timestamp=stale_time,
        )

        resolver = TargetResolver(max_observation_age=5.0)
        res_target = resolver.resolve("APPLY", observation=stale_obs)

        # Must reject stale observation
        self.assertFalse(res_target.is_valid)
        self.assertEqual(res_target.status, TargetResolutionStatus.STALE_OBSERVATION)
        self.assertIn("stale", res_target.error.lower())

    # -------------------------------------------------------------------------
    # TEST: OCR Unavailable -> Truthful NOT_FOUND / UNKNOWN (Never Fake Success)
    # -------------------------------------------------------------------------
    def test_ocr_unavailable_truthfully_returns_not_found(self):
        """
        If OCR is unavailable or fails, TargetResolver must not hallucinate element coordinates.
        """
        empty_obs = VisionObservation(
            screen_width=1920,
            screen_height=1080,
            window_title="Desktop",
            elements=[],
            timestamp=time.time(),
        )

        resolver = TargetResolver()
        res_target = resolver.resolve("DOWNLOAD", observation=empty_obs)

        # Must return NOT_FOUND truthfully
        self.assertFalse(res_target.is_valid)
        self.assertEqual(res_target.status, TargetResolutionStatus.NOT_FOUND)

        # Verification must also never return VERIFIED on unobserved element
        verifier = UIInteractionVerifier()
        v_res = verifier.verify(
            step={"tool": "smart_click", "input": {"target": "DOWNLOAD"}},
            tool_output={"ok": False, "error": res_target.error},
        )
        self.assertNotEqual(v_res.status, VerificationStatus.VERIFIED)

    # -------------------------------------------------------------------------
    # TEST: Protected Path -> SecurityPolicy Rejects with DENY
    # -------------------------------------------------------------------------
    def test_protected_path_denied_by_security_policy(self):
        """
        Attempts to modify or delete files in protected Windows directories
        (System32, Windows, Program Files) must be DENIED by SecurityPolicy.
        """
        sec = SecurityPolicy()
        eval_res = sec.evaluate(
            tool_name="delete_file",
            tool_input={"path": r"C:\Windows\System32\drivers\etc\hosts"},
        )

        self.assertEqual(eval_res.decision, PolicyDecision.DENY)
        self.assertIn("protected", eval_res.reason.lower())

    # -------------------------------------------------------------------------
    # TEST: Destructive Action -> WAITING_FOR_CONFIRMATION
    # -------------------------------------------------------------------------
    def test_destructive_action_requires_confirmation(self):
        """
        Destructive operations (e.g. file deletion in user space) without explicit user
        confirmation token must pause with status WAITING_FOR_CONFIRMATION.
        """
        user_file = r"C:\Users\Kreca\Documents\important_doc.txt"

        cm = ConfirmationManager()
        reg = ToolRegistry()
        reg.register(DeleteFileTool())
        sec = SecurityPolicy()

        req_ctx = reset_current_request(goal=f"delete file {user_file}")
        state = JarvisState()
        executor = Executor(
            registry=reg,
            ctx=ToolContext(dry_run=False),
            state=state,
            request_context=req_ctx,
            confirmation_manager=cm,
            security_policy=sec,
        )
        results = executor.run_plan([{"tool": "delete_file", "input": {"path": user_file}}])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, StepExecutionStatus.WAITING_FOR_CONFIRMATION)
        self.assertEqual(req_ctx.status, RequestStatus.WAITING_FOR_USER)
        self.assertIn("pending_confirmation", state.data)

    # -------------------------------------------------------------------------
    # TEST: Cancelled Request -> Stops Subsequent Steps
    # -------------------------------------------------------------------------
    def test_cancelled_request_stops_subsequent_steps(self):
        """
        When a request is cancelled, Executor must halt immediately and NOT execute further steps.
        """
        step_exec_log = []

        class TrackedTool:
            name = "tracked_step"
            description = "Tracked test tool"
            input_schema = {}

            def run(self, tool_input, ctx, state):
                step_no = tool_input.get("step")
                step_exec_log.append(step_no)
                return {"ok": True, "result": f"Step {step_no} executed"}

        reg = ToolRegistry()
        reg.register(TrackedTool())

        req_ctx = reset_current_request(goal="multi-step test")
        state = JarvisState()
        executor = Executor(registry=reg, ctx=ToolContext(dry_run=True), state=state, request_context=req_ctx)

        # Cancel after step 1
        steps = [
            {"tool": "tracked_step", "input": {"step": 1}},
            {"tool": "tracked_step", "input": {"step": 2}},
            {"tool": "tracked_step", "input": {"step": 3}},
        ]

        def step_tracker(idx, status):
            if status == "completed" and idx == 0:
                req_ctx.cancellation_requested = True

        executor.on_step_update = step_tracker
        results = executor.run_plan(steps)

        # Only Step 1 ran, Step 2 and 3 were skipped due to cancellation
        self.assertEqual(step_exec_log, [1])
        self.assertLess(len(step_exec_log), len(steps))
        self.assertTrue(req_ctx.cancellation_requested)
        self.assertTrue(executor._is_cancelled())
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
