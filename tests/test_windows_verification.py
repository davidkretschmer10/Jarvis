# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.verification import (
    ApplicationVerifier,
    DirectoryVerifier,
    FileVerifier,
    PassThroughVerifier,
    ProcessVerifier,
    StepVerifierRegistry,
    UIInteractionVerifier,
    VerificationResult,
    VerificationStatus,
    WindowVerifier,
)


class TestWindowsVerification(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="jarvis_win_verif_")

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_copy_file_verification_success(self):
        src = os.path.join(self.tmp_dir, "v_src.txt")
        dst = os.path.join(self.tmp_dir, "v_dst.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("identical payload")
        shutil.copy2(src, dst)

        fv = FileVerifier()
        step = {"tool": "copy_file", "args": {"source": src, "destination": dst}}
        res = fv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.VERIFIED)
        self.assertTrue(res.is_verified())

    def test_copy_file_verification_failure_when_dst_missing(self):
        src = os.path.join(self.tmp_dir, "v_src2.txt")
        dst = os.path.join(self.tmp_dir, "v_missing.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("data")

        fv = FileVerifier()
        step = {"tool": "copy_file", "args": {"source": src, "destination": dst}}
        res = fv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.FAILED)
        self.assertTrue(res.is_failed())

    def test_move_file_verification_success(self):
        src = os.path.join(self.tmp_dir, "to_move.txt")
        dst = os.path.join(self.tmp_dir, "moved.txt")
        with open(dst, "w", encoding="utf-8") as f:
            f.write("moved data")
        # Ensure src does not exist

        fv = FileVerifier()
        step = {"tool": "move_file", "args": {"source": src, "destination": dst}}
        res = fv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.VERIFIED)

    def test_move_file_verification_fails_if_source_still_exists(self):
        src = os.path.join(self.tmp_dir, "still_here.txt")
        dst = os.path.join(self.tmp_dir, "moved_dst.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("source")
        with open(dst, "w", encoding="utf-8") as f:
            f.write("dest")

        fv = FileVerifier()
        step = {"tool": "move_file", "args": {"source": src, "destination": dst}}
        res = fv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.FAILED)

    @patch("core.verification._get_running_processes_windows", return_value=["notepad.exe", "python.exe"])
    def test_process_verifier_query_exists(self, mock_procs):
        pv = ProcessVerifier()
        step = {"tool": "process_exists", "args": {"process_name": "notepad"}}
        res = pv.verify(step, {"ok": True, "exists": True})
        self.assertEqual(res.status, VerificationStatus.VERIFIED)

    @patch("core.verification._get_running_processes_windows", return_value=["explorer.exe"])
    def test_process_verifier_terminate_success_when_absent(self, mock_procs):
        pv = ProcessVerifier()
        step = {"tool": "terminate_process", "args": {"process_name": "notepad.exe"}}
        res = pv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.VERIFIED)

    @patch("core.verification._get_running_processes_windows", return_value=["notepad.exe"])
    def test_process_verifier_terminate_fails_when_still_running(self, mock_procs):
        pv = ProcessVerifier()
        step = {"tool": "terminate_process", "args": {"process_name": "notepad.exe"}}
        res = pv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.FAILED)

    @patch("core.verification._get_visible_window_titles_windows", return_value=["Notepad - Untitled", "Command Prompt"])
    def test_window_verifier_exists(self, mock_windows):
        wv = WindowVerifier()
        step = {"tool": "window_exists", "args": {"title": "Notepad"}}
        res = wv.verify(step, {"ok": True, "exists": True})
        self.assertEqual(res.status, VerificationStatus.VERIFIED)

    @patch("core.verification._get_visible_window_titles_windows", return_value=["Command Prompt"])
    def test_window_verifier_close_success(self, mock_windows):
        wv = WindowVerifier()
        step = {"tool": "close_window", "args": {"title": "Notepad"}}
        res = wv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.VERIFIED)

    @patch("core.verification._get_visible_window_titles_windows", return_value=["Notepad - Untitled"])
    def test_window_verifier_close_fails_when_still_visible(self, mock_windows):
        wv = WindowVerifier()
        step = {"tool": "close_window", "args": {"title": "Notepad"}}
        res = wv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.FAILED)

    def test_window_verifier_generic_close_without_title_is_unknown(self):
        wv = WindowVerifier()
        step = {"tool": "close_window", "args": {}}
        res = wv.verify(step, {"ok": True})
        self.assertEqual(res.status, VerificationStatus.UNKNOWN)
        self.assertFalse(res.is_verified())

    def test_step_verifier_registry_routes_to_all_verifiers(self):
        reg = StepVerifierRegistry()
        verifier_types = [type(v) for v in reg.verifiers]
        self.assertIn(ProcessVerifier, verifier_types)
        self.assertIn(WindowVerifier, verifier_types)
        self.assertIn(FileVerifier, verifier_types)
        self.assertIn(DirectoryVerifier, verifier_types)
        self.assertIn(ApplicationVerifier, verifier_types)
        self.assertIn(PassThroughVerifier, verifier_types)
        self.assertIn(UIInteractionVerifier, verifier_types)


if __name__ == "__main__":
    unittest.main()
