import unittest
from unittest.mock import patch, MagicMock
import os
import tempfile
import json
from core import agent
from core.agent import open_program, search_levels, normalize_name

class TestPhase2_7(unittest.TestCase):
    def setUp(self):
        # Setup temporary directories/paths for cache and preferences
        self.temp_dir = tempfile.TemporaryDirectory()
        self.apps_cache_path = os.path.join(self.temp_dir.name, "apps_cache.json")
        self.prefs_path = os.path.join(self.temp_dir.name, "user_preferences.json")
        
        self.patch_cache = patch("core.agent.APPS_CACHE_FILE", self.apps_cache_path)
        self.patch_prefs = patch("core.agent.PREFERENCES_FILE", self.prefs_path)
        
        self.patch_cache.start()
        self.patch_prefs.start()
        
        # Reset scanned_apps to empty
        agent.scanned_apps = {}

    def tearDown(self):
        self.patch_cache.stop()
        self.patch_prefs.stop()
        self.temp_dir.cleanup()

    def create_dummy_file(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("")

    @patch("core.agent.os.startfile")
    @patch("core.agent.scan_apps", return_value={})
    @patch("core.agent.scan_registry_app_paths", return_value={})
    def test_chrome_vs_cpp_collision(self, mock_reg, mock_scan, mock_startfile):
        chrome_path = os.path.join(self.temp_dir.name, "chrome.exe")
        cpp_path = os.path.join(self.temp_dir.name, "c++.exe")
        updater_path = os.path.join(self.temp_dir.name, "updater.exe")
        
        self.create_dummy_file(chrome_path)
        self.create_dummy_file(cpp_path)
        self.create_dummy_file(updater_path)

        mock_cache = {
            "c": cpp_path,
            "chrome": chrome_path,
            "chromium updater": updater_path
        }
        with open(self.apps_cache_path, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f, ensure_ascii=False)

        # "Otevři Chrome" or "Chrome" should match chrome.exe and never c++.exe or chromium updater
        res = open_program("chrome")
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("path"), chrome_path)
        mock_startfile.assert_called_with(chrome_path)

    @patch("core.agent.os.startfile")
    @patch("core.agent.scan_apps", return_value={})
    @patch("core.agent.scan_registry_app_paths", return_value={})
    def test_open_blender_and_steam(self, mock_reg, mock_scan, mock_startfile):
        blender_path = os.path.join(self.temp_dir.name, "blender.exe")
        steam_path = os.path.join(self.temp_dir.name, "steam.exe")
        
        self.create_dummy_file(blender_path)
        self.create_dummy_file(steam_path)

        mock_cache = {
            "blender": blender_path,
            "steam": steam_path
        }
        with open(self.apps_cache_path, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f, ensure_ascii=False)

        # Blender
        res1 = open_program("Blender")
        self.assertTrue(res1.get("ok"))
        self.assertEqual(res1.get("path"), blender_path)

        # Steam
        res2 = open_program("Steam")
        self.assertTrue(res2.get("ok"))
        self.assertEqual(res2.get("path"), steam_path)

    @patch("core.agent.os.startfile")
    @patch("core.agent.scan_apps", return_value={})
    @patch("core.agent.scan_registry_app_paths", return_value={})
    def test_multiple_candidates_confirmation(self, mock_reg, mock_scan, mock_startfile):
        epic1_path = os.path.join(self.temp_dir.name, "Epic1", "epicgames.exe")
        epic2_path = os.path.join(self.temp_dir.name, "Epic2", "epicgames.exe")
        
        self.create_dummy_file(epic1_path)
        self.create_dummy_file(epic2_path)

        # Create cache with multiple candidates that score highly (e.g. >= 85)
        mock_cache = {
            "epic games launcher 1": epic1_path,
            "epic games launcher 2": epic2_path
        }
        with open(self.apps_cache_path, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f, ensure_ascii=False)

        # "epicgames" will exact-match the executable names "epicgames.exe" in both paths (100 pts each)
        res = open_program("epicgames")
        self.assertIsInstance(res, dict)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error"), "CONFIRMATION_REQUIRED")
        self.assertIn("Nalezl jsem více kandidátů", res.get("message", ""))
        self.assertEqual(len(res.get("pending_candidates", [])), 2)

    @patch("core.agent.os.startfile")
    @patch("core.agent.scan_apps", return_value={})
    @patch("core.agent.scan_registry_app_paths", return_value={})
    def test_low_confidence_confirmation(self, mock_reg, mock_scan, mock_startfile):
        unity_path = os.path.join(self.temp_dir.name, "unity_hub.exe")
        self.create_dummy_file(unity_path)

        # Create cache with a single app that matches with low confidence (e.g. fuzzy < 85%)
        mock_cache = {
            "unity hub": unity_path
        }
        with open(self.apps_cache_path, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f, ensure_ascii=False)

        # "unity hb" fuzzy matches "unity hub" with ratio/overlap >= 0.75, yielding score 60
        res = open_program("unity hb")
        self.assertIsInstance(res, dict)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("error"), "CONFIRMATION_REQUIRED")
        self.assertIn("se skóre 60%", res.get("message", ""))

    @patch("core.agent.os.startfile")
    @patch("core.agent.scan_apps", return_value={})
    @patch("core.agent.scan_registry_app_paths", return_value={})
    def test_user_app_learning(self, mock_reg, mock_scan, mock_startfile):
        custom_chrome = os.path.join(self.temp_dir.name, "Custom", "chrome.exe")
        self.create_dummy_file(custom_chrome)

        # Learn preference manually
        agent.learn_app_preference("chrome", custom_chrome)
        
        # Even if cache contains standard chrome, user preference MUST take precedence
        res = open_program("chrome")
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("path"), custom_chrome)
        mock_startfile.assert_called_with(custom_chrome)

if __name__ == "__main__":
    unittest.main()
