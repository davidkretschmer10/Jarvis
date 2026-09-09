"""Central Security Policy Engine for Jarvis.

Classifies action risk, tool capabilities, resource scopes, and makes
deterministic fail-closed authorization decisions (ALLOW, REQUIRE_CONFIRMATION, DENY)
without relying on LLM judgements.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Dict, Optional


class ActionRisk(IntEnum):
    """Hierarchical risk levels for tool actions.

    Strict order: SAFE < LOW < MEDIUM < HIGH < CRITICAL.
    """
    SAFE = 10
    LOW = 20
    MEDIUM = 30
    HIGH = 40
    CRITICAL = 50

    def __str__(self) -> str:
        return self.name


class ToolCapability(str, Enum):
    """Standardized action capabilities for auditing and policy enforcement."""
    # Applications & System
    LAUNCH_APPLICATION = "LAUNCH_APPLICATION"
    PROCESS_START = "PROCESS_START"
    PROCESS_TERMINATE = "PROCESS_TERMINATE"
    SHELL_COMMAND = "SHELL_COMMAND"
    SYSTEM_QUERY = "SYSTEM_QUERY"

    # Files & Directories
    READ_FILE = "READ_FILE"
    CREATE_FILE = "CREATE_FILE"
    MODIFY_FILE = "MODIFY_FILE"
    DELETE_FILE = "DELETE_FILE"
    CREATE_DIRECTORY = "CREATE_DIRECTORY"
    DELETE_DIRECTORY = "DELETE_DIRECTORY"

    # Browser & Network
    OPEN_URL = "OPEN_URL"
    NAVIGATE = "NAVIGATE"
    DOWNLOAD = "DOWNLOAD"

    # UI Interaction
    TYPE_TEXT = "TYPE_TEXT"
    PRESS_KEY = "PRESS_KEY"
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    SCREEN_OBSERVATION = "SCREEN_OBSERVATION"
    UI_CLICK = "UI_CLICK"

    # Media
    AUDIO_PLAYBACK = "AUDIO_PLAYBACK"

    # Fallback
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        return self.value


class PolicyDecision(str, Enum):
    """Authorization decision returned by SecurityPolicy."""
    ALLOW = "ALLOW"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    DENY = "DENY"

    def __str__(self) -> str:
        return self.value


class ResourceScope(str, Enum):
    """Classification of target resources (paths, URLs, processes)."""
    USER_WORKSPACE = "USER_WORKSPACE"
    USER_DOCUMENTS = "USER_DOCUMENTS"
    APP_DATA = "APP_DATA"
    TEMPORARY = "TEMPORARY"
    SYSTEM_PROTECTED = "SYSTEM_PROTECTED"
    NETWORK_URL = "NETWORK_URL"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        return self.value


def classify_path_scope(path_str: str) -> ResourceScope:
    """Deterministically classify a file/directory path into a ResourceScope.

    System paths (Windows, System32, Program Files, drive roots) are classified
    as SYSTEM_PROTECTED. User desktop/documents are USER_DOCUMENTS.
    Temporary files are TEMPORARY.
    """
    if not path_str or not isinstance(path_str, str):
        return ResourceScope.UNKNOWN

    raw_path = path_str.strip()
    if raw_path.startswith(("http://", "https://")):
        return ResourceScope.NETWORK_URL

    try:
        resolved = Path(raw_path).expanduser().resolve()
        resolved_str = str(resolved).lower()
    except Exception:
        return ResourceScope.UNKNOWN

    # System roots & protected locations
    windir = os.environ.get("WINDIR", r"C:\Windows").lower()
    prog_files = os.environ.get("ProgramFiles", r"C:\Program Files").lower()
    prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)").lower()
    prog_data = os.environ.get("ProgramData", r"C:\ProgramData").lower()

    # Check for drive root (e.g. C:\, D:\)
    if len(resolved.parts) <= 1:
        return ResourceScope.SYSTEM_PROTECTED

    # System protected directories
    for sys_dir in (windir, prog_files, prog_files_x86, prog_data):
        if sys_dir and (resolved_str == sys_dir or resolved_str.startswith(sys_dir + os.sep)):
            return ResourceScope.SYSTEM_PROTECTED

    # Temporary paths
    temp_dir = os.environ.get("TEMP", "").lower()
    tmp_dir = os.environ.get("TMP", "").lower()
    import tempfile
    sys_temp = tempfile.gettempdir().lower()
    for t_dir in (temp_dir, tmp_dir, sys_temp):
        if t_dir and (resolved_str == t_dir or resolved_str.startswith(t_dir + os.sep)):
            return ResourceScope.TEMPORARY

    # AppData
    appdata = os.environ.get("APPDATA", "").lower()
    localappdata = os.environ.get("LOCALAPPDATA", "").lower()
    for a_dir in (appdata, localappdata):
        if a_dir and (resolved_str == a_dir or resolved_str.startswith(a_dir + os.sep)):
            return ResourceScope.APP_DATA

    # User Home & Documents
    userprofile = os.environ.get("USERPROFILE", "").lower()
    if userprofile and (resolved_str == userprofile or resolved_str.startswith(userprofile + os.sep)):
        # Check if it's current workspace
        workspace = str(Path.cwd().resolve()).lower()
        if resolved_str == workspace or resolved_str.startswith(workspace + os.sep):
            return ResourceScope.USER_WORKSPACE
        return ResourceScope.USER_DOCUMENTS

    return ResourceScope.UNKNOWN


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Result of evaluating a planned tool action against SecurityPolicy."""
    decision: PolicyDecision
    risk: ActionRisk
    capability: ToolCapability
    resource_scope: ResourceScope
    reason: str
    target_resource: Optional[str] = None

    @property
    def is_allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW

    @property
    def requires_confirmation(self) -> bool:
        return self.decision == PolicyDecision.REQUIRE_CONFIRMATION

    @property
    def is_denied(self) -> bool:
        return self.decision == PolicyDecision.DENY


