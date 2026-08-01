# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import argparse
import sys
import os

from tests.stress.launch_stress import run_launch_stress, is_pid_running, kill_pid
from tests.stress.stress_runner import parse_args

class TestPhase3_1(unittest.TestCase):
    
    def test_argparse_launch_profile(self):
        # Test that stress_runner parses the launch profile and verify-launch argument correctly
        test_args = ["stress_runner.py", "--profile", "launch", "--verify-launch"]
        with patch.object(sys, "argv", test_args):
            parsed = parse_args()
            self.assertEqual(parsed.profile, "launch")
            self.assertTrue(parsed.verify_launch)

    def test_run_launch_stress_dry_run(self):
        # Run launch stress test in dry_run mode (simulation)
        mock_cache = {
            "google chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "epic games launcher": "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\EpicGamesLauncher.exe",
            "blender": "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe",
            "visual studio code": "C:\\Users\\User\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
            "calculator": "C:\\Windows\\System32\\calc.exe",
            "notepad": "C:\\Windows\\notepad.exe"
        }
        
        # Classify routing level is real or mocked. To avoid real app matching registry scans, we can patch cache loading.
        with patch("core.intents.fast_command_router.load_apps_cache", return_value=mock_cache):
            stats = run_launch_stress(num_iterations=1, verify_launch=False, dry_run=True, mock_cache_data=mock_cache)
            
            self.assertGreater(stats["total_runs"], 0)
            self.assertEqual(stats["failed_runs"], 0)
            self.assertEqual(stats["success_runs"], stats["total_runs"])
            self.assertEqual(len(stats["elapsed_times"]), stats["total_runs"])

    @patch("tests.stress.launch_stress.open_program")
    @patch("tests.stress.launch_stress.get_all_processes_info")
    @patch("tests.stress.launch_stress.kill_pid")
    def test_run_launch_stress_real_run_mocked(self, mock_kill, mock_get_procs, mock_open):
        # Verify launch flow when real run is triggered but mocked
        mock_cache = {
            "google chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "epic games launcher": "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\EpicGamesLauncher.exe",
            "blender": "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe",
            "visual studio code": "C:\\Users\\User\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
            "calculator": "C:\\Windows\\System32\\calc.exe",
            "notepad": "C:\\Windows\\notepad.exe"
        }
        
        # open_program returns success and a dummy pid 9999
        mock_open.return_value = {"ok": True, "result": "SUCCESS", "pid": 9999}
        mock_get_procs.return_value = [
            {"name": "chrome.exe", "pid": 9999, "ppid": 0},
            {"name": "EpicGamesLauncher.exe", "pid": 10001, "ppid": 9999},
            {"name": "blender.exe", "pid": 10002, "ppid": 9999},
            {"name": "Code.exe", "pid": 10003, "ppid": 9999},
            {"name": "calc.exe", "pid": 10004, "ppid": 9999},
            {"name": "notepad.exe", "pid": 10005, "ppid": 9999}
        ]
        
        with patch("core.intents.fast_command_router.load_apps_cache", return_value=mock_cache), \
             patch("time.sleep"):  # skip the 2s sleep to keep tests fast
            
            stats = run_launch_stress(num_iterations=1, verify_launch=True, dry_run=False, mock_cache_data=mock_cache)
            
            self.assertGreater(stats["total_runs"], 0)
            self.assertEqual(stats["failed_runs"], 0)
            self.assertEqual(stats["success_runs"], stats["total_runs"])
            self.assertEqual(mock_open.call_count, stats["total_runs"])
            self.assertEqual(mock_get_procs.call_count, stats["total_runs"])
            self.assertGreaterEqual(mock_kill.call_count, stats["total_runs"])
            mock_get_procs.assert_called()
            mock_kill.assert_called_with(9999)

    @patch("subprocess.run")
    def test_is_pid_running(self, mock_run):
        # Simulate active process
        mock_result = MagicMock()
        mock_result.stdout = '"python.exe","1234","Console","1","56,120 K"'
        mock_run.return_value = mock_result
        
        self.assertTrue(is_pid_running(1234))
        
        # Simulate missing process
        mock_result.stdout = "No tasks are running which match the specified criteria."
        self.assertFalse(is_pid_running(5678))

    @patch("subprocess.run")
    def test_kill_pid(self, mock_run):
        kill_pid(9999)
        mock_run.assert_called_once()
        self.assertIn("taskkill", mock_run.call_args[0][0])
        self.assertIn("9999", mock_run.call_args[0][0])

    def test_ignored_apps_filter(self):
        from core.intents.fast_command_router import is_ignored_app
        self.assertTrue(is_ignored_app("epicwebhelper", "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\epicwebhelper.exe"))
        self.assertTrue(is_ignored_app("updater", "C:\\Windows\\updater.exe"))
        self.assertTrue(is_ignored_app("crash reporter", "C:\\Program Files\\crashreporter.exe"))
        self.assertTrue(is_ignored_app("helper", "C:\\Program Files\\webhelper.exe"))
        self.assertFalse(is_ignored_app("blender", "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe"))
        self.assertFalse(is_ignored_app("epic games launcher", "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\EpicGamesLauncher.exe"))

    def test_calculator_forced_routing(self):
        from core.intents.fast_command_router import classify_routing_level
        # Even with empty apps cache, these must resolve as FAST_COMMAND with calculator target
        with patch("core.intents.fast_command_router.load_apps_cache", return_value={}):
            for cmd in ["otevři kalkulačku", "otevři kalkulačku prosím", "zapni kalkulačku", "calc", "calculator"]:
                res = classify_routing_level(cmd)
                self.assertEqual(res["route"], "FAST_COMMAND")
                self.assertEqual(res["step"]["tool"], "open_app")
                self.assertEqual(res["step"]["input"]["name"], "calculator")

    def test_epic_games_launcher_preference(self):
        from core.agent import search_levels
        # If cache has both epic games launcher and epicwebhelper (though scanner filters it), epicwebhelper must be ignored,
        # and "epic" query should resolve to epic games launcher.
        mock_cache = {
            "epic games launcher": "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\EpicGamesLauncher.exe",
            "epicwebhelper": "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\epicwebhelper.exe"
        }
        with patch("core.agent.load_scanned_apps", return_value=mock_cache), \
             patch("core.agent.scan_registry_app_paths", return_value={}), \
             patch("core.agent.scan_apps", return_value={}):
            candidates = search_levels("epic")
            self.assertTrue(len(candidates) > 0)
            self.assertEqual(candidates[0]["name"], "epic games launcher")

if __name__ == "__main__":
    unittest.main()
