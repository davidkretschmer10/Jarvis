# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import os
import json
import shutil

from tests.stress.performance_monitor import PerformanceMonitor
from tests.stress.router_stress import run_router_stress
from tests.stress.mini_planner_stress import run_mini_planner_stress
from tests.stress.planner_v2_stress import run_planner_v2_stress
from tests.stress.chaos_test import run_chaos_tests

class StressFrameworkTests(unittest.TestCase):
    def setUp(self):
        self.test_dir = "logs/test_logs"
        os.makedirs(self.test_dir, exist_ok=True)
        self.perf_log = os.path.join(self.test_dir, "perf.json")
        
    def tearDown(self):
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_performance_monitor_gathering(self):
        pm = PerformanceMonitor(log_path=self.perf_log, interval=1)
        ram = pm.get_process_ram()
        self.assertIsInstance(ram, float)
        
        count = pm.get_jarvis_processes_count()
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 1)

    def test_router_stress_simulation(self):
        mock_cache = {
            "google chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "epic games launcher": "C:\\Program Files\\Epic Games\\Launcher\\Portal\\Binaries\\Win64\\EpicGamesLauncher.exe"
        }
        res = run_router_stress(num_iterations=5, mock_cache_data=mock_cache)
        
        self.assertEqual(res["total_runs"], 5)
        self.assertEqual(res["ollama_leaks"], 0)
        self.assertIsInstance(res["success_runs"], int)
        self.assertIsInstance(res["failed_runs"], int)
        self.assertEqual(len(res["elapsed_times"]), 5)

    def test_mini_planner_stress_simulation(self):
        res = run_mini_planner_stress(num_iterations=2)
        self.assertEqual(res["total_runs"], 2)
        self.assertIsInstance(res["success_runs"], int)
        self.assertIsInstance(res["ollama_calls"], int)

    def test_planner_v2_stress_simulation(self):
        res = run_planner_v2_stress(num_iterations=2)
        self.assertEqual(res["total_runs"], 2)
        self.assertIsInstance(res["success_runs"], int)

    def test_chaos_scenarios(self):
        res = run_chaos_tests()
        self.assertGreater(res["total_chaos_runs"], 0)
        self.assertIn("success_runs", res)
        self.assertIn("failed_runs", res)
        self.assertIsInstance(res["failures_details"], list)

    def test_crash_log_writing(self):
        crash_dir = "logs/test_crashes"
        os.makedirs(crash_dir, exist_ok=True)
        try:
            crash_data = {
                "timestamp": "2026-06-11 22:00:00",
                "last_command": "zapni chrome",
                "error": "TestError",
                "stack_trace": "line 1... in test",
                "request_id": "test_req_123"
            }
            filename = os.path.join(crash_dir, "crash_test.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(crash_data, f, indent=4, ensure_ascii=False)
                
            self.assertTrue(os.path.exists(filename))
            with open(filename, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["error"], "TestError")
            self.assertEqual(loaded["request_id"], "test_req_123")
        finally:
            if os.path.exists(crash_dir):
                shutil.rmtree(crash_dir)

if __name__ == "__main__":
    unittest.main()