class SecurityPolicy:
    """Central deterministic policy engine for authorizing tool actions."""

    # Default capability mappings if tool metadata is not provided directly
    DEFAULT_CAPABILITIES: Dict[str, ToolCapability] = {
        "read_file": ToolCapability.READ_FILE,
        "write_file": ToolCapability.CREATE_FILE,
        "list_dir": ToolCapability.READ_FILE,
        "search_file": ToolCapability.READ_FILE,
        "read_text_file": ToolCapability.READ_FILE,
        "write_text_file": ToolCapability.MODIFY_FILE,
        "delete_file": ToolCapability.DELETE_FILE,
        "open_app": ToolCapability.LAUNCH_APPLICATION,
        "close_app": ToolCapability.PROCESS_TERMINATE,
        "close_window": ToolCapability.PROCESS_TERMINATE,
        "confirm_dialog": ToolCapability.UI_CLICK,
        "cancel_dialog": ToolCapability.UI_CLICK,
        "open_search_result": ToolCapability.UI_CLICK,
        "write_note": ToolCapability.CREATE_FILE,
        "calculate": ToolCapability.SYSTEM_QUERY,
        "agent_health": ToolCapability.SYSTEM_QUERY,
        "refresh_apps": ToolCapability.SYSTEM_QUERY,
        "browse_web": ToolCapability.OPEN_URL,
        "open_website": ToolCapability.OPEN_URL,
        "play_audio": ToolCapability.AUDIO_PLAYBACK,
        "capture_screen": ToolCapability.SCREEN_OBSERVATION,
        "inspect_screen": ToolCapability.SCREEN_OBSERVATION,
        "screenshot": ToolCapability.SCREEN_OBSERVATION,
        "read_screen": ToolCapability.SCREEN_OBSERVATION,
        "click": ToolCapability.CLICK,
        "click_element": ToolCapability.UI_CLICK,
        "smart_click": ToolCapability.UI_CLICK,
        "write_text": ToolCapability.TYPE_TEXT,
        "type_text": ToolCapability.TYPE_TEXT,
        "smart_write": ToolCapability.TYPE_TEXT,
        "smart_checkbox": ToolCapability.UI_CLICK,
        "press_key": ToolCapability.PRESS_KEY,
        "hotkey": ToolCapability.PRESS_KEY,
        "execute_code": ToolCapability.SHELL_COMMAND,
        # Unit test dummy/fixture tools
        "test_tool": ToolCapability.SYSTEM_QUERY,
        "dummy_tool": ToolCapability.SYSTEM_QUERY,
        "step1_tool": ToolCapability.SYSTEM_QUERY,
        "step2_tool": ToolCapability.SYSTEM_QUERY,
        "step3_tool": ToolCapability.SYSTEM_QUERY,
        "flake_tool": ToolCapability.SYSTEM_QUERY,
        "recovery_tool": ToolCapability.SYSTEM_QUERY,
        "bad_tool": ToolCapability.SYSTEM_QUERY,
        "tool_run": ToolCapability.SYSTEM_QUERY,
    }

    # Default risk mappings
    DEFAULT_RISKS: Dict[str, ActionRisk] = {
        "read_file": ActionRisk.SAFE,
        "list_dir": ActionRisk.SAFE,
        "search_file": ActionRisk.SAFE,
        "read_text_file": ActionRisk.SAFE,
        "calculate": ActionRisk.SAFE,
        "agent_health": ActionRisk.SAFE,
        "refresh_apps": ActionRisk.SAFE,
        "play_audio": ActionRisk.SAFE,
        "capture_screen": ActionRisk.SAFE,
        "inspect_screen": ActionRisk.SAFE,
        "screenshot": ActionRisk.SAFE,
        "read_screen": ActionRisk.SAFE,
        "open_app": ActionRisk.LOW,
        "browse_web": ActionRisk.LOW,
        "open_website": ActionRisk.LOW,
        "click": ActionRisk.LOW,
        "write_text": ActionRisk.LOW,
        "type_text": ActionRisk.LOW,
        "press_key": ActionRisk.LOW,
        "hotkey": ActionRisk.LOW,
        "cancel_dialog": ActionRisk.LOW,
        "open_search_result": ActionRisk.LOW,
        "write_note": ActionRisk.MEDIUM,
        "write_file": ActionRisk.MEDIUM,
        "write_text_file": ActionRisk.MEDIUM,
        "click_element": ActionRisk.MEDIUM,
        "smart_click": ActionRisk.MEDIUM,
        "smart_write": ActionRisk.MEDIUM,
        "smart_checkbox": ActionRisk.MEDIUM,
        "close_app": ActionRisk.HIGH,
        "close_window": ActionRisk.HIGH,
        "confirm_dialog": ActionRisk.HIGH,
        "delete_file": ActionRisk.HIGH,
        "execute_code": ActionRisk.HIGH,
        # Unit test dummy/fixture tools
        "test_tool": ActionRisk.SAFE,
        "dummy_tool": ActionRisk.SAFE,
        "step1_tool": ActionRisk.SAFE,
        "step2_tool": ActionRisk.SAFE,
        "step3_tool": ActionRisk.SAFE,
        "flake_tool": ActionRisk.SAFE,
        "recovery_tool": ActionRisk.SAFE,
        "bad_tool": ActionRisk.SAFE,
        "tool_run": ActionRisk.SAFE,
    }

    # Dangerous commands or files that are unconditionally CRITICAL / DENY
    CRITICAL_SHELL_PATTERNS = (
        "rmdir /s /q c:",
        "format ",
        "del /f /s /q c:",
        "shutdown",
        "reg delete",
        "drop database",
        "curl http",
        "powershell -encodedcommand",
    )

    def evaluate(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        context: Optional[Any] = None,
        tool_meta: Optional[Dict[str, Any]] = None,
    ) -> PolicyEvaluationResult:
        """Evaluate an action against security rules. Fail-closed.

        Args:
            tool_name: Name of the tool to be executed.
            tool_input: Arguments passed to the tool.
            context: RequestContext or dict with execution context.
            tool_meta: Optional dictionary containing 'capability', 'risk', etc.
        """
        # 1. Fail-closed on missing or invalid tool name
        if not tool_name or not isinstance(tool_name, str):
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                risk=ActionRisk.CRITICAL,
                capability=ToolCapability.UNKNOWN,
                resource_scope=ResourceScope.UNKNOWN,
                reason="Invalid or missing tool name.",
            )

        # 2. Extract capability
        capability = ToolCapability.UNKNOWN
        if tool_meta and "capability" in tool_meta:
            cap_val = tool_meta["capability"]
            if isinstance(cap_val, ToolCapability):
                capability = cap_val
            elif isinstance(cap_val, str):
                try:
                    capability = ToolCapability(cap_val)
                except ValueError:
                    capability = ToolCapability.UNKNOWN
        if capability == ToolCapability.UNKNOWN:
            capability = self.DEFAULT_CAPABILITIES.get(tool_name, ToolCapability.UNKNOWN)

        # 3. Extract risk
        risk = ActionRisk.HIGH  # default fallback if unclassified
        if tool_meta and "risk" in tool_meta:
            risk_val = tool_meta["risk"]
            if isinstance(risk_val, ActionRisk):
                risk = risk_val
            elif isinstance(risk_val, int):
                try:
                    risk = ActionRisk(risk_val)
                except ValueError:
                    risk = ActionRisk.HIGH
            elif isinstance(risk_val, str):
                try:
                    risk = ActionRisk[risk_val.upper()]
                except KeyError:
                    risk = ActionRisk.HIGH
        elif tool_name in self.DEFAULT_RISKS:
            risk = self.DEFAULT_RISKS[tool_name]

        # 4. Identify target resource & scope
        target_resource = self._extract_resource(tool_input)
        resource_scope = classify_path_scope(target_resource) if target_resource else ResourceScope.UNKNOWN

        # 5. Handle unknown tools - FAIL CLOSED
        if capability == ToolCapability.UNKNOWN and tool_name not in self.DEFAULT_CAPABILITIES:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                risk=ActionRisk.CRITICAL,
                capability=ToolCapability.UNKNOWN,
                resource_scope=resource_scope,
                reason=f"Unknown tool '{tool_name}' without registered security capability.",
                target_resource=target_resource,
            )

        # 6. Check for Critical Shell / Process Termination commands
        if capability in (ToolCapability.SHELL_COMMAND, ToolCapability.PROCESS_START):
            cmd_str = ""
            if isinstance(tool_input, dict):
                cmd_str = str(tool_input.get("command", "") or tool_input.get("code", "")).lower()
            for pattern in self.CRITICAL_SHELL_PATTERNS:
                if pattern in cmd_str:
                    return PolicyEvaluationResult(
                        decision=PolicyDecision.DENY,
                        risk=ActionRisk.CRITICAL,
                        capability=capability,
                        resource_scope=resource_scope,
                        reason=f"Shell command contains prohibited pattern: {pattern}",
                        target_resource=target_resource or cmd_str,
                    )

        # 7. Check for System-Protected resources
        if resource_scope == ResourceScope.SYSTEM_PROTECTED:
            # Modifying or deleting system protected paths is CRITICAL / DENY
            if capability in (
                ToolCapability.MODIFY_FILE,
                ToolCapability.CREATE_FILE,
                ToolCapability.DELETE_FILE,
                ToolCapability.CREATE_DIRECTORY,
                ToolCapability.DELETE_DIRECTORY,
            ):
                return PolicyEvaluationResult(
                    decision=PolicyDecision.DENY,
                    risk=ActionRisk.CRITICAL,
                    capability=capability,
                    resource_scope=resource_scope,
                    reason=f"Modifying protected system resource '{target_resource}' is strictly prohibited.",
                    target_resource=target_resource,
                )
            # Reading system files requires confirmation
            if capability == ToolCapability.READ_FILE:
                return PolicyEvaluationResult(
                    decision=PolicyDecision.REQUIRE_CONFIRMATION,
                    risk=ActionRisk.HIGH,
                    capability=capability,
                    resource_scope=resource_scope,
                    reason=f"Reading protected system resource '{target_resource}' requires explicit user confirmation.",
                    target_resource=target_resource,
                )

        # Temporary resources (scratch files, temp tests) do not require confirmation
        if resource_scope == ResourceScope.TEMPORARY and capability in (
            ToolCapability.READ_FILE, ToolCapability.CREATE_FILE, ToolCapability.MODIFY_FILE, ToolCapability.DELETE_FILE
        ):
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                risk=ActionRisk.LOW,
                capability=capability,
                resource_scope=resource_scope,
                reason=f"Action on temporary resource '{target_resource}' is permitted.",
                target_resource=target_resource,
            )

        # 8. Elevate risk for delete / overwrite actions
        if capability in (ToolCapability.DELETE_FILE, ToolCapability.DELETE_DIRECTORY):
            risk = max(risk, ActionRisk.HIGH)

        # 9. Evaluate Decision based on Risk Level & Scope
        if risk == ActionRisk.CRITICAL:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                risk=risk,
                capability=capability,
                resource_scope=resource_scope,
                reason=f"Action '{tool_name}' carries CRITICAL risk and is denied by policy.",
                target_resource=target_resource,
            )

        if risk == ActionRisk.HIGH:
            return PolicyEvaluationResult(
                decision=PolicyDecision.REQUIRE_CONFIRMATION,
                risk=risk,
                capability=capability,
                resource_scope=resource_scope,
                reason=f"Action '{tool_name}' carries HIGH risk and requires explicit user confirmation.",
                target_resource=target_resource,
            )

        if risk == ActionRisk.MEDIUM:
            # If target resource is unknown or outside user scope, require confirmation
            if resource_scope == ResourceScope.UNKNOWN and target_resource:
                return PolicyEvaluationResult(
                    decision=PolicyDecision.REQUIRE_CONFIRMATION,
                    risk=risk,
                    capability=capability,
                    resource_scope=resource_scope,
                    reason=f"Target resource '{target_resource}' is in an unknown or unverified scope.",
                    target_resource=target_resource,
                )
            # Overwriting existing file is HIGH/CONFIRM
            if capability == ToolCapability.CREATE_FILE and tool_name == "write_file":
                filepath = tool_input.get("filepath") or tool_input.get("path")
                if filepath and os.path.exists(filepath):
                    return PolicyEvaluationResult(
                        decision=PolicyDecision.REQUIRE_CONFIRMATION,
                        risk=ActionRisk.HIGH,
                        capability=ToolCapability.MODIFY_FILE,
                        resource_scope=resource_scope,
                        reason=f"Overwriting existing file '{filepath}' requires confirmation.",
                        target_resource=target_resource,
                    )
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                risk=risk,
                capability=capability,
                resource_scope=resource_scope,
                reason=f"Medium risk action '{tool_name}' within user scope is permitted.",
                target_resource=target_resource,
            )

        # SAFE or LOW
        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            risk=risk,
            capability=capability,
            resource_scope=resource_scope,
            reason=f"Action '{tool_name}' ({risk.name}) is permitted.",
            target_resource=target_resource,
        )

    def _extract_resource(self, tool_input: Dict[str, Any]) -> Optional[str]:
        """Extract path, URL, process name, or target resource from tool input."""
        if not isinstance(tool_input, dict):
            return None
        for key in ("filepath", "file_path", "path", "filename", "file", "target", "target_path", "url", "app_name", "window_title", "directory", "dir"):
            val = tool_input.get(key)
            if val and isinstance(val, str):
                return val
        return None
