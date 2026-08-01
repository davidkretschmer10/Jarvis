from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from core.task_memory import TaskMemory
from core.state import JarvisState
from core.planner import Planner
from core.executor import Executor
from tools.base import ToolContext
from tools.registry import ToolRegistry
from tools.pc_control import (
    SmartClickTool,
    SmartWriteTool,
    SmartCheckboxTool,
    CloseWindowTool,
    ConfirmDialogTool,
)
from tools.file_manager import WriteTextFileTool
from vision.ui_detector import UIDetector, VisionError
from vision.schemas.ui_element import UIElement
from vision.schemas.ui_response import UIResponse
from vision.tesseract_validator import check_tesseract
from core.intents.command_router import build_search_url


class TestTesseractValidation(unittest.TestCase):
    @patch("pytesseract.get_tesseract_version")
    def test_check_tesseract_pytesseract_success(self, mock_get_ver):
        mock_get_ver.return_value = "5.3.0.20230503"
        ok, msg = check_tesseract()
        self.assertTrue(ok)
        self.assertIn("5.3.0", msg)

    @patch("pytesseract.get_tesseract_version")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_check_tesseract_subprocess_fallback(self, mock_run, mock_which, mock_get_ver):
        mock_get_ver.side_effect = Exception("Import error or similar")
        mock_which.return_value = "/usr/bin/tesseract"
        
        mock_subprocess_result = MagicMock()
        mock_subprocess_result.return_code = 0
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "tesseract v5.1.0\n leptonica-1.82.0"
        mock_run.return_value = mock_subprocess_result
        
        ok, msg = check_tesseract()
        self.assertTrue(ok)
        self.assertIn("v5.1.0", msg)

    @patch("pytesseract.get_tesseract_version")
    @patch("shutil.which")
    def test_check_tesseract_missing(self, mock_which, mock_get_ver):
        mock_get_ver.side_effect = Exception("No pytesseract")
        mock_which.return_value = None
        ok, msg = check_tesseract()
        self.assertFalse(ok)
        self.assertEqual(msg, "Chybí Tesseract")


class TestVisionFailsafe(unittest.TestCase):
    @patch("core.task_memory.TASK_MEMORY_FILE", "temp_task_memory.json")
    def test_vision_failsafe_halts_execution(self):
        # Register a tool that raises VisionError
        reg = ToolRegistry()
        
        class MockFailingTool:
            name = "mock_fail"
            description = "Fails with VisionError"
            input_schema = {"type": "object"}
            def run(self, tool_input, ctx, state):
                raise VisionError("OCR failed")
                
        reg.register(MockFailingTool())
        
        task_memory = TaskMemory()
        ctx = ToolContext(dry_run=False, agent_base_url="http://localhost", workspace_root=".")
        state = JarvisState()
        
        executor = Executor(registry=reg, ctx=ctx, state=state, task_memory=task_memory)
        
        steps = [
            {"tool": "mock_fail", "input": {}, "description": "Execute mock fail"},
            {"tool": "mock_fail", "input": {}, "description": "Should not run"}
        ]
        
        results = executor.run_plan(steps)
        
        # Verify execution was terminated on the first step
        self.assertEqual(len(results), 1)
        self.assertEqual(state.data.get("user_help_required"), "Vision systém není dostupný. Zkontrolujte instalaci OCR.")
        self.assertEqual(task_memory.steps[0]["status"], "failed")
        self.assertEqual(task_memory.steps[1]["status"], "pending")
        
        if os.path.exists("temp_task_memory.json"):
            try:
                os.remove("temp_task_memory.json")
            except OSError:
                pass


