import unittest
from unittest.mock import patch

from core import agent
from utils.helpers import normalize_name


class AppScanTests(unittest.TestCase):
    def test_normalize_epick_game_alias(self):
        self.assertEqual(normalize_name("epick game"), "epic games")

    def test_open_program_fuzzy_matches_epic_games_launcher(self):
        fake_apps = {"epic games launcher": r"C:\Apps\Epic Games Launcher.lnk"}
        with patch.dict(agent.scanned_apps, fake_apps, clear=True), \
             patch("core.agent.os.path.exists", return_value=True), \
             patch("core.agent.scan_apps", return_value={}), \
             patch("core.agent.scan_registry_app_paths", return_value={}), \
             patch("core.agent.os.startfile") as startfile:
            result = agent.open_program("epick game")

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("error"), "CONFIRMATION_REQUIRED")
        self.assertEqual(result.get("pending_app_path"), r"C:\Apps\Epic Games Launcher.lnk")
        self.assertEqual(result.get("pending_app_name"), "epic games launcher")


if __name__ == "__main__":
    unittest.main()
