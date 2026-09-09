# -*- coding: utf-8 -*-
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.observation import Observation, ObservationType


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class VerificationResult:
    """
    Structured result of an independent verification of an action.
    """

    status: VerificationStatus
    verifier: str
    expected: str = ""
    observed: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    timestamp: float = field(default_factory=time.time)

    def is_verified(self) -> bool:
        return self.status == VerificationStatus.VERIFIED

    def is_failed(self) -> bool:
        return self.status == VerificationStatus.FAILED

    def is_unknown(self) -> bool:
        return self.status == VerificationStatus.UNKNOWN

    def is_not_applicable(self) -> bool:
        return self.status == VerificationStatus.NOT_APPLICABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, VerificationStatus) else str(self.status),
            "verifier": self.verifier,
            "expected": self.expected,
            "observed": self.observed,
            "evidence": self.evidence,
            "message": self.message,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Windows inspection helpers (Read-only, standard library only)
# ---------------------------------------------------------------------------

def _get_running_processes_windows() -> List[str]:
    """Return list of lowercase process image names currently running on Windows."""
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        proc = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=3.0,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if proc.returncode == 0:
            lines = proc.stdout.strip().splitlines()
            names = []
            for line in lines:
                parts = line.split(",")
                if parts:
                    clean_name = parts[0].strip(' "').lower()
                    if clean_name:
                        names.append(clean_name)
            return names
    except Exception:
        pass
    return []