class TestAutoRepairHardening(unittest.TestCase):
    @patch("vision.ui_detector.UIDetector.detect_screen")
    @patch("ai.engine.ask_ai")
    @patch("core.task_memory.TASK_MEMORY_FILE", "temp_task_memory.json")
    def test_auto_repair_regex_json_extraction(self, mock_ask_ai, mock_detect_screen):
        # Mock detector response
        mock_response = UIResponse(screen_type="browser", elements=[], image_path="fake.png")
        mock_detect_screen.return_value = mock_response
        
        reg = ToolRegistry()
        # Register smart_click
        smart_click = SmartClickTool()
        reg.register(smart_click)
        
        # Mock LLM return with markdown prefix/suffix
        mock_ask_ai.return_value = """
        Analysis completed. Here is your repair action:
        ```json
        {
          "tool": "smart_click",
          "input": {"target": "Odeslat"},
          "description": "Opravný krok: Kliknout na Odeslat"
        }
        ```
        Hope it helps.
        """
        
        task_memory = TaskMemory()
        ctx = ToolContext(dry_run=False, agent_base_url="http://localhost", workspace_root=".")
        state = JarvisState()
        
        executor = Executor(registry=reg, ctx=ctx, state=state, task_memory=task_memory)
        
        # Mocking smart_click tool run to succeed on repair execution
        with patch.object(SmartClickTool, "run") as mock_run:
            mock_run.return_value = {"ok": True, "result": "Success"}
            
            repaired = executor._attempt_repair(
                failed_step={"tool": "smart_click", "input": {"target": "Send"}},
                error_msg="Element not found"
            )
            
            self.assertTrue(repaired)
            mock_run.assert_called_once()
            
        if os.path.exists("temp_task_memory.json"):
            try:
                os.remove("temp_task_memory.json")
            except OSError:
                pass


class TestChromeSmartActions(unittest.TestCase):
    def test_direct_searches(self):
        # Google searches
        url1 = build_search_url("Google a vyhledej počasí", "Otevři Google a vyhledej počasí")
        self.assertEqual(url1, "https://www.google.com/search?q=pocasi")
        
        # YouTube searches
        url2 = build_search_url("YouTube a vyhledej oblíbené songy", "Otevři YouTube a vyhledej oblíbené songy")
        self.assertEqual(url2, "https://www.youtube.com/results?search_query=oblibene%20songy")
        
        # Seznam searches
        url3 = build_search_url("Seznam a vyhledej novinky", "Otevři Seznam a vyhledej novinky")
        self.assertEqual(url3, "https://search.seznam.cz/?q=novinky")

    def test_direct_base_urls(self):
        self.assertEqual(build_search_url("Google", "Otevři Google"), "https://www.google.com/")
        self.assertEqual(build_search_url("Seznam", "Otevři Seznam"), "https://www.seznam.cz/")
        self.assertEqual(build_search_url("YouTube", "Otevři YouTube"), "https://www.youtube.com/")


class TestConfidenceAndSafety(unittest.TestCase):
    @patch("vision.ui_detector.UIDetector.detect_screen")
    @patch("tools.pc_control._post_agent")
    def test_smart_click_confidence_gating(self, mock_post, mock_detect_screen):
        # Element under 0.70 confidence -> CONFIRMATION_REQUIRED
        low_conf_el = UIElement(id="btn_1", type="button", text="Přihlásit", x=100, y=200, width=50, height=20, confidence=0.65)
        mock_detect_screen.return_value = UIResponse(screen_type="test", elements=[low_conf_el], image_path="fake.png")
        
        smart_click = SmartClickTool()
        state = JarvisState()
        ctx = ToolContext(dry_run=False, agent_base_url="http://localhost", workspace_root=".")
        
        # 1. First run: No pre-approval
        res = smart_click.run({"target": "Přihlásit"}, ctx, state)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "CONFIRMATION_REQUIRED")
        self.assertIn("Nízká spolehlivost", res["message"])
        
        # 2. Second run: Pre-approved
        state.data["action_confirmed"] = True
        mock_post.return_value = {"ok": True, "result": "Clicked"}
        
        res = smart_click.run({"target": "Přihlásit"}, ctx, state)
        self.assertTrue(res["ok"])
        self.assertFalse(state.data.get("action_confirmed", False)) # Resets flag

    def test_risky_tools_require_confirmation(self):
        close_tool = CloseWindowTool()
        write_file_tool = WriteTextFileTool()
        state = JarvisState()
        ctx = ToolContext(dry_run=False, agent_base_url="http://localhost", workspace_root=".")
        
        # Close Window
        res_close = close_tool.run({}, ctx, state)
        self.assertFalse(res_close["ok"])
        self.assertEqual(res_close["error"], "CONFIRMATION_REQUIRED")
        
        state.data["action_confirmed"] = True
        with patch("tools.pc_control._post_agent") as mock_post:
            mock_post.return_value = {"ok": True}
            res_close2 = close_tool.run({}, ctx, state)
            self.assertTrue(res_close2["ok"])
            
        # Write file safety confirmation
        state.data["action_confirmed"] = False
        res_write = write_file_tool.run({"path": "test.txt", "content": "hello"}, ctx, state)
        self.assertFalse(res_write["ok"])
        self.assertEqual(res_write["error"], "CONFIRMATION_REQUIRED")
