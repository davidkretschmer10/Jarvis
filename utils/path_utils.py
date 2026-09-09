# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def canonical_windows_path(path_str: str, workspace_root: Optional[str] = None) -> str:
    """
    Deterministically normalize and resolve a Windows path:
    1. Expands environment variables (e.g. %APPDATA%, %TEMP%, %USERPROFILE%).
    2. Expands user home tilde (~).
    3. Resolves relative paths against workspace_root (or cwd).
    4. Canonicalizes directory traversals ('..') and symlinks via Path.resolve().
    5. Normalizes Windows separators and trailing slashes.
    """
    if not path_str or not isinstance(path_str, str):
        return ""

    raw = path_str.strip()
    if not raw:
        return ""

    # Don't alter web URLs
    if raw.lower().startswith(("http://", "https://", "ws://", "wss://")):
        return raw

    # 1. Expand environment variables (e.g. %TEMP%, %APPDATA%)
    expanded = os.path.expandvars(raw)

    # 2. Expand user tilde (~ / ~user)
    expanded = os.path.expanduser(expanded)

    # 3. Resolve against workspace_root if relative
    path_obj = Path(expanded)
    if not path_obj.is_absolute():
        base = workspace_root or os.getcwd()
        path_obj = Path(base) / path_obj

    # 4. Resolve canonical absolute path (handles .., symlinks, junctions)
    try:
        resolved = path_obj.resolve()
    except Exception:
        resolved = Path(os.path.abspath(str(path_obj)))

    # 5. Return normalized string
    return str(resolved)


def is_subpath_of(candidate_path: str, parent_directory: str) -> bool:
    """Return True if candidate_path is strictly inside or equal to parent_directory."""
    try:
        c_can = Path(canonical_windows_path(candidate_path))
        p_can = Path(canonical_windows_path(parent_directory))
        return p_can == c_can or p_can in c_can.parents
    except Exception:
        return False


def get_system_protected_roots() -> list[str]:
    """Return canonical paths of protected Windows directories."""
    roots = []
    windir = os.environ.get("WINDIR", r"C:\Windows")
    if windir:
        roots.append(canonical_windows_path(windir))

    prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    if prog_files:
        roots.append(canonical_windows_path(prog_files))

    prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    if prog_files_x86:
        roots.append(canonical_windows_path(prog_files_x86))

    prog_data = os.environ.get("ProgramData", r"C:\ProgramData")
    if prog_data:
        roots.append(canonical_windows_path(prog_data))

    return roots


def is_protected_system_path(path_str: str) -> bool:
    """Check if the given path falls under a protected Windows system root."""
    if not path_str:
        return False

    can_path = canonical_windows_path(path_str).lower()
    path_obj = Path(can_path)

    # Drive root check (e.g. C:\ or D:\ directly)
    if len(path_obj.parts) <= 1:
        return True

    for sys_root in get_system_protected_roots():
        sys_root_lower = sys_root.lower()
        if can_path == sys_root_lower or can_path.startswith(sys_root_lower + os.sep):
            return True

    return False