def _get_visible_window_titles_windows() -> List[str]:
    """Return list of visible window titles using ctypes EnumWindows (Windows only)."""
    titles: List[str] = []
    if os.name != "nt":
        return titles

    try:
        user32 = ctypes.windll.user32

        def enum_windows_proc(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.strip()
                    if title:
                        titles.append(title)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
    except Exception:
        pass
    return titles


# ---------------------------------------------------------------------------
# Verifier Base Class
# ---------------------------------------------------------------------------

class BaseVerifier:
    """
    Base class for all verifiers.
    Verifiers are strictly READ-ONLY. They observe, never act or mutate state.
    """

    is_read_only: bool = True

    def can_verify(self, step: Dict[str, Any], tool_output: Dict[str, Any]) -> bool:
        raise NotImplementedError

    def verify(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Application Verifier
# ---------------------------------------------------------------------------

class ApplicationVerifier(BaseVerifier):
    """
    Verifies application launch / termination.
    Checks process table and window titles deterministically.
    """

    APP_PROCESS_MAP = {
        "notepad": ["notepad.exe"],
        "calculator": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
        "calc": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
        "chrome": ["chrome.exe"],
        "edge": ["msedge.exe"],
        "msedge": ["msedge.exe"],
        "firefox": ["firefox.exe"],
        "explorer": ["explorer.exe"],
        "cmd": ["cmd.exe"],
        "powershell": ["powershell.exe", "pwsh.exe"],
        "terminal": ["windowsterminal.exe", "wt.exe"],
    }

    def can_verify(self, step: Dict[str, Any], tool_output: Dict[str, Any]) -> bool:
        tool = (step.get("tool") or "").lower()
        action = (step.get("action") or "").lower()
        return tool in {"open_app", "launch_app", "app_launcher", "close_app", "kill_process"} or "app" in tool or "app" in action

    def verify(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        args = step.get("args") or {}
        app_target = (
            args.get("app_name")
            or args.get("name")
            or args.get("app")
            or args.get("process_name")
            or step.get("target")
            or ""
        ).strip().lower()

        # Is this a close/kill action?
        tool = (step.get("tool") or "").lower()
        is_closing = "close" in tool or "kill" in tool or "terminate" in tool

        expected_procs = self.APP_PROCESS_MAP.get(app_target, [])
        if not expected_procs:
            # If target has .exe or is raw name
            if app_target.endswith(".exe"):
                expected_procs = [app_target]
            elif app_target:
                expected_procs = [f"{app_target}.exe", app_target]

        if not expected_procs:
            return VerificationResult(
                status=VerificationStatus.UNKNOWN,
                verifier="ApplicationVerifier",
                expected=f"App '{app_target}' process running",
                observed="Unknown application target name",
                evidence={"app_target": app_target},
                message=f"Cannot identify expected process name for '{app_target}'",
            )

        # Allow slight delay for app process to register if just launched
        active_processes = _get_running_processes_windows()
        visible_windows = _get_visible_window_titles_windows()

        found_proc = None
        for p in expected_procs:
            if p in active_processes:
                found_proc = p
                break

        found_win = None
        for w in visible_windows:
            if app_target in w.lower():
                found_win = w
                break

        if is_closing:
            # Expect process not to exist
            if not found_proc and not found_win:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="ApplicationVerifier",
                    expected=f"Process {expected_procs} terminated",
                    observed="Process and window not detected",
                    evidence={"expected_procs": expected_procs, "terminated": True},
                    message=f"Application '{app_target}' successfully terminated",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="ApplicationVerifier",
                    expected=f"Process {expected_procs} terminated",
                    observed=f"Process still active ({found_proc or found_win})",
                    evidence={"active_proc": found_proc, "active_window": found_win},
                    message=f"Application '{app_target}' is still running",
                )
        else:
            # Expect process or window to exist
            if found_proc or found_win:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="ApplicationVerifier",
                    expected=f"Process {expected_procs} or window '{app_target}' active",
                    observed=f"Detected process={found_proc}, window={found_win}",
                    evidence={"found_proc": found_proc, "found_win": found_win},
                    message=f"Application '{app_target}' verified active",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="ApplicationVerifier",
                    expected=f"Process {expected_procs} running",
                    observed="Process not found in system process table",
                    evidence={"checked_procs": expected_procs, "active_sample_count": len(active_processes)},
                    message=f"Application '{app_target}' process was not found after execution",
                )


# ---------------------------------------------------------------------------
# File Verifier
# ---------------------------------------------------------------------------

class FileVerifier(BaseVerifier):
    """
    Verifies file creation, modification, and deletion deterministically via filesystem checks.
    """

    def can_verify(self, step: Dict[str, Any], tool_output: Dict[str, Any]) -> bool:
        tool = (step.get("tool") or "").lower()
        return tool in {
            "write_file",
            "write_text_file",
            "create_file",
            "copy_file",
            "move_file",
            "delete_file",
            "remove_file",
            "append_file",
            "modify_file",
        } or "file" in tool

    def verify(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        args = step.get("args") or step.get("input") or {}
        tool = (step.get("tool") or "").lower()

        # Handle Copy File verification
        if tool in {"copy_file", "copy"}:
            src = args.get("source") or args.get("src") or ""
            dst = args.get("destination") or args.get("dst") or ""
            if not src or not dst:
                return VerificationResult(
                    status=VerificationStatus.UNKNOWN,
                    verifier="FileVerifier",
                    expected="Source and destination file paths",
                    observed=f"src='{src}', dst='{dst}'",
                    message="Cannot verify copy without source and destination paths",
                )
            src_exists = os.path.isfile(src)
            dst_exists = os.path.isfile(dst)
            if src_exists and dst_exists and os.path.getsize(src) == os.path.getsize(dst):
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="FileVerifier",
                    expected=f"Destination '{dst}' exists with size matching source '{src}'",
                    observed=f"Source ({os.path.getsize(src)} bytes) and destination match",
                    evidence={"source": src, "destination": dst, "size": os.path.getsize(dst)},
                    message=f"File successfully copied from '{src}' to '{dst}'",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="FileVerifier",
                    expected=f"Destination '{dst}' created with matching size",
                    observed=f"src_exists={src_exists}, dst_exists={dst_exists}",
                    evidence={"src_exists": src_exists, "dst_exists": dst_exists},
                    message=f"Copy verification failed: source exists={src_exists}, destination exists={dst_exists}",
                )

        # Handle Move File verification
        if tool in {"move_file", "move"}:
            src = args.get("source") or args.get("src") or ""
            dst = args.get("destination") or args.get("dst") or ""
            if not src or not dst:
                return VerificationResult(
                    status=VerificationStatus.UNKNOWN,
                    verifier="FileVerifier",
                    expected="Source and destination file paths",
                    observed=f"src='{src}', dst='{dst}'",
                    message="Cannot verify move without source and destination paths",
                )
            src_exists = os.path.exists(src)
            dst_exists = os.path.exists(dst)
            if not src_exists and dst_exists:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="FileVerifier",
                    expected=f"Source '{src}' absent and destination '{dst}' present",
                    observed="Source gone, destination exists",
                    evidence={"source": src, "destination": dst},
                    message=f"File successfully moved from '{src}' to '{dst}'",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="FileVerifier",
                    expected=f"Source '{src}' absent and destination '{dst}' present",
                    observed=f"src_still_exists={src_exists}, dst_exists={dst_exists}",
                    evidence={"src_still_exists": src_exists, "dst_exists": dst_exists},
                    message=f"Move verification failed: source still exists={src_exists}, destination exists={dst_exists}",
                )

        file_path = (
            args.get("file_path")
            or args.get("path")
            or args.get("filepath")
            or args.get("target")
            or ""
        )

        if not file_path:
            return VerificationResult(
                status=VerificationStatus.UNKNOWN,
                verifier="FileVerifier",
                expected="Target file path",
                observed="No file path found in step arguments",
                evidence={},
                message="Cannot verify file operation without path argument",
            )

        # Read-only tools (like read_file) shouldn't be verified as mutating
        if tool in {"read_file", "view_file", "get_file_info"}:
            exists = os.path.exists(file_path)
            return VerificationResult(
                status=VerificationStatus.NOT_APPLICABLE if exists else VerificationStatus.FAILED,
                verifier="FileVerifier",
                expected=f"File {file_path} exists to be read",
                observed=f"File exists={exists}",
                evidence={"path": file_path, "exists": exists},
                message=f"File read target exists={exists}",
            )

        is_delete = "delete" in tool or "remove" in tool
        exists = os.path.exists(file_path)

        if is_delete:
            if not exists:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="FileVerifier",
                    expected=f"File {file_path} does not exist",
                    observed="Path does not exist",
                    evidence={"path": file_path, "exists": False},
                    message=f"File '{file_path}' confirmed deleted",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="FileVerifier",
                    expected=f"File {file_path} deleted",
                    observed="File still exists on disk",
                    evidence={"path": file_path, "exists": True},
                    message=f"File '{file_path}' still exists after delete operation",
                )
        else:
            # Create / write / append
            if exists and os.path.isfile(file_path):
                size = os.path.getsize(file_path)
                expected_content = args.get("content") or args.get("text")
                content_matched = True
                if expected_content is not None and isinstance(expected_content, str):
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            actual_content = f.read()
                        content_matched = expected_content in actual_content
                    except Exception:
                        content_matched = True  # Can't read, but file exists

                if not content_matched:
                    return VerificationResult(
                        status=VerificationStatus.FAILED,
                        verifier="FileVerifier",
                        expected="Expected content present in file",
                        observed="File exists but expected content was missing",
                        evidence={"path": file_path, "size": size, "content_match": False},
                        message=f"File exists but does not contain expected content",
                    )

                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="FileVerifier",
                    expected=f"File {file_path} exists and is written",
                    observed=f"File exists with size={size} bytes",
                    evidence={"path": file_path, "size": size, "exists": True},
                    message=f"File '{file_path}' verified on disk ({size} bytes)",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="FileVerifier",
                    expected=f"File {file_path} created/written",
                    observed=f"File not found on disk (exists={exists})",
                    evidence={"path": file_path, "exists": exists},
                    message=f"File '{file_path}' was not created or is not a regular file",
                )


