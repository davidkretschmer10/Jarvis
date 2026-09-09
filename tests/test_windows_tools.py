# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from core.security_policy import ActionRisk, ToolCapability
from tools.base import ToolContext
from tools.file_manager import (
    CopyFileTool,
    CreateDirectoryTool,
    CreateFileTool,
    DeleteDirectoryTool,
    DeleteFileTool,
    ListDirTool,
    MoveFileTool,
    ReadFileTool,
    ReadTextFileTool,
    WriteFileTool,
    WriteTextFileTool,
)
from tools.pc_control import (
    DoubleClickTool,
    OpenUrlTool,
    TypeTextTool,
    WriteTextTool,
)
from tools.registry import ToolRegistry, build_default_registry


class TestWindowsTools(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="jarvis_win_tools_test_")
        self.ctx = ToolContext(workspace_root=self.tmp_dir)

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_and_read_file(self):
        target = os.path.join(self.tmp_dir, "new_doc.txt")
        create_tool = CreateFileTool()
        res_create = create_tool.run({"path": target, "content": "Hello Windows"}, self.ctx, None)
        self.assertTrue(res_create["ok"])
        self.assertTrue(os.path.isfile(target))

        read_tool = ReadFileTool()
        res_read = read_tool.run({"path": target}, self.ctx, None)
        self.assertTrue(res_read["ok"])
        self.assertEqual(res_read["result"], "Hello Windows")

    def test_write_file_and_read_alias(self):
        target = os.path.join(self.tmp_dir, "notes.txt")
        write_tool = WriteFileTool()
        res_write = write_tool.run({"path": target, "content": "Updated content"}, self.ctx, None)
        self.assertTrue(res_write["ok"])

        # read_text_file alias
        read_text_tool = ReadTextFileTool()
        res_read = read_text_tool.run({"path": "notes.txt"}, self.ctx, None)
        self.assertTrue(res_read["ok"])
        self.assertEqual(res_read["result"], "Updated content")

    def test_copy_file(self):
        src = os.path.join(self.tmp_dir, "src.txt")
        dst = os.path.join(self.tmp_dir, "sub", "dst.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("copy payload")

        copy_tool = CopyFileTool()
        res = copy_tool.run({"source": src, "destination": dst}, self.ctx, None)
        self.assertTrue(res["ok"])
        self.assertTrue(os.path.isfile(src))
        self.assertTrue(os.path.isfile(dst))
        with open(dst, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "copy payload")

    def test_move_file(self):
        src = os.path.join(self.tmp_dir, "initial.txt")
        dst = os.path.join(self.tmp_dir, "moved.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("move payload")

        move_tool = MoveFileTool()
        res = move_tool.run({"source": src, "destination": dst}, self.ctx, None)
        self.assertTrue(res["ok"])
        self.assertFalse(os.path.exists(src))
        self.assertTrue(os.path.isfile(dst))

    def test_delete_file_and_idempotence(self):
        target = os.path.join(self.tmp_dir, "to_delete.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("temp")

        del_tool = DeleteFileTool()
        res1 = del_tool.run({"path": target}, self.ctx, None)
        self.assertTrue(res1["ok"])
        self.assertFalse(os.path.exists(target))

        # Second run: file already absent, must succeed idempotently
        res2 = del_tool.run({"path": target}, self.ctx, None)
        self.assertTrue(res2["ok"])
        self.assertTrue(res2.get("already_deleted", False))

    def test_create_and_delete_directory_idempotence(self):
        sub_dir = os.path.join(self.tmp_dir, "sub_folder", "inner")
        create_dir = CreateDirectoryTool()
        res_create = create_dir.run({"path": sub_dir}, self.ctx, None)
        self.assertTrue(res_create["ok"])
        self.assertTrue(os.path.isdir(sub_dir))

        del_dir = DeleteDirectoryTool()
        # Delete with recursive
        res_del = del_dir.run({"path": os.path.join(self.tmp_dir, "sub_folder"), "recursive": True}, self.ctx, None)
        self.assertTrue(res_del["ok"])
        self.assertFalse(os.path.exists(sub_dir))

        # Idempotent delete when already absent
        res_del2 = del_dir.run({"path": sub_dir}, self.ctx, None)
        self.assertTrue(res_del2["ok"])
        self.assertTrue(res_del2.get("already_deleted", False))

    def test_open_url_validates_scheme(self):
        url_tool = OpenUrlTool()
        # Non-http scheme rejected
        res_bad = url_tool.run({"url": "javascript:alert(1)"}, self.ctx, None)
        self.assertFalse(res_bad["ok"])
        self.assertIn("Invalid URL scheme", res_bad["error"])

        # File scheme rejected
        res_file = url_tool.run({"url": "file:///c:/Windows/System32/cmd.exe"}, self.ctx, None)
        self.assertFalse(res_file["ok"])

    def test_default_registry_has_all_canonical_tools(self):
        reg = build_default_registry()
        expected = [
            "launch_application", "open_app",
            "open_url", "open_website", "open_path",
            "create_file", "read_file", "read_text_file",
            "write_file", "write_text_file",
            "copy_file", "move_file", "delete_file",
            "create_directory", "delete_directory",
            "process_exists", "get_process_info", "terminate_process",
            "window_exists", "close_window",
            "click", "double_click", "type_text", "write_text",
            "press_key", "hotkey", "screenshot", "read_screen"
        ]
        for tool_name in expected:
            tool = reg.get(tool_name)
            self.assertIsNotNone(tool, f"Expected tool '{tool_name}' missing in default registry.")
            self.assertIsInstance(tool.capability, ToolCapability)
            self.assertIsInstance(tool.risk, ActionRisk)
            self.assertGreater(tool.timeout, 0)


if __name__ == "__main__":
    unittest.main()
