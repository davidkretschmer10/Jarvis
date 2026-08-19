# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.services.application_resolver import (
    ApplicationResolver,
    get_application_resolver,
)


class TestApplicationResolver(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = os.path.join(self.temp_dir.name, "apps_cache.json")
        self.pref_file = os.path.join(self.temp_dir.name, "user_preferences.json")
        self.resolver = ApplicationResolver(
            cache_file=self.cache_file,
            preferences_file=self.pref_file,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_dummy_file(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("")

    # 1. Exact Match
    def test_exact_match(self):
        chrome_path = os.path.join(self.temp_dir.name, "chrome.exe")
        self.create_dummy_file(chrome_path)

        mock_cache = {"chrome": chrome_path}
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f)

        res = self.resolver.resolve("chrome")
        self.assertTrue(res.found)
        self.assertEqual(res.path, chrome_path)
        self.assertEqual(res.score, 100)
        self.assertGreaterEqual(res.confidence, 0.98)

    # 2. Alias Match
    def test_alias_match(self):
        chrome_path = os.path.join(self.temp_dir.name, "chrome.exe")
        epic_path = os.path.join(self.temp_dir.name, "EpicGamesLauncher.exe")
        code_path = os.path.join(self.temp_dir.name, "Code.exe")
        calc_path = os.path.join(self.temp_dir.name, "calc.exe")

        self.create_dummy_file(chrome_path)
        self.create_dummy_file(epic_path)
        self.create_dummy_file(code_path)
        self.create_dummy_file(calc_path)

        mock_cache = {
            "google chrome": chrome_path,
            "epic games launcher": epic_path,
            "visual studio code": code_path,
            "calculator": calc_path,
        }
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f)

        # "chrom" -> google chrome
        res_chrom = self.resolver.resolve("chrom")
        self.assertTrue(res_chrom.found)
        self.assertEqual(res_chrom.path, chrome_path)
        self.assertEqual(res_chrom.name, "google chrome")

        # "epic" -> epic games launcher
        res_epic = self.resolver.resolve("epic")
        self.assertTrue(res_epic.found)
        self.assertEqual(res_epic.path, epic_path)
        self.assertEqual(res_epic.name, "epic games launcher")

        # "vscode" -> visual studio code
        res_vscode = self.resolver.resolve("vscode")
        self.assertTrue(res_vscode.found)
        self.assertEqual(res_vscode.path, code_path)

        # "kalkulačka" -> calculator
        res_calc = self.resolver.resolve("kalkulačka")
        self.assertTrue(res_calc.found)

    # 3. Fuzzy Match
    def test_fuzzy_match(self):
        unity_path = os.path.join(self.temp_dir.name, "unity_hub.exe")
        self.create_dummy_file(unity_path)

        mock_cache = {"unity hub": unity_path}
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f)

        res = self.resolver.resolve("unity hb")
        self.assertTrue(res.found)
        self.assertTrue(res.confirmation_required)
        self.assertEqual(res.score, 60)
        self.assertIn("se skóre 60%", res.confirmation_message or "")

    # 4. User Preference
    def test_user_preference(self):
        std_chrome = os.path.join(self.temp_dir.name, "std", "chrome.exe")
        custom_chrome = os.path.join(self.temp_dir.name, "custom", "chrome.exe")
        self.create_dummy_file(std_chrome)
        self.create_dummy_file(custom_chrome)

        # Standard cache contains std_chrome
        mock_cache = {"chrome": std_chrome}
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f)

        # Save preference pointing to custom_chrome
        self.resolver.save_preference("chrome", custom_chrome)

        res = self.resolver.resolve("chrome")
        self.assertTrue(res.found)
        self.assertTrue(res.is_preference)
        self.assertEqual(res.path, custom_chrome)
        self.assertEqual(res.score, 100)

    # 5. Application Cache
    def test_application_cache_rebuild(self):
        blender_path = os.path.join(self.temp_dir.name, "blender.exe")
        self.create_dummy_file(blender_path)

        with patch.object(self.resolver, "scan_all", return_value={"blender": blender_path}), \
             patch.object(self.resolver, "scan_registry_app_paths", return_value={}):
            rebuilt = self.resolver.rebuild_cache()
            self.assertIn("blender", rebuilt)
            self.assertEqual(rebuilt["blender"], blender_path)
            self.assertTrue(os.path.exists(self.cache_file))

    # 6. Start Menu Fallback
    def test_start_menu_fallback(self):
        notepad_path = os.path.join(self.temp_dir.name, "notepad.exe")
        self.create_dummy_file(notepad_path)

        # Empty cache
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump({}, f)

        with patch.object(self.resolver, "scan_start_menu", return_value={"notepad": notepad_path}):
            res = self.resolver.resolve("notepad")
            self.assertTrue(res.found)
            self.assertEqual(res.path, notepad_path)

    # 7. Registry Fallback
    def test_registry_fallback(self):
        reg_app_path = os.path.join(self.temp_dir.name, "regapp.exe")
        self.create_dummy_file(reg_app_path)

        # Empty cache & start menu
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump({}, f)

        with patch.object(self.resolver, "scan_start_menu", return_value={}), \
             patch.object(self.resolver, "scan_registry_app_paths", return_value={"regapp": reg_app_path}):
            res = self.resolver.resolve("regapp")
            self.assertTrue(res.found)
            self.assertEqual(res.path, reg_app_path)

    # 8. Program Files Fallback
    def test_program_files_fallback(self):
        pf_app_path = os.path.join(self.temp_dir.name, "pf_tool.exe")
        self.create_dummy_file(pf_app_path)

        with patch.object(self.resolver, "scan_all", return_value={"pf tool": pf_app_path}), \
             patch.object(self.resolver, "scan_registry_app_paths", return_value={}):
            # Rebuilding loads from scan_all
            apps = self.resolver.rebuild_cache()
            self.assertIn("pf tool", apps)
            res = self.resolver.resolve("pf tool")
            self.assertTrue(res.found)
            self.assertEqual(res.path, pf_app_path)

    # 9. .lnk Shortcut Resolution
    def test_lnk_shortcut_resolution(self):
        target_exe = os.path.join(self.temp_dir.name, "target.exe")
        lnk_file = os.path.join(self.temp_dir.name, "app.lnk")
        self.create_dummy_file(target_exe)
        self.create_dummy_file(lnk_file)

        with patch.object(self.resolver, "resolve_shortcut", return_value=target_exe), \
             patch("os.startfile") as mock_startfile:
            res = self.resolver.launch_path(lnk_file, "test_app")
            self.assertTrue(res["ok"])
            self.assertEqual(res["path"], target_exe)

    # 10. Missing Application
    def test_missing_application(self):
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump({}, f)

        with patch.object(self.resolver, "scan_start_menu", return_value={}), \
             patch.object(self.resolver, "scan_registry_app_paths", return_value={}):
            res = self.resolver.resolve("non_existent_app_xyz")
            self.assertFalse(res.found)
            self.assertEqual(res.confidence, 0.0)

    # 11. Low-confidence candidates & Browser query
    def test_browser_query_without_preference(self):
        res = self.resolver.resolve("otevři prohlížeč")
        self.assertFalse(res.found)
        self.assertTrue(res.confirmation_required)
        self.assertLess(res.confidence, 0.70)
        self.assertIn("Chrome", res.candidate_names)

    def test_browser_query_with_preference(self):
        chrome_path = os.path.join(self.temp_dir.name, "chrome.exe")
        self.create_dummy_file(chrome_path)

        mock_cache = {"google chrome": chrome_path}
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f)

        self.resolver.save_preference("prohlizec", "chrome")

        res = self.resolver.resolve("prohlížeč")
        self.assertTrue(res.found)
        self.assertFalse(res.confirmation_required)
        self.assertEqual(res.name, "google chrome")
        self.assertGreaterEqual(res.confidence, 0.90)

    # 12. Multiple candidates confirmation
    def test_multiple_candidates_confirmation(self):
        app1_path = os.path.join(self.temp_dir.name, "app1", "appgame.exe")
        app2_path = os.path.join(self.temp_dir.name, "app2", "appgame.exe")
        self.create_dummy_file(app1_path)
        self.create_dummy_file(app2_path)

        mock_cache = {
            "appgame version 1": app1_path,
            "appgame version 2": app2_path,
        }
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(mock_cache, f)

        res = self.resolver.resolve("appgame")
        self.assertTrue(res.found)
        self.assertTrue(res.confirmation_required)
        self.assertEqual(len(res.pending_candidates), 2)
        self.assertIn("Nalezl jsem více kandidátů", res.confirmation_message or "")

    # 13. Confidence Scoring
    def test_confidence_scoring(self):
        self.assertGreaterEqual(self.resolver.score_to_confidence(100), 0.98)
        self.assertGreaterEqual(self.resolver.score_to_confidence(95), 0.97)
        self.assertGreaterEqual(self.resolver.score_to_confidence(90), 0.96)
        self.assertGreaterEqual(self.resolver.score_to_confidence(80), 0.95)
        self.assertGreaterEqual(self.resolver.score_to_confidence(70), 0.92)
        self.assertGreaterEqual(self.resolver.score_to_confidence(60), 0.90)

    # 14. Ignored App Filter
    def test_ignored_app_filter(self):
        self.assertTrue(self.resolver.is_ignored_app("epicwebhelper", "C:\\epicwebhelper.exe"))
        self.assertTrue(self.resolver.is_ignored_app("updater", "C:\\updater.exe"))
        self.assertTrue(self.resolver.is_ignored_app("crash reporter", "C:\\crashreporter.exe"))
        self.assertFalse(self.resolver.is_ignored_app("chrome", "C:\\chrome.exe"))
        self.assertFalse(self.resolver.is_ignored_app("blender", "C:\\blender.exe"))


if __name__ == "__main__":
    unittest.main()