# ---------------------------------------------------------------------------
# Directory Verifier
# ---------------------------------------------------------------------------

class DirectoryVerifier(BaseVerifier):
    """
    Verifies directory creation and deletion deterministically.
    """

    def can_verify(self, step: Dict[str, Any], tool_output: Dict[str, Any]) -> bool:
        tool = (step.get("tool") or "").lower()
        return tool in {
            "make_directory",
            "create_dir",
            "create_directory",
            "delete_directory",
            "remove_dir",
            "remove_directory",
        } or "dir" in tool or "directory" in tool

    def verify(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        args = step.get("args") or {}
        tool = (step.get("tool") or "").lower()
        dir_path = (
            args.get("directory_path")
            or args.get("dir_path")
            or args.get("path")
            or args.get("target")
            or ""
        )

        if not dir_path:
            return VerificationResult(
                status=VerificationStatus.UNKNOWN,
                verifier="DirectoryVerifier",
                expected="Target directory path",
                observed="No directory path in step arguments",
                evidence={},
                message="Cannot verify directory operation without path argument",
            )

        if tool in {"list_directory", "list_dir"}:
            exists = os.path.isdir(dir_path)
            return VerificationResult(
                status=VerificationStatus.NOT_APPLICABLE if exists else VerificationStatus.FAILED,
                verifier="DirectoryVerifier",
                expected=f"Directory {dir_path} exists",
                observed=f"Exists={exists}",
                evidence={"path": dir_path, "exists": exists},
                message=f"Directory read target exists={exists}",
            )

        is_delete = "delete" in tool or "remove" in tool
        exists = os.path.exists(dir_path)

        if is_delete:
            if not exists:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="DirectoryVerifier",
                    expected=f"Directory {dir_path} deleted",
                    observed="Directory does not exist",
                    evidence={"path": dir_path, "exists": False},
                    message=f"Directory '{dir_path}' confirmed deleted",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="DirectoryVerifier",
                    expected=f"Directory {dir_path} deleted",
                    observed="Directory still exists",
                    evidence={"path": dir_path, "exists": True},
                    message=f"Directory '{dir_path}' still exists after deletion",
                )
        else:
            if exists and os.path.isdir(dir_path):
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="DirectoryVerifier",
                    expected=f"Directory {dir_path} created",
                    observed="Directory confirmed existing",
                    evidence={"path": dir_path, "exists": True, "is_dir": True},
                    message=f"Directory '{dir_path}' verified existing",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="DirectoryVerifier",
                    expected=f"Directory {dir_path} created",
                    observed=f"Directory not found on disk (exists={exists})",
                    evidence={"path": dir_path, "exists": exists},
                    message=f"Directory '{dir_path}' was not found after creation",
                )


