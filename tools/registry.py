from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from tools.base import JSON, Tool, ToolContext


@dataclass
class ToolRegistry:
    _tools: Dict[str, Tool]

    def __init__(self) -> None:
        self._tools = {}

    def register(self, tool: Tool) -> None:
        name = getattr(tool, "name", None)
        cls_name = tool.__class__.__name__

        # 1. Check name
        if not name:
            print(f"Invalid tool: {cls_name} - Reason: empty name")
            return

        # 2. Check description
        description = getattr(tool, "description", None)
        if not description:
            print(f"Invalid tool: {cls_name} - Reason: empty description")
            return

        # 3. Check input_schema
        input_schema = getattr(tool, "input_schema", None)
        if input_schema is None:
            print(f"Invalid tool: {cls_name} - Reason: empty input_schema")
            return

        # 4. Check duplicate
        if name in self._tools:
            print(f"Invalid tool: {cls_name} - Reason: Tool '{name}' is already registered")
            return

        # 5. Security metadata enforcement
        from core.security_policy import ActionRisk, SecurityPolicy, ToolCapability
        cap = getattr(tool, "capability", None)
        if not isinstance(cap, (ToolCapability, str)):
            default_cap = SecurityPolicy.DEFAULT_CAPABILITIES.get(name, ToolCapability.SYSTEM_QUERY)
            setattr(tool, "capability", default_cap)

        rsk = getattr(tool, "risk", None)
        if not isinstance(rsk, (ActionRisk, int, str)):
            default_risk = SecurityPolicy.DEFAULT_RISKS.get(name, ActionRisk.LOW)
            setattr(tool, "risk", default_risk)

        tout = getattr(tool, "timeout", None)
        if not isinstance(tout, (int, float)):
            setattr(tool, "timeout", 30.0)

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

    def validate_input(self, name: str, tool_input: JSON) -> Tuple[bool, Optional[str]]:
        """Validate input arguments against tool's input_schema."""
        tool = self.get(name)
        if not tool:
            return False, f"Unknown tool: {name}"
        if not isinstance(tool_input, dict):
            return False, f"Tool input must be a dictionary, got {type(tool_input).__name__}"

        schema = getattr(tool, "input_schema", None) or {}
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in tool_input:
                return False, f"Missing required parameter '{field}' for tool '{name}'"
        return True, None

    def run(self, name: str, tool_input: JSON, ctx: ToolContext, state: Any) -> JSON:
        tool = self.get(name)
        if not tool:
            return {"ok": False, "error": f"Unknown tool: {name}"}

        is_valid, validation_err = self.validate_input(name, tool_input)
        if not is_valid:
            return {"ok": False, "error": f"Invalid arguments for {name}: {validation_err}"}

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

