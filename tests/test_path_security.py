# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.security_policy import ActionRisk, PolicyDecision, ResourceScope, SecurityPolicy, ToolCapability, classify_path_scope
from utils.path_utils import canonical_windows_path, is_protected_system_path, is_subpath_of


class TestPathSecurity(unittest.TestCase):
    def test_canonical_path_expands_env_vars(self):
        temp_env = os.environ.get("TEMP", "")
        if temp_env:
            resolved = canonical_windows_path(r"%TEMP%\test_file.txt")
            self.assertNotIn("%TEMP%", resolved)
            self.assertTrue(resolved.lower().startswith(temp_env.lower()) or "temp" in resolved.lower())

    def test_canonical_path_expands_tilde(self):
        user_home = str(Path.home())
        resolved = canonical_windows_path(r"~/my_document.txt")
        self.assertNotIn("~", resolved)
        self.assertTrue(resolved.lower().startswith(user_home.lower()))

    def test_canonical_path_resolves_workspace_relative(self):
        with tempfile.TemporaryDirectory() as ws:
            resolved = canonical_windows_path("sub/file.txt", workspace_root=ws)
            expected = os.path.abspath(os.path.join(ws, "sub", "file.txt"))
            self.assertEqual(resolved.lower(), expected.lower())

    def test_canonical_path_resolves_traversal(self):
        with tempfile.TemporaryDirectory() as ws:
            resolved = canonical_windows_path(os.path.join(ws, "a", "..", "b.txt"))
            expected = os.path.abspath(os.path.join(ws, "b.txt"))
            self.assertEqual(resolved.lower(), expected.lower())

    def test_is_protected_system_path(self):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        self.assertTrue(is_protected_system_path(windir))
        self.assertTrue(is_protected_system_path(os.path.join(windir, "System32", "cmd.exe")))
        self.assertTrue(is_protected_system_path(r"C:\\"))

    def test_traversal_into_protected_path_detected(self):
        user_dir = os.environ.get("USERPROFILE", r"C:\Users\Default")
        traversal = os.path.join(user_dir, r"..\..\Windows\System32\cmd.exe")
        self.assertTrue(is_protected_system_path(traversal))
        scope = classify_path_scope(traversal)
        self.assertEqual(scope, ResourceScope.SYSTEM_PROTECTED)

    def test_temp_path_classified_as_temporary(self):
        with tempfile.NamedTemporaryFile() as tf:
            scope = classify_path_scope(tf.name)
            self.assertEqual(scope, ResourceScope.TEMPORARY)

    def test_security_policy_denies_destructive_action_on_protected_path(self):
        policy = SecurityPolicy()
        windir = os.environ.get("WINDIR", r"C:\Windows")
        target = os.path.join(windir, "System32", "critical.dll")

        # Delete file in System32 must be strictly DENIED
        eval_del = policy.evaluate("delete_file", {"path": target})
        self.assertEqual(eval_del.decision, PolicyDecision.DENY)
        self.assertEqual(eval_del.risk, ActionRisk.CRITICAL)
        self.assertTrue(eval_del.is_denied)

        # Write file in Windows must be strictly DENIED
        eval_write = policy.evaluate("write_file", {"path": target, "content": "bad"})
        self.assertEqual(eval_write.decision, PolicyDecision.DENY)
        self.assertEqual(eval_write.risk, ActionRisk.CRITICAL)
        self.assertTrue(eval_del.is_denied)

    def test_security_policy_denies_traversal_attack(self):
        policy = SecurityPolicy()
        user_dir = os.environ.get("USERPROFILE", r"C:\Users\Default")
        traversal = os.path.join(user_dir, r"..\..\Windows\System32\drivers\etc\hosts")

        eval_res = policy.evaluate("delete_file", {"path": traversal})
        self.assertEqual(eval_res.decision, PolicyDecision.DENY)
        self.assertEqual(eval_res.risk, ActionRisk.CRITICAL)
        self.assertTrue(eval_res.is_denied)


if __name__ == "__main__":
    unittest.main()