# ---------------------------------------------------------------------------
# Browser Verifier
# ---------------------------------------------------------------------------

class BrowserVerifier(BaseVerifier):
    """
    Verifies browser launches or state where deterministic checks are possible.
    """

    BROWSER_PROCS = ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]

    def can_verify(self, step: Dict[str, Any], tool_output: Dict[str, Any]) -> bool:
        tool = (step.get("tool") or "").lower()
        return "browser" in tool or tool in {"open_url", "search_web", "web_search"}

    def verify(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        tool = (step.get("tool") or "").lower()
        if tool in {"search_web", "web_search", "fetch_url"}:
            # Informational / query tool
            return VerificationResult(
                status=VerificationStatus.NOT_APPLICABLE,
                verifier="BrowserVerifier",
                expected="Web data retrieved",
                observed="Query executed",
                evidence={"tool": tool},
                message="Read-only web request",
            )

        active_procs = _get_running_processes_windows()
        found_browsers = [bp for bp in self.BROWSER_PROCS if bp in active_procs]

        if found_browsers:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                verifier="BrowserVerifier",
                expected="Browser process running",
                observed=f"Active browsers: {found_browsers}",
                evidence={"browsers": found_browsers},
                message=f"Browser verified active ({', '.join(found_browsers)})",
            )
        else:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                verifier="BrowserVerifier",
                expected="Browser process running",
                observed="No recognized browser process running",
                evidence={"checked": self.BROWSER_PROCS},
                message="Browser process was not detected after navigation command",
            )


