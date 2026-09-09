# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from core.event_bus import EventBus
from core.executor import Executor, StepExecutionStatus
from core.lifecycle import RequestContext, reset_current_request
from core.security_policy import SecurityPolicy
from core.state import JarvisState
from tools.base import ToolContext
from tools.registry import build_default_registry


class TestWindowsDeterministicE2E(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="jarvis_e2e_")
        self.ctx = ToolContext(workspace_root=self.tmp_dir)
        self.state = JarvisState()
        self.event_bus = EventBus()
        self.registry = build_default_registry()
        self.policy = SecurityPolicy()

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_scenario1_create_test_file_verified(self):
        """SCENARIO 1: Create test file -> Security -> create_file -> Verify."""
        target_path = os.path.join(self.tmp_dir, "scenario1_output.txt")
        req_ctx = RequestContext(goal="Vytvoř testovací soubor", request_id="scen-1")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            security_policy=self.policy,
        )

        steps = [
            {
                "tool": "create_file",
                "args": {"path": target_path, "content": "Scenario 1 content verification"},
            }
        ]

        results = executor.run_plan(steps)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].is_success)
        self.assertEqual(results[0].verification_status, "VERIFIED")
        self.assertTrue(os.path.isfile(target_path))
        with open(target_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "Scenario 1 content verification")

    def test_scenario2_create_file_then_move_verified(self):
        """SCENARIO 2: Create file then move it -> step 1: create -> verify, step 2: move -> verify."""
        init_path = os.path.join(self.tmp_dir, "initial_data.txt")
        moved_path = os.path.join(self.tmp_dir, "final_data.txt")
        req_ctx = RequestContext(goal="Vytvoř soubor a potom ho přesuň", request_id="scen-2")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            security_policy=self.policy,
        )

        steps = [
            {"tool": "create_file", "args": {"path": init_path, "content": "E2E Move Test"}},
            {"tool": "move_file", "args": {"source": init_path, "destination": moved_path}},
        ]

        results = executor.run_plan(steps)
        self.assertEqual(len(results), 2)

        # Step 1: create verified
        self.assertTrue(results[0].is_success)
        self.assertEqual(results[0].verification_status, "VERIFIED")

        # Step 2: move verified
        self.assertTrue(results[1].is_success)
        self.assertEqual(results[1].verification_status, "VERIFIED")
        self.assertFalse(os.path.exists(init_path))
        self.assertTrue(os.path.isfile(moved_path))

    def test_scenario3_and_4_safe_process_lifecycle(self):
        """SCENARIO 3 & 4: Launch harmless background process -> verify PID, then terminate -> verify absence."""
        req_ctx = RequestContext(goal="Spusť a ukonči bezpečný testovací proces", request_id="scen-3-4")

        # Start harmless sleep process
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        pid = proc.pid
        time.sleep(0.3)

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            security_policy=self.policy,
        )

        try:
            # Scenario 3: verify presence
            steps = [{"tool": "process_exists", "args": {"pid": pid}}]
            results_exists = executor.run_plan(steps)
            self.assertEqual(len(results_exists), 1)
            self.assertTrue(results_exists[0].is_success)
            self.assertEqual(results_exists[0].verification_status, "VERIFIED")

            # Scenario 4: terminate requires confirmation (HIGH risk)
            steps_term = [{"tool": "terminate_process", "args": {"pid": pid}}]
            results_paused = executor.run_plan(steps_term)
            self.assertEqual(len(results_paused), 1)
            self.assertEqual(results_paused[0].status, StepExecutionStatus.WAITING_FOR_CONFIRMATION)

            # Authorize the confirmed action and execute
            self.state.data["action_authorized"] = True
            results_term = executor.run_plan(steps_term)
            self.assertEqual(len(results_term), 1)
            self.assertTrue(results_term[0].is_success)
            self.assertEqual(results_term[0].verification_status, "VERIFIED")
        finally:
            if proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=2.0)
                except Exception:
                    pass

    def test_scenario5_system_path_denial(self):
        """SCENARIO 5: Attempt destructive action on C:\Windows -> DENIED by SecurityPolicy."""
        windir = os.environ.get("WINDIR", r"C:\Windows")
        target_path = os.path.join(windir, "System32", "e2e_forbidden.dll")
        req_ctx = RequestContext(goal="Zapiš do System32", request_id="scen-5")

        executor = Executor(
            registry=self.registry,
            ctx=self.ctx,
            state=self.state,
            request_context=req_ctx,
            event_bus=self.event_bus,
            security_policy=self.policy,
        )

        steps = [{"tool": "delete_file", "args": {"path": target_path}}]
        results = executor.run_plan(steps)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].is_success)
        self.assertEqual(results[0].status, StepExecutionStatus.TERMINAL_ERROR)
        self.assertEqual(results[0].execution_status, "denied")
        self.assertTrue(results[0].output.get("security_denied", False))


if __name__ == "__main__":
    unittest.main()
