# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import sys
import time
import unittest

from core.security_policy import ActionRisk, PolicyDecision, SecurityPolicy, ToolCapability
from tools.base import ToolContext
from tools.pc_control import GetProcessInfoTool, ProcessExistsTool, TerminateProcessTool


class TestProcessTools(unittest.TestCase):
    def setUp(self):
        self.ctx = ToolContext()
        self.test_proc = None

    def tearDown(self):
        if self.test_proc and self.test_proc.poll() is None:
            try:
                self.test_proc.kill()
                self.test_proc.wait(timeout=2.0)
            except Exception:
                pass

    def test_safe_real_process_lifecycle(self):
        # 1. Start a harmless background Python sleep process
        self.test_proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        pid = self.test_proc.pid
        time.sleep(0.3)

        # 2. Test process_exists tool
        exists_tool = ProcessExistsTool()
        res_exists = exists_tool.run({"pid": pid}, self.ctx, None)
        self.assertTrue(res_exists["ok"])
        self.assertTrue(res_exists["exists"])

        # 3. Test get_process_info tool
        info_tool = GetProcessInfoTool()
        res_info = info_tool.run({"pid": pid}, self.ctx, None)
        self.assertTrue(res_info["ok"])
        self.assertGreaterEqual(res_info["count"], 1)

        # 4. Test terminate_process tool
        term_tool = TerminateProcessTool()
        res_term = term_tool.run({"pid": pid}, self.ctx, None)
        self.assertTrue(res_term["ok"])

        # Wait for termination to register
        time.sleep(0.3)

        # 5. Verify process is now absent
        res_exists_after = exists_tool.run({"pid": pid}, self.ctx, None)
        self.assertTrue(res_exists_after["ok"])
        self.assertFalse(res_exists_after["exists"])

        # 6. Test idempotent termination on already-terminated process
        res_term_idempotent = term_tool.run({"pid": pid}, self.ctx, None)
        self.assertTrue(res_term_idempotent["ok"])
        self.assertTrue(res_term_idempotent.get("already_terminated", False))

    def test_security_policy_denies_protected_system_processes(self):
        policy = SecurityPolicy()
        protected_list = ["csrss.exe", "lsass.exe", "smss.exe", "services.exe", "wininit.exe"]

        for proc_name in protected_list:
            eval_res = policy.evaluate("terminate_process", {"process_name": proc_name})
            self.assertEqual(
                eval_res.decision,
                PolicyDecision.DENY,
                f"Termination of protected process '{proc_name}' must be DENIED.",
            )
            self.assertEqual(eval_res.risk, ActionRisk.CRITICAL)
            self.assertTrue(eval_res.is_denied)


if __name__ == "__main__":
    unittest.main()