# ---------------------------------------------------------------------------
# UI Interaction Verifier (Mouse / Keyboard)
# ---------------------------------------------------------------------------

class UIInteractionVerifier(BaseVerifier):
    """
    Verifies mouse and keyboard actions.
    CRITICAL RULE: UI interactions without a concrete, validated delta
    must return UNKNOWN, NEVER automatically VERIFIED.
    """

    def can_verify(self, step: Dict[str, Any], tool_output: Dict[str, Any]) -> bool:
        tool = (step.get("tool") or "").lower()
        return tool in {
            "mouse_click",
            "click",
            "double_click",
            "type_text",
            "type",
            "press_key",
            "hotkey",
            "gui_click",
        } or "mouse" in tool or "keyboard" in tool

    def verify(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        tool = (step.get("tool") or "").lower()
        # If the tool explicitly observed an element or state change via vision/OCR:
        observed_delta = tool_output.get("observed_delta") or tool_output.get("verified")
        if observed_delta is True:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                verifier="UIInteractionVerifier",
                expected="UI state delta observed",
                observed=str(tool_output.get("delta_evidence", "Delta confirmed")),
                evidence=tool_output,
                message="UI interaction verified via observed delta",
            )

        # In the absence of an explicit verifiable delta, this CANNOT be declared VERIFIED.
        return VerificationResult(
            status=VerificationStatus.UNKNOWN,
            verifier="UIInteractionVerifier",
            expected=f"Concrete UI delta after {tool}",
            observed="Tool execution reported success, but UI change cannot be deterministically proven",
            evidence={"tool_reported_ok": tool_output.get("ok", False)},
            message=f"Action '{tool}' executed, but resulting state is UNKNOWN (no verifiable UI delta)",
        )


# ---------------------------------------------------------------------------
# Process Verifier
# ---------------------------------------------------------------------------

class ProcessVerifier(BaseVerifier):
    """
    Verifies process existence, start, and termination deterministically.
    """

    def can_verify(self, step: Dict[str, Any], tool_output: Dict[str, Any]) -> bool:
        tool = (step.get("tool") or "").lower()
        return tool in {
            "process_exists",
            "terminate_process",
            "kill_process",
            "get_process_info",
        }

    def verify(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        args = step.get("args") or step.get("input") or {}
        tool = (step.get("tool") or "").lower()
        target = str(args.get("process_name") or args.get("name") or "").strip().lower()
        pid = args.get("pid")

        active_procs = _get_running_processes_windows()
        is_terminate = "terminate" in tool or "kill" in tool

        # Helper to check if PID is active
        def _check_pid_active(p_val: Any) -> bool:
            if p_val is None:
                return False
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                STILL_ACTIVE = 259
                h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(p_val))
                if h_proc:
                    exit_code = ctypes.c_ulong()
                    kernel32.GetExitCodeProcess(h_proc, ctypes.byref(exit_code))
                    kernel32.CloseHandle(h_proc)
                    return exit_code.value == STILL_ACTIVE
            except Exception:
                pass
            try:
                from tools.pc_control import _query_processes_windows
                return any(p.get("pid") == int(p_val) for p in _query_processes_windows())
            except Exception:
                return False

        if is_terminate:
            target_running = False
            if pid is not None:
                target_running = _check_pid_active(pid)
            elif target:
                clean_target = target if target.endswith(".exe") else f"{target}.exe"
                if clean_target in active_procs or target in active_procs:
                    target_running = True

            if not target_running:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="ProcessVerifier",
                    expected=f"Process '{target or pid}' terminated and absent",
                    observed="Process not found in system process table",
                    evidence={"target": target or pid, "running": False},
                    message=f"Process '{target or pid}' verified terminated",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="ProcessVerifier",
                    expected=f"Process '{target or pid}' terminated",
                    observed="Process is still present in system process table",
                    evidence={"target": target or pid, "running": True},
                    message=f"Process '{target or pid}' is still running after termination",
                )

        # For process_exists or get_process_info:
        if pid is not None:
            actually_exists = _check_pid_active(pid)
        elif target:
            clean_target = target if target.endswith(".exe") else f"{target}.exe"
            actually_exists = (bool(clean_target) and clean_target in active_procs) or (bool(target) and target in active_procs)
        else:
            actually_exists = False

        reported_exists = tool_output.get("exists", actually_exists)

        if reported_exists == actually_exists:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                verifier="ProcessVerifier",
                expected=f"Process query for '{target or pid}' matches system state",
                observed=f"exists={actually_exists}",
                evidence={"target": target or pid, "exists": actually_exists},
                message=f"Process state verified (exists={actually_exists})",
            )
        else:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                verifier="ProcessVerifier",
                expected=f"Process query for '{target or pid}' matches system state",
                observed=f"reported={reported_exists}, actual={actually_exists}",
                evidence={"reported": reported_exists, "actual": actually_exists},
                message=f"Process state mismatch for '{target or pid}'",
            )


