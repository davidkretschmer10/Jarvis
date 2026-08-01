import unittest
from unittest.mock import patch

from core import agent


class AgentCommandExecutionTests(unittest.TestCase):
    def test_command_open_uses_mocked_program_launcher(self):
        with agent.app.test_client() as client, patch("core.agent.open_program", return_value="SUCCESS: Opened app") as open_program:
            response = client.post("/command", json={"action": "open", "value": "notepad"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        open_program.assert_called_once_with("notepad")

    def test_command_click_uses_mocked_click(self):
        payload = {"x": 10, "y": 20}
        with agent.app.test_client() as client, patch("core.agent.click", return_value="Kliknuto") as click:
            response = client.post("/command", json={"action": "click", "value": payload})

        self.assertTrue(response.get_json()["ok"])
        click.assert_called_once_with(payload)

    def test_command_rejects_unknown_action(self):
        with agent.app.test_client() as client:
            response = client.post("/command", json={"action": "missing"})

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
