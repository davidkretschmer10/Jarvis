# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import os
import json
import subprocess

from core.intents.fast_command_router import (
    classify_routing_level,
    get_fast_command_step,
    save_user_preference,
    load_user_preferences,
    increment_router_stat,
    get_appdata_path
)

class RouterTests(unittest.TestCase):
    def setUp(self):
        # Clear preferences and stats before each test to ensure isolation
        self.pref_file = get_appdata_path("user_preferences.json")
        self.stats_file = get_appdata_path("router_stats.json")
        
        if os.path.exists(self.pref_file):
            try:
                os.remove(self.pref_file)
            except Exception:
                pass
        if os.path.exists(self.stats_file):
            try:
                os.remove(self.stats_file)
            except Exception:
                pass

        # Mock apps cache so tests pass reliably on any machine
        self.mock_cache = {
            "google chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "epic games launcher": "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\EpicGamesLauncher.exe",
            "notepad": "C:\\Windows\\notepad.exe",
            "calculator": "C:\\Windows\\System32\\calc.exe",
            "blender": "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe",
            "steam": "C:\\Program Files (x86)\\Steam\\steam.exe",
            "visual studio code": "C:\\Users\\User\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
        }
        self.load_cache_patcher = patch("core.intents.fast_command_router.load_apps_cache", return_value=self.mock_cache)
        self.load_cache_patcher.start()

    def tearDown(self):
        self.load_cache_patcher.stop()
        
        # Clean up files
        if os.path.exists(self.pref_file):
            try:
                os.remove(self.pref_file)
            except Exception:
                pass
        if os.path.exists(self.stats_file):
            try:
                os.remove(self.stats_file)
            except Exception:
                pass

    def test_classify_routing_level(self):
        # Level 1: FAST_COMMAND
        self.assertEqual(classify_routing_level("Zapni Chrome")["route"], "FAST_COMMAND")
        self.assertEqual(classify_routing_level("Otevři kalkulačku")["route"], "FAST_COMMAND")
        self.assertEqual(classify_routing_level("Screenshot")["route"], "FAST_COMMAND")
        self.assertEqual(classify_routing_level("otevři seznam.cz")["route"], "FAST_COMMAND")
        
        # Level 2: MINI_PLANNER
        self.assertEqual(classify_routing_level("Otevři Chrome a vyhledej Nvidia")["route"], "MINI_PLANNER")
        self.assertEqual(classify_routing_level("Otevři Poznámkový blok a napiš Ahoj")["route"], "MINI_PLANNER")
        
        # Level 3: PLANNER_V2
        self.assertEqual(classify_routing_level("Vytvoř prezentaci o AI")["route"], "PLANNER_V2")
        self.assertEqual(classify_routing_level("Najdi informace o Nvidii a vytvoř report")["route"], "PLANNER_V2")
        self.assertEqual(classify_routing_level("Vytvoř model auta v Blenderu")["route"], "PLANNER_V2")
        self.assertEqual(classify_routing_level("Naprogramuj kalkulačku")["route"], "PLANNER_V2")

    def test_flexible_matching_hotfixes(self):
        # Test cases for Problem 1, 3 and 5:
        test_commands = [
            "zapni chrom",
            "zapni chrome",
            "otevři chrome",
            "zapni epic",
            "otevři epic games"
        ]
        
        for cmd in test_commands:
            res = classify_routing_level(cmd)
            self.assertEqual(res["route"], "FAST_COMMAND", f"Failed to classify '{cmd}' as FAST_COMMAND")
            self.assertGreaterEqual(res["confidence"], 0.90, f"Confidence for '{cmd}' too low: {res['confidence']}")
            self.assertIsNotNone(res["step"], f"Step was None for '{cmd}'")
            self.assertIn(res["step"]["tool"], ("open_app", "open"))
            
            # Match resolved targets
            target_name = res["step"]["input"]["name"]
            if "chrom" in cmd:
                self.assertEqual(target_name, "google chrome")
            elif "epic" in cmd:
                self.assertEqual(target_name, "epic games launcher")

    def test_confidence_and_preference_learning(self):
        # 1. "Otevři prohlížeč" without preference -> confidence should be < 0.70
        res1 = classify_routing_level("Otevři prohlížeč")
        self.assertEqual(res1["route"], "FAST_COMMAND")
        self.assertLess(res1["confidence"], 0.70)
        self.assertIsNotNone(res1["candidates"])
        self.assertIn("Chrome", res1["candidates"])

        # 2. Select Chrome and save preference
        save_user_preference("prohlizec", "chrome")
        
        # Verify preference is written to file
        prefs = load_user_preferences()
        self.assertEqual(prefs.get("prohlizec"), "chrome")

        # 3. Next run of "Otevři prohlížeč" -> confidence should be high (>= 0.90) and step populated with chrome
        res2 = classify_routing_level("Otevři prohlížeč")
        self.assertEqual(res2["route"], "FAST_COMMAND")
        self.assertGreaterEqual(res2["confidence"], 0.90)
        self.assertIsNone(res2["candidates"])
        self.assertIsNotNone(res2["step"])
        self.assertEqual(res2["step"]["tool"], "open_app")
        # In our setup, chrome preference resolves from mock cache to google chrome
        self.assertEqual(res2["step"]["input"]["name"], "google chrome")

    def test_url_and_search_fast_routing(self):
        # Weby (URL)
        res_seznam = classify_routing_level("otevři seznam.cz")
        self.assertEqual(res_seznam["route"], "FAST_COMMAND")
        self.assertEqual(res_seznam["step"]["tool"], "open_website")
        self.assertEqual(res_seznam["step"]["input"]["url"], "https://www.seznam.cz")

        # Search commands
        res_search = classify_routing_level("vyhledej nvidia")
        self.assertEqual(res_search["route"], "FAST_COMMAND")
        self.assertEqual(res_search["step"]["tool"], "open_website")
        self.assertTrue(res_search["step"]["input"]["url"].startswith("https://www.google.com/search"))
        self.assertIn("nvidia", res_search["step"]["input"]["url"])

    def test_router_stats(self):
        increment_router_stat("FAST_COMMAND", elapsed_time=0.150)
        increment_router_stat("MINI_PLANNER", fallback=True, fallback_reason="plan contains more than 5 steps")
        increment_router_stat("PLANNER_V2")
        increment_router_stat("FAST_COMMAND", confirmation=True)

        with open(self.stats_file, "r", encoding="utf-8") as f:
            stats = json.load(f)

        self.assertEqual(stats["fast_command"], 2)
        self.assertEqual(stats["mini_planner"], 1)
        self.assertEqual(stats["planner_v2"], 1)
        self.assertEqual(stats["fallbacks"], 1)
        self.assertEqual(stats["confirmations"], 1)
        self.assertGreater(stats["avg_fast_time"], 0)
        self.assertEqual(stats["fallback_log"][0]["reason"], "plan contains more than 5 steps")

    def test_update_request_stat(self):
        from core.intents.fast_command_router import update_request_stat
        
        update_request_stat("completed")
        update_request_stat("cancelled")
        update_request_stat("failed")
        update_request_stat("completed")

        with open(self.stats_file, "r", encoding="utf-8") as f:
            stats = json.load(f)

        self.assertEqual(stats["requests_completed"], 2)
        self.assertEqual(stats["requests_cancelled"], 1)
        self.assertEqual(stats["requests_failed"], 1)

    @patch("ai.engine.ask_ai")
    def test_ollama_call_counts(self, mock_ask_ai):
        # 1. FAST_COMMAND -> should make exactly 0 calls to Ollama (ask_ai)
        mock_reg = MagicMock()
        
        # Test routing for our flexible matching commands
        for cmd in ["zapni chrom", "zapni chrome", "otevři chrome", "zapni epic", "otevři epic games"]:
            route_info = classify_routing_level(cmd)
            self.assertEqual(route_info["route"], "FAST_COMMAND")
            self.assertIsNotNone(route_info["step"])
        
        self.assertEqual(mock_ask_ai.call_count, 0)

        # 2. MINI_PLANNER -> should make exactly 1 call to Ollama (ask_ai) for planning
        from core.planner import Planner
        mock_ask_ai.return_value = '[{"tool": "open_app", "input": {"name": "chrome"}, "description": "test"}]'
        
        planner = Planner(registry=mock_reg)
        steps = planner.plan("Otevři Chrome a vyhledej Nvidia")
        
        self.assertEqual(len(steps), 1)
        self.assertEqual(mock_ask_ai.call_count, 1)

    def test_request_context_state_lifecycle(self):
        from ai.engine import (
            reset_current_request,
            complete_current_request,
            cancel_current_request,
            fail_current_request,
            check_request_context_block,
            ask_ai,
            generate_stream
        )
        # 1. Reset context
        ctx = reset_current_request()
        self.assertFalse(ctx.completed)
        self.assertFalse(ctx.cancelled)
        self.assertFalse(ctx.failed)
        self.assertFalse(check_request_context_block())

        # 2. Reset again should cancel the previous one
        ctx2 = reset_current_request()
        self.assertTrue(ctx.cancelled)
        self.assertFalse(ctx2.cancelled)
        
        # 3. Test completed status blocking AI call
        complete_current_request()
        self.assertTrue(ctx2.completed)
        self.assertTrue(check_request_context_block())
        self.assertEqual(ask_ai("Ahoj"), "")
        self.assertEqual(list(generate_stream("Ahoj")), [])

        # 4. Test cancelled status blocking AI call
        ctx3 = reset_current_request()
        cancel_current_request()
        self.assertTrue(ctx3.cancelled)
        self.assertTrue(check_request_context_block())
        self.assertEqual(ask_ai("Ahoj"), "")
        self.assertEqual(list(generate_stream("Ahoj")), [])

        # 5. Test failed status blocking AI call
        ctx4 = reset_current_request()
        fail_current_request()
        self.assertTrue(ctx4.failed)
        self.assertTrue(check_request_context_block())
        self.assertEqual(ask_ai("Ahoj"), "")
        self.assertEqual(list(generate_stream("Ahoj")), [])

    @patch("core.agent.resolve_shortcut")
    @patch("core.agent.subprocess.Popen")
    @patch("core.agent.os.startfile")
    @patch("core.agent.os.path.exists", return_value=True)
    def test_launch_path_exe_direct(self, mock_exists, mock_startfile, mock_popen, mock_resolve_shortcut):
        from core.agent import launch_path
        res = launch_path("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "chrome")
        self.assertTrue(res["ok"])
        self.assertEqual(res["path"], "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
        mock_popen.assert_called_once_with(["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"])
        mock_startfile.assert_not_called()

    @patch("core.agent.resolve_shortcut", return_value="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
    @patch("core.agent.subprocess.Popen")
    @patch("core.agent.os.startfile")
    @patch("core.agent.os.path.exists", return_value=True)
    def test_launch_path_lnk_shortcut_success(self, mock_exists, mock_startfile, mock_popen, mock_resolve_shortcut):
        from core.agent import launch_path
        res = launch_path("C:\\Users\\Public\\Desktop\\Google Chrome.lnk", "chrome")
        self.assertTrue(res["ok"])
        self.assertEqual(res["path"], "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
        mock_resolve_shortcut.assert_called_once_with("C:\\Users\\Public\\Desktop\\Google Chrome.lnk")
        mock_popen.assert_called_once_with(["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"])
        mock_startfile.assert_not_called()

    @patch("core.agent.resolve_shortcut", return_value="C:\\Program Files\\NonExistent\\target.exe")
    @patch("core.agent.subprocess.Popen")
    @patch("core.agent.os.startfile")
    @patch("core.agent.os.path.exists")
    def test_launch_path_lnk_shortcut_missing_target_fallback(self, mock_exists, mock_startfile, mock_popen, mock_resolve_shortcut):
        def exists_side_effect(path):
            if path.endswith(".lnk"):
                return True
            return False
        mock_exists.side_effect = exists_side_effect
        
        from core.agent import launch_path
        res = launch_path("C:\\Users\\Public\\Desktop\\Google Chrome.lnk", "chrome")
        self.assertTrue(res["ok"])
        self.assertEqual(res["path"], "C:\\Users\\Public\\Desktop\\Google Chrome.lnk")
        mock_resolve_shortcut.assert_called_once_with("C:\\Users\\Public\\Desktop\\Google Chrome.lnk")
        mock_startfile.assert_called_once_with("C:\\Users\\Public\\Desktop\\Google Chrome.lnk")
        mock_popen.assert_not_called()

    @patch("subprocess.run")
    def test_resolve_shortcut_powershell_fallback(self, mock_run):
        from core.agent import resolve_shortcut
        
        mock_res = MagicMock()
        mock_res.stdout = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\n"
        mock_run.return_value = mock_res
        
        with patch.dict("sys.modules", {"win32com": None}):
            target = resolve_shortcut("C:\\Users\\Public\\Desktop\\Google Chrome.lnk")
            self.assertEqual(target, "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
            args, kwargs = mock_run.call_args
            self.assertIn("powershell", args[0])

    def test_refresh_apps_routing(self):
        res = classify_routing_level("refresh_apps")
        self.assertEqual(res["route"], "FAST_COMMAND")
        self.assertEqual(res["confidence"], 1.0)
        self.assertEqual(res["step"]["tool"], "refresh_apps")

        res2 = classify_routing_level("refresh apps")
        self.assertEqual(res2["route"], "FAST_COMMAND")
        self.assertEqual(res2["confidence"], 1.0)
        self.assertEqual(res2["step"]["tool"], "refresh_apps")


class RouterIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.getenv("JARVIS_RUN_INTEGRATION_TESTS") == "1", "Integration tests disabled unless JARVIS_RUN_INTEGRATION_TESTS=1")
    def test_zapni_chrome_integration(self):
        from core.intents.fast_command_router import classify_routing_level
        from core.agent import load_scanned_apps, launch_path
        
        res = classify_routing_level("zapni chrome")
        self.assertEqual(res["route"], "FAST_COMMAND")
        self.assertGreaterEqual(res["confidence"], 0.90)
        self.assertIsNotNone(res["step"])
        self.assertEqual(res["step"]["tool"], "open_app")
        
        scanned = load_scanned_apps()
        chrome_path = scanned.get("google chrome") or scanned.get("chrome")
        if not chrome_path:
            self.skipTest("Chrome not found on host machine.")
            
        launch_res = launch_path(chrome_path, "chrome")
        self.assertTrue(launch_res["ok"])
        
        import time
        time.sleep(2)
        
        import subprocess
        tasklist_res = subprocess.run(["tasklist"], capture_output=True, text=True)
        self.assertIn("chrome.exe", tasklist_res.stdout.lower(), "chrome.exe process is not running according to tasklist")

if __name__ == "__main__":
    unittest.main()