# ---------------------------------------------------------------------------
# Window Verifier
# ---------------------------------------------------------------------------

class WindowVerifier(BaseVerifier):
    """
    Verifies window existence and closing deterministically using visible window titles.
    """

    def can_verify(self, step: Dict[str, Any], tool_output: Dict[str, Any]) -> bool:
        tool = (step.get("tool") or "").lower()
        return tool in {"window_exists", "close_window"} or ("window" in tool and "ui" not in tool)

    def verify(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        args = step.get("args") or step.get("input") or {}
        tool = (step.get("tool") or "").lower()
        target = str(
            args.get("title")
            or args.get("window_title")
            or args.get("target")
            or ""
        ).strip().lower()

        visible_windows = _get_visible_window_titles_windows()
        is_close = "close" in tool

        if is_close:
            if not target:
                return VerificationResult(
                    status=VerificationStatus.UNKNOWN,
                    verifier="WindowVerifier",
                    expected="Target window title for deterministic verification",
                    observed="Generic window close executed without target title",
                    message="Active window closed, but specific window title verification is UNKNOWN",
                )

            found = [w for w in visible_windows if target in w.lower()]
            if not found:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    verifier="WindowVerifier",
                    expected=f"Window matching '{target}' absent",
                    observed="No matching visible window found",
                    evidence={"target": target, "still_visible": False},
                    message=f"Window '{target}' verified closed",
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="WindowVerifier",
                    expected=f"Window matching '{target}' absent",
                    observed=f"Window still visible: {found}",
                    evidence={"target": target, "found": found},
                    message=f"Window '{target}' still visible after close action",
                )

        # window_exists tool
        found = [w for w in visible_windows if target in w.lower()] if target else []
        actually_exists = len(found) > 0
        reported_exists = tool_output.get("exists", actually_exists)

        if reported_exists == actually_exists:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                verifier="WindowVerifier",
                expected=f"Window query '{target}' matches system state",
                observed=f"exists={actually_exists}, matching={found}",
                evidence={"target": target, "matching": found},
                message=f"Window state verified (exists={actually_exists})",
            )
        else:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                verifier="WindowVerifier",
                expected=f"Window query '{target}' matches system state",
                observed=f"reported={reported_exists}, actual={actually_exists}",
                evidence={"reported": reported_exists, "actual": actually_exists},
                message=f"Window state mismatch for '{target}'",
            )


# ---------------------------------------------------------------------------
# Pass-Through / Informational Verifier
# ---------------------------------------------------------------------------

