import os
import tempfile
import unittest

from tools.base import ToolContext
from tools.file_manager import ListDirTool, ReadTextFileTool, WriteTextFileTool


class FileManagerToolTests(unittest.TestCase):
    def test_list_dir_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as root:
            result = ListDirTool().run({"path": ".."}, ToolContext(workspace_root=root), None)

        self.assertFalse(result["ok"])
        self.assertIn("escapes workspace", result["error"])

    def test_read_file_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as root:
            result = ReadTextFileTool().run({"path": "../secret.txt"}, ToolContext(workspace_root=root), None)

        self.assertFalse(result["ok"])
        self.assertIn("escapes workspace", result["error"])

    def test_write_file_stays_under_workspace(self):
        with tempfile.TemporaryDirectory() as root:
            ctx = ToolContext(workspace_root=root)
            result = WriteTextFileTool().run({"path": "notes/out.txt", "content": "hello"}, ctx, None)
            target = os.path.join(root, "notes", "out.txt")

            self.assertTrue(result["ok"])
            self.assertTrue(os.path.exists(target))
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "hello")


if __name__ == "__main__":
    unittest.main()
