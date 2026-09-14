# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from core.action_audit import ActionAuditLogger
from core.security_policy import ActionRisk, PolicyDecision, SecurityPolicy, ToolCapability


class TestVisionSecurity(unittest.TestCase):
    def setUp(self):
        self.policy = SecurityPolicy()

    def test_classify_click_risk_neutral_targets(self):
        self.assertEqual(SecurityPolicy.classify_click_risk("Nastavení"), ActionRisk.LOW)
        self.assertEqual(SecurityPolicy.classify_click_risk("Profil"), ActionRisk.LOW)
        self.assertEqual(SecurityPolicy.classify_click_risk("Zobrazit více"), ActionRisk.LOW)
        self.assertEqual(SecurityPolicy.classify_click_risk("Nápověda"), ActionRisk.LOW)

    def test_classify_click_risk_destructive_targets(self):
        self.assertEqual(SecurityPolicy.classify_click_risk("Smazat vše"), ActionRisk.HIGH)
        self.assertEqual(SecurityPolicy.classify_click_risk("Delete account"), ActionRisk.HIGH)
        self.assertEqual(SecurityPolicy.classify_click_risk("Odstranit soubor"), ActionRisk.HIGH)
        self.assertEqual(SecurityPolicy.classify_click_risk("Zaplatit objednávku"), ActionRisk.HIGH)
        self.assertEqual(SecurityPolicy.classify_click_risk("Purchase license"), ActionRisk.HIGH)
        self.assertEqual(SecurityPolicy.classify_click_risk("Shutdown system"), ActionRisk.HIGH)
        self.assertEqual(SecurityPolicy.classify_click_risk("Odeslat formulář"), ActionRisk.HIGH)

    def test_evaluate_destructive_click_requires_confirmation(self):
        tool_input = {"target": "Smazat databázi"}
        res = self.policy.evaluate("smart_click", tool_input)
        self.assertEqual(res.decision, PolicyDecision.REQUIRE_CONFIRMATION)
        self.assertEqual(res.risk, ActionRisk.HIGH)

    def test_evaluate_neutral_click_allowed(self):
        tool_input = {"target": "Nastavení profilu"}
        res = self.policy.evaluate("smart_click", tool_input)
        self.assertEqual(res.decision, PolicyDecision.ALLOW)

    def test_action_audit_logging_with_vision_metadata_and_redaction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test_audit.jsonl"
            logger = ActionAuditLogger(log_path=log_path)

            rec = logger.log(
                request_id="req_test_1",
                step_id=1,
                source="gui",
                tool="smart_click",
                capability="UI_CLICK",
                risk="HIGH",
                decision="REQUIRE_CONFIRMATION",
                resource="Tlačítko token=secret_password_123",
                target_bbox=[100, 200, 80, 30],
                confidence=0.96,
                resolver_source="ocr",
            )

            d = rec.to_dict()
            self.assertEqual(d["tool"], "smart_click")
            self.assertEqual(d["target_bbox"], [100, 200, 80, 30])
            self.assertEqual(d["confidence"], 0.96)
            self.assertEqual(d["resolver_source"], "ocr")
            # Verify sensitive secret redaction
            self.assertNotIn("secret_password_123", d["resource"])
            self.assertIn("[REDACTED]", d["resource"])


if __name__ == "__main__":
    unittest.main()
