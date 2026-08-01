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
    CancelDialogTool,
    OpenSearchResultTool,
)
from vision.ui_detector import UIDetector
from vision.schemas.ui_element import UIElement
from vision.schemas.ui_response import UIResponse


class TestTaskMemory(unittest.TestCase):
    def setUp(self):
        # Patch the persistent file path to a temp location
        self.patcher = patch("core.task_memory.TASK_MEMORY_FILE", "temp_task_memory.json")
        self.patcher.start()
        self.memory = TaskMemory()

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists("temp_task_memory.json"):
            try:
                os.remove("temp_task_memory.json")
            except OSError:
                pass

    def test_start_and_update_task(self):
        steps = [
            {"tool": "open_app", "input": {"name": "chrome"}, "description": "Otevřít Chrome"},
            {"tool": "smart_click", "input": {"target": "Hledat"}, "description": "Kliknout na Hledat"},
        ]
        self.memory.start_task("Najdi seznam", steps)
        self.assertEqual(self.memory.current_task, "Najdi seznam")
        self.assertEqual(len(self.memory.steps), 2)
        self.assertEqual(self.memory.steps[0]["status"], "pending")
        self.assertEqual(self.memory.steps[0]["description"], "Otevřít Chrome")

        # Update status to in_progress
        self.memory.update_step_status(0, "in_progress")
        self.assertEqual(self.memory.steps[0]["status"], "in_progress")

        # Save and load to verify persistence
        loaded_memory = TaskMemory()
        self.assertTrue(loaded_memory.load())
        self.assertEqual(loaded_memory.current_task, "Najdi seznam")
        self.assertEqual(loaded_memory.steps[0]["status"], "in_progress")

        # Reset
        self.memory.reset()
        self.assertEqual(self.memory.current_task, "")
        self.assertFalse(os.path.exists("temp_task_memory.json"))


class TestVision2(unittest.TestCase):
    @patch("vision.tesseract_validator.check_tesseract", return_value=(True, "Mocked"))
    @patch("pytesseract.image_to_data")
    @patch("pyautogui.getActiveWindowTitle")
    @patch("ai.engine.ask_ai")
    @patch("PIL.Image.open")
    def test_ui_detector_llama3(self, mock_image_open, mock_ask_ai, mock_active_window, mock_ocr_data, mock_check_tess):
        mock_img = MagicMock()
        mock_img.width = 1920
        mock_img.height = 1080
        mock_image_open.return_value.__enter__.return_value = mock_img
        mock_image_open.return_value.width = 1920
        mock_image_open.return_value.height = 1080
        
        mock_active_window.return_value = "Chrome Web Browser"
        mock_ocr_data.return_value = {
            "text": ["", "Hledat", "Prihlasit"],
            "conf": [0.0, 90.0, 85.0],
            "left": [0, 100, 440],
            "top": [0, 50, 220],
            "width": [0, 80, 120],
            "height": [0, 30, 40],
            "line_num": [0, 1, 1],
            "block_num": [0, 1, 1],
        }
        
        # Mock LLM JSON output identifying elements
        mock_ask_ai.return_value = json.dumps({
            "screen_type": "browser",
            "elements": [
                {
                    "id": "input_search",
                    "type": "input",
                    "text": "Hledat",
                    "x": 100,
                    "y": 50,
                    "width": 80,
                    "height": 30,
                    "confidence": 0.95
                },
                {
                    "id": "btn_login",
                    "type": "button",
                    "text": "Prihlasit",
                    "x": 440,
                    "y": 220,
                    "width": 120,
                    "height": 40,
                    "confidence": 0.96
                }
            ]
        })

        detector = UIDetector()
        response = detector.detect_screenshot("mock_image.png")
        
        self.assertEqual(response.screen_type, "browser")
        self.assertEqual(len(response.elements), 2)
        self.assertEqual(response.elements[0].type, "input")
        self.assertEqual(response.elements[1].type, "button")
        self.assertEqual(response.elements[1].center, (500, 240))


