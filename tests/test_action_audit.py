"""Tests for Central Action Audit Logger and Secret Redaction."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.action_audit import ActionAuditLogger, ActionAuditRecord, redact_secrets


class TestActionAudit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.temp_dir.name) / "audit" / "test_action_audit.jsonl"
        self.logger = ActionAuditLogger(log_path=self.log_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # 26. audit log created
    def test_26_audit_log_file_created(self):
        self.logger.log(
            request_id="req_test_01",
            step_id=1,
            source="cli",
            tool="read_file",
            capability="READ_FILE",
            risk="SAFE",
            decision="ALLOW",
            execution_status="SUCCESS",
        )
        self.assertTrue(self.log_path.exists())
        self.assertGreater(self.log_path.stat().st_size, 0)

    # 27 & 28. audit log redacts secrets & does not contain plaintext password/token
    def test_27_28_secret_redaction_in_data_and_strings(self):
        sensitive_data = {
            "password": "SuperSecretPassword123!",
            "api_key": "sk-proj-9876543210fedcba",
            "access_token": "bearer_token_xyz",
            "nested": {
                "auth_header": "Bearer secret_jwt_token",
                "normal_field": "public_data",
            },
            "error_msg": "Failed to connect with token=secret_value_12345",
        }
        redacted = redact_secrets(sensitive_data)

        self.assertEqual(redacted["password"], "[REDACTED]")
        self.assertEqual(redacted["api_key"], "[REDACTED]")
        self.assertEqual(redacted["access_token"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["auth_header"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["normal_field"], "public_data")
        self.assertNotIn("secret_value_12345", redacted["error_msg"])
        self.assertIn("[REDACTED]", redacted["error_msg"])

        # Test log record serialization
        record = self.logger.log(
            request_id="req_secrets",
            step_id=1,
            source="gui",
            tool="login_tool",
            capability="PROCESS_START",
            risk="HIGH",
            decision="REQUIRE_CONFIRMATION",
            error="Auth failed for token=my_secret_token_abc",
        )
        with open(self.log_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("my_secret_token_abc", content)
        self.assertIn("[REDACTED]", content)

    # 29. audit record contains request_id
    def test_29_audit_record_contains_request_id(self):
        record = self.logger.log(
            request_id="unique_request_id_999",
            step_id=2,
            source="voice",
            tool="open_app",
            capability="LAUNCH_APPLICATION",
            risk="LOW",
            decision="ALLOW",
        )
        self.assertEqual(record.request_id, "unique_request_id_999")
        with open(self.log_path, "r", encoding="utf-8") as f:
            line = f.readline()
            data = json.loads(line)
        self.assertEqual(data["request_id"], "unique_request_id_999")

    # 30. audit record contains step_id
    def test_30_audit_record_contains_step_id(self):
        record = self.logger.log(
            request_id="req_step_check",
            step_id=5,
            source="http",
            tool="write_file",
            capability="CREATE_FILE",
            risk="MEDIUM",
            decision="ALLOW",
        )
        self.assertEqual(record.step_id, 5)
        with open(self.log_path, "r", encoding="utf-8") as f:
            data = json.loads(f.readline())
        self.assertEqual(data["step_id"], 5)

    # 31. verified action is recorded
    def test_31_verified_action_recorded(self):
        self.logger.log(
            request_id="req_verified",
            step_id=1,
            source="runtime",
            tool="create_file",
            capability="CREATE_FILE",
            risk="MEDIUM",
            decision="ALLOW",
            execution_status="SUCCESS",
            verification_status="VERIFIED",
        )
        with open(self.log_path, "r", encoding="utf-8") as f:
            data = json.loads(f.readline())
        self.assertEqual(data["execution_status"], "SUCCESS")
        self.assertEqual(data["verification_status"], "VERIFIED")

    # 32. failed action is recorded
    def test_32_failed_action_recorded(self):
        self.logger.log(
            request_id="req_failed",
            step_id=1,
            source="runtime",
            tool="delete_file",
            capability="DELETE_FILE",
            risk="HIGH",
            decision="REQUIRE_CONFIRMATION",
            execution_status="FAILED",
            error="File not found on disk",
        )
        with open(self.log_path, "r", encoding="utf-8") as f:
            data = json.loads(f.readline())
        self.assertEqual(data["execution_status"], "FAILED")
        self.assertEqual(data["error"], "File not found on disk")

    # 33. denied action is recorded
    def test_33_denied_action_recorded(self):
        self.logger.log(
            request_id="req_denied",
            step_id=1,
            source="runtime",
            tool="shell_command",
            capability="SHELL_COMMAND",
            risk="CRITICAL",
            decision="DENY",
            execution_status="DENIED",
            error="Command contains dangerous pattern: format",
        )
        with open(self.log_path, "r", encoding="utf-8") as f:
            data = json.loads(f.readline())
        self.assertEqual(data["decision"], "DENY")
        self.assertEqual(data["execution_status"], "DENIED")


if __name__ == "__main__":
    unittest.main()
