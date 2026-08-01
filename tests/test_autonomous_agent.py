import unittest
from unittest.mock import patch

from core.autonomous_agent import AutonomousAgent


class AutonomousAgentTests(unittest.TestCase):
    def test_parse_plan_accepts_json_inside_text(self):
        agent = AutonomousAgent()
        steps = agent.parse_plan('plan:\n[{"action":"open","value":"chrome"}]')

        self.assertEqual(steps, [("open", "chrome")])

    def test_evaluate_rejects_error_result(self):
        agent = AutonomousAgent()
        result = agent.evaluate("zapni app", ['open: app -> {"ok": false, "result": "ERROR"}'])

        self.assertEqual(result, "NO")

    def test_run_returns_failure_when_plan_is_empty(self):
        agent = AutonomousAgent()
        with patch.object(agent, "deterministic_plan", return_value=[]), patch.object(agent, "plan", return_value="not json"):
            result = agent.run("udelej neco nejasneho")

        self.assertFalse(result["ok"])
        self.assertIn("plan", result)

    def test_deterministic_open_plan_handles_epic_typo(self):
        agent = AutonomousAgent()
        steps = agent.deterministic_plan("zapni mi epick game")

        self.assertEqual(steps, [("open", "epic games")])

    def test_run_does_not_call_llm_for_open_app(self):
        agent = AutonomousAgent()
        with patch.object(agent, "plan") as plan, patch.object(agent, "execute", return_value='{"ok":true}'):
            result = agent.run("zapni mi epick game")

        plan.assert_not_called()
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
