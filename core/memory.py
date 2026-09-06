# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any
from core.memory_manager import get_memory_manager


def _get_chats_file() -> str:
    return get_memory_manager().chats_file


def _get_profile_file() -> str:
    return get_memory_manager().profile_file


class _DynamicPath:
    def __init__(self, getter):
        self._getter = getter

    def __fspath__(self) -> str:
        return self._getter()

    def __str__(self) -> str:
        return self._getter()

    def __eq__(self, other: Any) -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))


CHATS_FILE = _DynamicPath(_get_chats_file)
PROFILE_FILE = _DynamicPath(_get_profile_file)
DATA_DIR = _DynamicPath(lambda: get_memory_manager().data_dir)


def load_json(file: str) -> Any:
    file_str = str(file)
    mgr = get_memory_manager()
    if file_str == str(mgr.chats_file):
        return mgr.load_chats()
    if file_str == str(mgr.profile_file):
        return mgr.load_profile()
    if file_str == str(mgr.task_memory_file):
        return mgr.load_task_memory()
    if file_str == str(mgr.app_prefs_file):
        return mgr.load_app_preferences()
    return mgr._safe_read_json(file_str, default={})


def save_json(file: str, data: Any) -> None:
    file_str = str(file)
    mgr = get_memory_manager()
    if file_str == str(mgr.chats_file):
        mgr.save_chats(data if isinstance(data, dict) else {})
    elif file_str == str(mgr.profile_file):
        mgr.save_profile(data if isinstance(data, list) else [])
    elif file_str == str(mgr.task_memory_file):
        mgr.save_task_memory(data if isinstance(data, dict) else {})
    elif file_str == str(mgr.app_prefs_file):
        mgr.save_app_preferences(data if isinstance(data, dict) else {})
    else:
        mgr._atomic_write_json(file_str, data)


def update_profile(profile: list, message: str) -> list:
    mgr = get_memory_manager()
    return mgr.update_profile(message)
