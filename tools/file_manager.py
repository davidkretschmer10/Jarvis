# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Optional

from core.security_policy import ActionRisk, ToolCapability
from tools.base import JSON, ToolContext
from utils.path_utils import canonical_windows_path


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


def _resolve_any_path(ctx: ToolContext, path_str: str) -> str:
    """Resolve path deterministically using canonical_windows_path."""
    return canonical_windows_path(path_str, workspace_root=_root(ctx))


# ===========================================================================
# Legacy / Workspace-Constrained Tools (for backward compatibility)
# ===========================================================================

class ReadTextFileTool:
    name = "read_text_file"
    description = "Read a UTF-8 text file from workspace (safe, no binaries)."
    capability = ToolCapability.READ_FILE
    risk = ActionRisk.SAFE
    timeout = 10.0
    input_schema: JSON = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "max_chars": {"type": "integer"}},
        "required": ["path"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        rel = str(tool_input.get("path") or tool_input.get("file_path") or tool_input.get("filepath") or "")
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
    capability = ToolCapability.MODIFY_FILE
    risk = ActionRisk.MEDIUM
    timeout = 15.0
    input_schema: JSON = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        rel = str(tool_input.get("path") or tool_input.get("file_path") or tool_input.get("filepath") or "")
        content = str(tool_input.get("content", ""))
        try:
            path = _resolve_under_root(ctx, rel)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        if state is not None and not state.data.get("action_confirmed") and not state.data.get("action_authorized"):
            return {
                "ok": False,
                "error": "CONFIRMATION_REQUIRED",
                "message": f"Detekoval jsem zápis do souboru '{rel}'. Přejete si přesto pokračovat?"
            }
        if state is not None and not state.data.get("action_authorized"):
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
    capability = ToolCapability.READ_FILE
    risk = ActionRisk.SAFE
    timeout = 10.0
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


# ===========================================================================
# Authoritative Deterministic Windows File Tools
# ===========================================================================

class CreateFileTool:
    name = "create_file"
    description = "Create a new file with optional initial content."
    capability = ToolCapability.CREATE_FILE
    risk = ActionRisk.MEDIUM
    timeout = 15.0
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        raw_path = str(
            tool_input.get("path")
            or tool_input.get("file_path")
            or tool_input.get("filepath")
            or tool_input.get("target")
            or ""
        )
        if not raw_path:
            return {"ok": False, "error": "Missing required parameter 'path'"}

        path = _resolve_any_path(ctx, raw_path)
        content = str(tool_input.get("content", ""))

        if ctx.dry_run:
            return {"ok": True, "dry_run": True, "result": f"Would create file {path}", "path": path}

        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "ok": True,
                "result": f"Created file {path}",
                "path": path,
                "created_files": [path],
                "save_to_state": {"last_created_path": path},
                "bytes": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {"ok": False, "error": f"Failed to create file: {e}", "path": path}


class ReadFileTool:
    name = "read_file"
    description = "Read text content from a file."
    capability = ToolCapability.READ_FILE
    risk = ActionRisk.SAFE
    timeout = 10.0
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer"},
        },
        "required": ["path"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        raw_path = str(
            tool_input.get("path")
            or tool_input.get("file_path")
            or tool_input.get("filepath")
            or tool_input.get("target")
            or ""
        )
        if not raw_path:
            return {"ok": False, "error": "Missing required parameter 'path'"}

        path = _resolve_any_path(ctx, raw_path)
        max_chars = int(tool_input.get("max_chars", 8000))

        if not os.path.isfile(path):
            return {"ok": False, "error": f"File not found: {path}", "path": path}

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_chars)
            return {
                "ok": True,
                "result": content,
                "path": path,
                "save_to_state": {"last_read_path": path},
                "truncated": len(content) >= max_chars,
                "bytes": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {"ok": False, "error": f"Failed to read file: {e}", "path": path}


class WriteFileTool:
    name = "write_file"
    description = "Write content to a file, replacing existing content."
    capability = ToolCapability.MODIFY_FILE
    risk = ActionRisk.MEDIUM
    timeout = 15.0
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        raw_path = str(
            tool_input.get("path")
            or tool_input.get("file_path")
            or tool_input.get("filepath")
            or tool_input.get("target")
            or ""
        )
        if not raw_path:
            return {"ok": False, "error": "Missing required parameter 'path'"}

        path = _resolve_any_path(ctx, raw_path)
        content = str(tool_input.get("content", ""))

        if ctx.dry_run:
            return {"ok": True, "dry_run": True, "result": f"Would write {path}", "path": path}

        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "ok": True,
                "result": f"Wrote {path}",
                "path": path,
                "save_to_state": {"last_written_path": path},
                "bytes": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {"ok": False, "error": f"Failed to write file: {e}", "path": path}


class CopyFileTool:
    name = "copy_file"
    description = "Copy a file from source path to destination path."
    capability = ToolCapability.CREATE_FILE
    risk = ActionRisk.LOW
    timeout = 15.0
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "destination": {"type": "string"},
        },
        "required": ["source", "destination"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        raw_src = str(tool_input.get("source") or tool_input.get("src") or tool_input.get("from") or "")
        raw_dst = str(tool_input.get("destination") or tool_input.get("dst") or tool_input.get("to") or "")

        if not raw_src or not raw_dst:
            return {"ok": False, "error": "Both 'source' and 'destination' paths are required"}

        src = _resolve_any_path(ctx, raw_src)
        dst = _resolve_any_path(ctx, raw_dst)

        if not os.path.isfile(src):
            return {"ok": False, "error": f"Source file does not exist: {src}", "source": src}

        if ctx.dry_run:
            return {"ok": True, "dry_run": True, "result": f"Would copy {src} to {dst}", "source": src, "destination": dst}

        try:
            parent = os.path.dirname(dst)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(src, dst)
            return {
                "ok": True,
                "result": f"Copied {src} to {dst}",
                "source": src,
                "destination": dst,
                "size": os.path.getsize(dst),
            }
        except Exception as e:
            return {"ok": False, "error": f"Failed to copy file: {e}", "source": src, "destination": dst}


class MoveFileTool:
    name = "move_file"
    description = "Move or rename a file from source path to destination path."
    capability = ToolCapability.MODIFY_FILE
    risk = ActionRisk.MEDIUM
    timeout = 15.0
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "destination": {"type": "string"},
        },
        "required": ["source", "destination"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        raw_src = str(tool_input.get("source") or tool_input.get("src") or tool_input.get("from") or "")
        raw_dst = str(tool_input.get("destination") or tool_input.get("dst") or tool_input.get("to") or "")

        if not raw_src or not raw_dst:
            return {"ok": False, "error": "Both 'source' and 'destination' paths are required"}

        src = _resolve_any_path(ctx, raw_src)
        dst = _resolve_any_path(ctx, raw_dst)

        if not os.path.exists(src):
            return {"ok": False, "error": f"Source path does not exist: {src}", "source": src}

        if ctx.dry_run:
            return {"ok": True, "dry_run": True, "result": f"Would move {src} to {dst}", "source": src, "destination": dst}

        try:
            parent = os.path.dirname(dst)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.move(src, dst)
            return {
                "ok": True,
                "result": f"Moved {src} to {dst}",
                "source": src,
                "destination": dst,
            }
        except Exception as e:
            return {"ok": False, "error": f"Failed to move file: {e}", "source": src, "destination": dst}


class DeleteFileTool:
    name = "delete_file"
    description = "Delete a file. Idempotent: succeeds if the file is already gone."
    capability = ToolCapability.DELETE_FILE
    risk = ActionRisk.HIGH
    timeout = 10.0
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        raw_path = str(
            tool_input.get("path")
            or tool_input.get("file_path")
            or tool_input.get("filepath")
            or tool_input.get("target")
            or ""
        )
        if not raw_path:
            return {"ok": False, "error": "Missing required parameter 'path'"}

        path = _resolve_any_path(ctx, raw_path)

        # Idempotence: If file is already absent, return success
        if not os.path.exists(path):
            return {
                "ok": True,
                "result": f"File {path} does not exist (already deleted)",
                "path": path,
                "already_deleted": True,
            }

        if ctx.dry_run:
            return {"ok": True, "dry_run": True, "result": f"Would delete file {path}", "path": path}

        try:
            os.remove(path)
            return {
                "ok": True,
                "result": f"Deleted file {path}",
                "path": path,
                "deleted": True,
            }
        except Exception as e:
            return {"ok": False, "error": f"Failed to delete file: {e}", "path": path}


class CreateDirectoryTool:
    name = "create_directory"
    description = "Create a directory (and any necessary parent directories). Idempotent."
    capability = ToolCapability.CREATE_DIRECTORY
    risk = ActionRisk.LOW
    timeout = 10.0
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        raw_path = str(
            tool_input.get("path")
            or tool_input.get("directory_path")
            or tool_input.get("dir_path")
            or tool_input.get("directory")
            or tool_input.get("target")
            or ""
        )
        if not raw_path:
            return {"ok": False, "error": "Missing required parameter 'path'"}

        path = _resolve_any_path(ctx, raw_path)

        if ctx.dry_run:
            return {"ok": True, "dry_run": True, "result": f"Would create directory {path}", "path": path}

        try:
            os.makedirs(path, exist_ok=True)
            return {
                "ok": True,
                "result": f"Directory {path} created/exists",
                "path": path,
            }
        except Exception as e:
            return {"ok": False, "error": f"Failed to create directory: {e}", "path": path}


class DeleteDirectoryTool:
    name = "delete_directory"
    description = "Delete a directory. Idempotent: succeeds if directory is already gone."
    capability = ToolCapability.DELETE_DIRECTORY
    risk = ActionRisk.HIGH
    timeout = 15.0
    input_schema: JSON = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "recursive": {"type": "boolean"},
        },
        "required": ["path"],
    }

    def run(self, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        raw_path = str(
            tool_input.get("path")
            or tool_input.get("directory_path")
            or tool_input.get("dir_path")
            or tool_input.get("directory")
            or tool_input.get("target")
            or ""
        )
        if not raw_path:
            return {"ok": False, "error": "Missing required parameter 'path'"}

        path = _resolve_any_path(ctx, raw_path)
        recursive = bool(tool_input.get("recursive", False))

        # Idempotence: If directory is already absent, return success
        if not os.path.exists(path):
            return {
                "ok": True,
                "result": f"Directory {path} does not exist (already deleted)",
                "path": path,
                "already_deleted": True,
            }

        if ctx.dry_run:
            return {"ok": True, "dry_run": True, "result": f"Would delete directory {path}", "path": path}

        try:
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)
            return {
                "ok": True,
                "result": f"Deleted directory {path}",
                "path": path,
                "deleted": True,
            }
        except Exception as e:
            return {"ok": False, "error": f"Failed to delete directory: {e}", "path": path}