class PassThroughVerifier(BaseVerifier):
    """
    Verifier for read-only or informational tools (system_info, memory_query, etc.)
    where external world mutation was never intended.
    """

    READ_ONLY_TOOLS = {
        "system_info",
        "get_time",
        "memory_query",
        "read_file",
        "read_text_file",
        "view_file",
        "list_directory",
        "list_dir",
        "search_web",
        "web_search",
        "echo",
        "agent_health",
        "refresh_apps",
        "get_process_info",
    }

    def can_verify(self, step: Dict[str, Any], tool_output: Dict[str, Any]) -> bool:
        tool = (step.get("tool") or "").lower()
        return tool in self.READ_ONLY_TOOLS

    def verify(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        return VerificationResult(
            status=VerificationStatus.NOT_APPLICABLE,
            verifier="PassThroughVerifier",
            expected="N/A (Read-only tool)",
            observed=f"Tool executed with ok={tool_output.get('ok', True)}",
            evidence={"tool": step.get("tool")},
            message="Read-only action; mutation verification not applicable",
        )


# ---------------------------------------------------------------------------
# Step Verifier Registry
# ---------------------------------------------------------------------------

class StepVerifierRegistry:
    """
    Central registry and coordinator for step verification.
    Applies the principle: DETERMINISTIC VERIFIER FIRST.
    """

    def __init__(self, verifiers: Optional[List[BaseVerifier]] = None):
        if verifiers is None:
            # Order: PassThrough/Read-only -> File -> Directory -> Process -> Window -> App -> Browser -> UI
            self.verifiers: List[BaseVerifier] = [
                PassThroughVerifier(),
                FileVerifier(),
                DirectoryVerifier(),
                ProcessVerifier(),
                WindowVerifier(),
                ApplicationVerifier(),
                BrowserVerifier(),
                UIInteractionVerifier(),
            ]
        else:
            self.verifiers = list(verifiers)

    def register_verifier(self, verifier: BaseVerifier, prepend: bool = True) -> None:
        """Register a new verifier."""
        if prepend:
            self.verifiers.insert(0, verifier)
        else:
            self.verifiers.append(verifier)

    def verify_step(
        self,
        step: Dict[str, Any],
        tool_output: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        ctx: Optional[Any] = None,
    ) -> VerificationResult:
        """
        Verify a step's execution result.
        Checks cancellation and timeouts before running verifiers.
        """
        # 1. Safety check: cancellation / timeout
        if ctx is not None:
            if getattr(ctx, "is_cancelled", False) is True:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="StepVerifierRegistry",
                    expected="Execution context active",
                    observed="Context was cancelled",
                    evidence={"cancelled": True},
                    message="Verification aborted due to cancellation",
                )
            if getattr(ctx, "is_timed_out", False) is True:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    verifier="StepVerifierRegistry",
                    expected="Execution within timeout budget",
                    observed="Context timed out",
                    evidence={"timed_out": True},
                    message="Verification aborted due to timeout",
                )

        # 2. Find matching verifier
        for verifier in self.verifiers:
            try:
                if verifier.can_verify(step, tool_output):
                    return verifier.verify(step, tool_output, state=state, ctx=ctx)
            except Exception as e:
                return VerificationResult(
                    status=VerificationStatus.UNKNOWN,
                    verifier=verifier.__class__.__name__,
                    expected="Verification execution",
                    observed=f"Verifier raised exception: {str(e)}",
                    evidence={"error": str(e)},
                    message=f"Verification encountered error: {str(e)}",
                )

        # 3. Default fallback if no verifier matched: UNKNOWN (never assume verified!)
        return VerificationResult(
            status=VerificationStatus.UNKNOWN,
            verifier="StepVerifierRegistry",
            expected="Registered verifier for step",
            observed=f"No specialized verifier matched tool '{step.get('tool')}'",
            evidence={"tool": step.get("tool")},
            message=f"No deterministic verifier registered for tool '{step.get('tool')}'; status is UNKNOWN",
        )
