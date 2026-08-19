from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from tools.base import JSON, Tool, ToolContext


@dataclass
class ToolRegistry:
    _tools: Dict[str, Tool]

    def __init__(self) -> None:
        self._tools = {}

    def register(self, tool: Tool) -> None:
        name = getattr(tool, "name", None)
        cls_name = tool.__class__.__name__
        print(f"Registering tool: {name or ''} (type: {cls_name})")

        # 1. Check name
        if not name:
            print("Invalid tool:")
            print(cls_name)
            print("Reason:")
            print("empty name")
            return

        # 2. Check description
        description = getattr(tool, "description", None)
        if not description:
            print("Invalid tool:")
            print(cls_name)
            print("Reason:")
            print("empty description")
            return

        # 3. Check input_schema
        input_schema = getattr(tool, "input_schema", None)
        if input_schema is None:
            print("Invalid tool:")
            print(cls_name)
            print("Reason:")
            print("empty input_schema")
            return

        # 4. Check duplicate
        if name in self._tools:
            print("Invalid tool:")
            print(cls_name)
            print("Reason:")
            print(f"Tool '{name}' is already registered")
            return

        self._tools[name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list(self) -> List[Tool]:
        return list(self._tools.values())

    def describe_for_planner(self) -> str:
        lines: List[str] = []
        for t in self.list():
            lines.append(f"- {t.name}: {t.description}")
        return "\n".join(lines)

    def run(self, name: str, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        tool = self.get(name)
        if not tool:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        try:
            out = tool.run(tool_input, ctx, state)
            if "ok" not in out:
                out = {"ok": True, **out}
            return out
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def build_default_registry() -> ToolRegistry:
    """Create the standard Jarvis tool registry used by CLI, GUI, and voice."""
    from tools.file_manager import ListDirTool, ReadTextFileTool, WriteTextFileTool
    from tools.pc_control import (
        AgentHealthTool,
        CancelDialogTool,
        ClickTool,
        CloseWindowTool,
        ConfirmDialogTool,
        HotkeyTool,
        OpenAppTool,
        OpenSearchResultTool,
        OpenWebsiteTool,
        PressKeyTool,
        ReadScreenTool,
        RefreshAppsTool,
        ScreenshotTool,
        SmartCheckboxTool,
        SmartClickTool,
        SmartWriteTool,
        WriteTextTool,
    )

    reg = ToolRegistry()
    reg.register(AgentHealthTool())
    reg.register(OpenAppTool())
    reg.register(WriteTextTool())
    reg.register(ClickTool())
    reg.register(OpenWebsiteTool())
    reg.register(PressKeyTool())
    reg.register(HotkeyTool())
    reg.register(ScreenshotTool())
    reg.register(ReadScreenTool())
    reg.register(SmartClickTool())
    reg.register(SmartWriteTool())
    reg.register(SmartCheckboxTool())
    reg.register(CloseWindowTool())
    reg.register(ConfirmDialogTool())
    reg.register(CancelDialogTool())
    reg.register(OpenSearchResultTool())
    reg.register(ListDirTool())
    reg.register(ReadTextFileTool())
    reg.register(WriteTextFileTool())
    reg.register(RefreshAppsTool())
    return reg

