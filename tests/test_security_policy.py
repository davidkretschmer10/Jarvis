"""Tests for Central SecurityPolicy Engine, ActionRisk, and ResourceScope."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.security_policy import (
    ActionRisk,
    PolicyDecision,
    PolicyEvaluationResult,
    ResourceScope,
    SecurityPolicy,
    ToolCapability,
    classify_path_scope,
)


class TestSecurityPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = SecurityPolicy()

    # 1. SAFE action -> ALLOW
    def test_01_safe_action_allowed(self):
        res = self.policy.evaluate("calculate", {"expression": "2+2"})
        self.assertEqual(res.decision, PolicyDecision.ALLOW)
        self.assertEqual(res.risk, ActionRisk.SAFE)
        self.assertTrue(res.is_allowed)

    # 2. LOW action -> ALLOW
    def test_02_low_action_allowed(self):
        res = self.policy.evaluate("open_app", {"name": "notepad"})
        self.assertEqual(res.decision, PolicyDecision.ALLOW)
        self.assertEqual(res.risk, ActionRisk.LOW)
        self.assertTrue(res.is_allowed)

    # 3. HIGH action -> REQUIRE_CONFIRMATION
    def test_03_high_action_requires_confirmation(self):
        res = self.policy.evaluate("close_app", {"name": "chrome"})
        self.assertEqual(res.decision, PolicyDecision.REQUIRE_CONFIRMATION)
        self.assertEqual(res.risk, ActionRisk.HIGH)
        self.assertTrue(res.requires_confirmation)

    # 4. CRITICAL action -> DENY
    def test_04_critical_action_denied(self):
        # Shell command with dangerous format pattern
        res = self.policy.evaluate(
            "execute_code",
            {"command": "format C: /fs:NTFS"},
            tool_meta={"capability": ToolCapability.SHELL_COMMAND, "risk": ActionRisk.CRITICAL},
        )
        self.assertEqual(res.decision, PolicyDecision.DENY)
        self.assertEqual(res.risk, ActionRisk.CRITICAL)
        self.assertTrue(res.is_denied)

    # 5. protected system path -> DENY / confirmation podle policy
    def test_05_protected_system_path_denied_for_modify(self):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        target_path = os.path.join(windir, "System32", "critical_system_file.dll")
        res = self.policy.evaluate(
            "write_file",
            {"filepath": target_path, "content": "corrupt"},
            tool_meta={"capability": ToolCapability.MODIFY_FILE, "risk": ActionRisk.HIGH},
        )
        self.assertEqual(res.decision, PolicyDecision.DENY)
        self.assertEqual(res.risk, ActionRisk.CRITICAL)
        self.assertEqual(res.resource_scope, ResourceScope.SYSTEM_PROTECTED)

    def test_05b_protected_system_path_read_requires_confirmation(self):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        target_path = os.path.join(windir, "win.ini")
        res = self.policy.evaluate(
            "read_file",
            {"filepath": target_path},
            tool_meta={"capability": ToolCapability.READ_FILE, "risk": ActionRisk.SAFE},
        )
        self.assertEqual(res.decision, PolicyDecision.REQUIRE_CONFIRMATION)
        self.assertEqual(res.resource_scope, ResourceScope.SYSTEM_PROTECTED)

    # 6. unknown path -> bezpečný fallback
    def test_06_unknown_path_safe_fallback(self):
        unknown_path = r"Z:\NonExistentDrive\unknown_folder\file.txt"
        scope = classify_path_scope(unknown_path)
        self.assertIn(scope, (ResourceScope.UNKNOWN, ResourceScope.SYSTEM_PROTECTED))

        res = self.policy.evaluate(
            "write_file",
            {"filepath": unknown_path, "content": "data"},
            tool_meta={"capability": ToolCapability.CREATE_FILE, "risk": ActionRisk.MEDIUM},
        )
        # Outside user workspace/known scopes -> requires confirmation
        self.assertEqual(res.decision, PolicyDecision.REQUIRE_CONFIRMATION)

    # 15. unknown tool -> denied
    def test_15_unknown_tool_denied(self):
        res = self.policy.evaluate("totally_unknown_custom_tool", {"arg": "val"})
        self.assertEqual(res.decision, PolicyDecision.DENY)
        self.assertEqual(res.risk, ActionRisk.CRITICAL)
        self.assertTrue(res.is_denied)

    # 17. missing security metadata -> denied / fallback to high
    def test_17_missing_tool_name_denied(self):
        res = self.policy.evaluate("", {})
        self.assertEqual(res.decision, PolicyDecision.DENY)
        self.assertEqual(res.risk, ActionRisk.CRITICAL)

    # Safe Real Windows Tests
    def test_real_windows_temp_file_scope(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            temp_path = tf.name
        try:
            scope = classify_path_scope(temp_path)
            self.assertEqual(scope, ResourceScope.TEMPORARY)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_real_windows_workspace_scope(self):
        cwd_path = str(Path.cwd().resolve() / "test_file.txt")
        scope = classify_path_scope(cwd_path)
        self.assertEqual(scope, ResourceScope.USER_WORKSPACE)

    def test_risk_level_ordering(self):
        self.assertLess(ActionRisk.SAFE, ActionRisk.LOW)
        self.assertLess(ActionRisk.LOW, ActionRisk.MEDIUM)
        self.assertLess(ActionRisk.MEDIUM, ActionRisk.HIGH)
        self.assertLess(ActionRisk.HIGH, ActionRisk.CRITICAL)


if __name__ == "__main__":
    unittest.main()