class TestSmartPCControl(unittest.TestCase):
    def setUp(self):
        self.ctx = ToolContext(dry_run=True)
        self.state = JarvisState()
        self.state.data["action_confirmed"] = True
        
        # Create a mock screen response
        elements = [
            UIElement(id="btn_login", type="button", text="Přihlásit se", x=400, y=200, width=100, height=30, confidence=0.9),
            UIElement(id="inp_username", type="input", text="Uživatelské jméno", x=100, y=100, width=150, height=25, confidence=0.8),
            UIElement(id="chk_agree", type="checkbox", text="Souhlasím", x=100, y=150, width=20, height=20, confidence=0.95)
        ]
        self.mock_ui_response = UIResponse(screen_type="browser", elements=elements, image_width=1920, image_height=1080)

    @patch("vision.ui_detector.UIDetector.detect_screen")
    @patch("tools.pc_control._post_agent")
    def test_smart_click(self, mock_post, mock_detect):
        mock_detect.return_value = self.mock_ui_response
        mock_post.return_value = {"ok": True}

        tool = SmartClickTool()
        result = tool.run({"target": "přihlásit"}, self.ctx, self.state)
        
        self.assertTrue(result["ok"])
        # Should click the center of the matching element (400 + 100//2 = 450, 200 + 30//2 = 215)
        mock_post.assert_called_with(self.ctx, "click", {"x": 450, "y": 215})

    @patch("vision.ui_detector.UIDetector.detect_screen")
    @patch("tools.pc_control._post_agent")
    def test_smart_write(self, mock_post, mock_detect):
        mock_detect.return_value = self.mock_ui_response
        mock_post.return_value = {"ok": True}

        tool = SmartWriteTool()
        result = tool.run({"target": "jméno", "text": "petr"}, self.ctx, self.state)

        self.assertTrue(result["ok"])
        # First clicks input field (100 + 150//2 = 175, 100 + 25//2 = 112) then writes text
        mock_post.assert_any_call(self.ctx, "click", {"x": 175, "y": 112})
        mock_post.assert_any_call(self.ctx, "write", "petr")

    @patch("tools.pc_control._post_agent")
    def test_close_window(self, mock_post):
        mock_post.return_value = {"ok": True}
        tool = CloseWindowTool()
        result = tool.run({}, self.ctx, self.state)
        self.assertTrue(result["ok"])
        mock_post.assert_called_with(self.ctx, "hotkey", ["alt", "f4"])


class TestPlannerExecutorV2(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        # Register a tool that will fail initially but succeed on repair
        self.mock_tool = MagicMock()
        self.mock_tool.name = "test_tool"
        self.mock_tool.description = "Mock test tool"
        self.mock_tool.input_schema = {}
        self.registry.register(self.mock_tool)

    @patch("ai.engine.ask_ai")
    @patch("vision.ui_detector.UIDetector.detect_screen")
    def test_executor_auto_repair_success(self, mock_detect, mock_ask_ai):
        # 1. Setup tool mock: fails first, then succeeds
        self.mock_tool.run.side_effect = [
            {"ok": False, "error": "Element not visible"},
            {"ok": True, "result": "Successfully clicked element after wait"}
        ]
        
        # 2. Setup visual detector
        elements = [UIElement(id="1", type="button", text="Tlačítko", x=10, y=20, width=50, height=20, confidence=0.9)]
        mock_detect.return_value = UIResponse(screen_type="browser", elements=elements, image_width=1000, image_height=800)

        # 3. Setup Llama 3 repair response (JSON action suggesting waiting or clicking alternate)
        mock_ask_ai.return_value = json.dumps({
            "tool": "test_tool",
            "input": {"action": "retry"},
            "description": "Zkusit akci znovu"
        })

        ctx = ToolContext(dry_run=True)
        state = JarvisState()
        executor = Executor(registry=self.registry, ctx=ctx, state=state)

        steps = [
            {"tool": "test_tool", "input": {}, "description": "Pustit testovací tool"}
        ]

        results = executor.run_plan(steps)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["output"]["ok"])
        self.assertIn("byl úspěšně opraven", results[0]["output"]["result"])

    @patch("ai.engine.ask_ai")
    @patch("vision.ui_detector.UIDetector.detect_screen")
    def test_executor_unrecoverable_failure(self, mock_detect, mock_ask_ai):
        self.mock_tool.run.side_effect = [
            {"ok": False, "error": "Password input requested"}
        ]
        elements = [UIElement(id="1", type="input", text="Heslo", x=10, y=20, width=50, height=20, confidence=0.9)]
        mock_detect.return_value = UIResponse(screen_type="browser", elements=elements, image_width=1000, image_height=800)

        # Llama 3 response indicating failure is unrecoverable without user password input
        mock_ask_ai.return_value = json.dumps({
            "unrecoverable": True,
            "message": "Prosím zadejte své heslo, asistent ho nezná."
        })

        ctx = ToolContext(dry_run=True)
        state = JarvisState()
        executor = Executor(registry=self.registry, ctx=ctx, state=state)

        steps = [
            {"tool": "test_tool", "input": {}, "description": "Spustit chráněný úkol"}
        ]

        results = executor.run_plan(steps)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["output"]["ok"])
        self.assertEqual(state.data.get("user_help_required"), "Prosím zadejte své heslo, asistent ho nezná.")


if __name__ == "__main__":
    unittest.main()
