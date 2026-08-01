from __future__ import annotations

import os
from typing import Any, Dict, List

from tools.base import JSON, ToolContext


def _root(ctx: ToolContext) -> str:
    return ctx.workspace_root or os.getcwd()


def _resolve_under_root(ctx: ToolContext, rel_path: str) -> str:
    root = os.path.abspath(_root(ctx))
    candidate = os.path.abspath(os.path.join(root, rel_path))
    try:
        common = os.path.commonpath([root, candidate])
    except ValueError:
        common = ""
    if common != root:
        raise ValueError(f"Path escapes workspace: {rel_path}")
    return candidate


class ReadTextFileTool:
    name = "read_text_file"
    description = "Read a UTF-8 text file from workspace (safe, no binaries)."
    input_schema: JSON = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "max_chars": {"type": "integer"}},
        "required": ["path"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        rel = str(tool_input.get("path", ""))
        max_chars = int(tool_input.get("max_chars", 8000))
        try:
            path = _resolve_under_root(ctx, rel)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        if not os.path.isfile(path):
            return {"ok": False, "error": f"File not found: {rel}"}

        with open(path, "r", encoding="utf-8") as f:
            content = f.read(max_chars)
        return {
            "ok": True,
            "result": content,
            "save_to_state": {"last_read_path": path},
            "path": path,
            "truncated": len(content) >= max_chars,
        }


class WriteTextFileTool:
    name = "write_text_file"
    description = "Write a UTF-8 text file under workspace."
    input_schema: JSON = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        rel = str(tool_input.get("path", ""))
        content = str(tool_input.get("content", ""))
        try:
            path = _resolve_under_root(ctx, rel)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        if state is not None and not state.data.get("action_confirmed"):
            return {
                "ok": False,
                "error": "CONFIRMATION_REQUIRED",
                "message": f"Detekoval jsem zápis do souboru '{rel}'. Přejete si přesto pokračovat?"
            }
        if state is not None:
            state.data["action_confirmed"] = False

        if ctx.dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "result": f"Would write {path}",
                "created_files": [path],
                "save_to_state": {"last_written_path": path},
                "bytes": len(content.encode("utf-8")),
            }

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "ok": True,
            "result": f"Wrote {path}",
            "created_files": [path],
            "save_to_state": {"last_written_path": path},
            "path": path,
            "bytes": len(content.encode("utf-8")),
        }


class ListDirTool:
    name = "list_dir"
    description = "List files in a directory under workspace."
    input_schema: JSON = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        rel = str(tool_input.get("path", "."))
        try:
            path = _resolve_under_root(ctx, rel)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        if not os.path.isdir(path):
            return {"ok": False, "error": f"Directory not found: {rel}"}
        items: List[Dict[str, Any]] = []
        for name in os.listdir(path):
            p = os.path.join(path, name)
            items.append({"name": name, "is_dir": os.path.isdir(p), "size": os.path.getsize(p) if os.path.isfile(p) else None})
        return {"ok": True, "result": items, "save_to_state": {"last_listed_dir": path}, "path": path, "items": items}

