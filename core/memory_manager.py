# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional

from core.services.application_resolver import get_default_appdata_path

_instance_lock = threading.RLock()
_global_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    global _global_memory_manager
    with _instance_lock:
        if _global_memory_manager is None:
            _global_memory_manager = MemoryManager()
        return _global_memory_manager


def set_memory_manager(instance: Optional[MemoryManager]) -> None:
    global _global_memory_manager
    with _instance_lock:
        _global_memory_manager = instance


class MemoryManager:
    """
    Centralized, thread-safe, atomic persistence manager for Jarvis memory domains:
    - User Profile & Facts (jarvis_profile.json)
    - Conversation History & Sessions (jarvis_chats.json)
    - Task Execution Memory (jarvis_task_memory.json)
    - Application Preferences & Aliases (jarvis_user_preferences.json)
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        if data_dir:
            self.data_dir = os.path.abspath(data_dir)
        else:
            default_sample_file = get_default_appdata_path("jarvis_memory_init.flag")
            self.data_dir = os.path.dirname(default_sample_file)

        os.makedirs(self.data_dir, exist_ok=True)

        self._lock = threading.RLock()

        self.chats_file = os.path.join(self.data_dir, "jarvis_chats.json")
        self.profile_file = os.path.join(self.data_dir, "jarvis_profile.json")
        self.task_memory_file = os.path.join(self.data_dir, "jarvis_task_memory.json")
        self.app_prefs_file = os.path.join(self.data_dir, "jarvis_user_preferences.json")

        self.migrate_legacy_data()

    def _atomic_write_json(self, filepath: str, data: Any) -> None:
        """Writes data atomically to filepath using a temporary file and os.replace."""
        with self._lock:
            dir_name = os.path.dirname(filepath)
            os.makedirs(dir_name, exist_ok=True)

            tmp_filepath = f"{filepath}.tmp_{threading.get_ident()}"
            try:
                with open(tmp_filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_filepath, filepath)
            except Exception as e:
                print(f"[MEMORY_MANAGER] Atomic save error for {filepath}: {e}")
                if os.path.exists(tmp_filepath):
                    try:
                        os.remove(tmp_filepath)
                    except Exception:
                        pass
                raise

    def _safe_read_json(self, filepath: str, default: Any) -> Any:
        """Reads JSON data safely with fallback to default on error or missing file."""
        with self._lock:
            if not os.path.exists(filepath):
                return default
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[MEMORY_MANAGER] Error reading {filepath}: {e}")
                return default

    # --- LEGACY MIGRATION ---

    def migrate_legacy_data(self) -> None:
        """Idempotent migration of legacy app_memory.json or root files if present."""
        with self._lock:
            legacy_app_mem_path = os.path.join(os.getcwd(), "app_memory.json")
            if os.path.exists(legacy_app_mem_path):
                try:
                    with open(legacy_app_mem_path, "r", encoding="utf-8") as f:
                        legacy_data = json.load(f)
                    if isinstance(legacy_data, dict) and legacy_data:
                        current_prefs = self.load_app_preferences()
                        current_prefs["migrated_app_memory"] = legacy_data
                        self.save_app_preferences(current_prefs)
                    os.remove(legacy_app_mem_path)
                    print(f"[MEMORY_MANAGER] Migrated legacy app_memory.json to {self.app_prefs_file}")
                except Exception as e:
                    print(f"[MEMORY_MANAGER] Legacy migration skipped/failed: {e}")

    # --- CHAT & CONVERSATION MEMORY ---

    def load_chats(self) -> Dict[str, Any]:
        data = self._safe_read_json(self.chats_file, default={})
        if not isinstance(data, dict):
            return {}
        return data

    def save_chats(self, chats: Dict[str, Any]) -> None:
        self._atomic_write_json(self.chats_file, chats)

    # --- USER PROFILE MEMORY ---

    def load_profile(self) -> List[str]:
        data = self._safe_read_json(self.profile_file, default=[])
        if not isinstance(data, list):
            return []
        return data

    def save_profile(self, profile: List[str]) -> None:
        self._atomic_write_json(self.profile_file, profile)

    def update_profile(self, message: str) -> List[str]:
        with self._lock:
            profile = self.load_profile()
            keywords = [
                "programovani",
                "programování",
                "python",
                "unity",
                "blender",
                "trading",
                "akcie",
                "investuji",
                "hra",
                "ai",
            ]
            lower = message.lower()
            updated = False
            for word in keywords:
                if word in lower:
                    fact = f"uzivatel se zajima o {word}"
                    if fact not in profile:
                        profile.append(fact)
                        updated = True
            if updated:
                self.save_profile(profile)
            return profile

    # --- TASK EXECUTION MEMORY ---

    def load_task_memory(self) -> Dict[str, Any]:
        data = self._safe_read_json(
            self.task_memory_file,
            default={"current_task": "", "steps": [], "last_result": ""},
        )
        if not isinstance(data, dict):
            return {"current_task": "", "steps": [], "last_result": ""}
        return data

    def save_task_memory(self, task_data: Dict[str, Any]) -> None:
        self._atomic_write_json(self.task_memory_file, task_data)

    def reset_task_memory(self) -> None:
        with self._lock:
            empty_data = {"current_task": "", "steps": [], "last_result": ""}
            self._atomic_write_json(self.task_memory_file, empty_data)

    # --- APP PREFERENCES MEMORY ---

    def load_app_preferences(self) -> Dict[str, Any]:
        data = self._safe_read_json(self.app_prefs_file, default={})
        if not isinstance(data, dict):
            return {}
        return data

    def save_app_preferences(self, prefs: Dict[str, Any]) -> None:
        self._atomic_write_json(self.app_prefs_file, prefs)
