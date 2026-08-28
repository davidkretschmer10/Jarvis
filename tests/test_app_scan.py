import json
import os
import tempfile
import unittest
from unittest.mock import patch

from core import agent
from core.services.application_resolver import reset_application_resolver
from utils.helpers import normalize_name


class AppScanTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = os.path.join(self.temp_dir.name, "apps_cache.json")
        self.pref_file = os.path.join(self.temp_dir.name, "user_preferences.json")

        with open(self.pref_file, "w", encoding="utf-8") as f:
            json.dump({}, f)

        self.patch_cache = patch("core.agent.APPS_CACHE_FILE", self.cache_file)
        self.patch_prefs = patch("core.agent.PREFERENCES_FILE", self.pref_file)
        self.patch_cache.start()
        self.patch_prefs.start()

        reset_application_resolver()
        agent.scanned_apps = {}

    def tearDown(self):
        self.patch_cache.stop()
        self.patch_prefs.stop()
        reset_application_resolver()
        self.temp_dir.cleanup()

    def test_normalize_epick_game_alias(self):
        self.assertEqual(normalize_name("epick game"), "epic games")

    def test_open_program_fuzzy_matches_epic_games_launcher(self):
        fake_apps = {"epic games launcher": r"C:\Apps\Epic Games Launcher.lnk"}
        with patch.dict(agent.scanned_apps, fake_apps, clear=True), \
             patch("core.agent.os.path.exists", return_value=True), \
             patch("core.services.application_resolver.os.path.exists", return_value=True), \
             patch("core.agent.scan_apps", return_value={}), \
             patch("core.agent.scan_registry_app_paths", return_value={}), \
             patch("core.services.application_resolver.ApplicationResolver.scan_registry_app_paths", return_value={}), \
             patch("core.agent.os.startfile") as startfile:
            result = agent.open_program("epick game")

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("error"), "CONFIRMATION_REQUIRED")
        self.assertEqual(result.get("pending_app_path"), r"C:\Apps\Epic Games Launcher.lnk")
        self.assertEqual(result.get("pending_app_name"), "epic games launcher")


if __name__ == "__main__":
    unittest.main()

