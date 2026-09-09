# -*- coding: utf-8 -*-
import json
import os
import shutil
import tempfile
import threading
import unittest

from core.memory import load_json, save_json, update_profile
from core.memory_manager import MemoryManager, get_memory_manager, set_memory_manager
from core.task_memory import TaskMemory


class TestMemoryManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager = MemoryManager(data_dir=self.temp_dir)
        set_memory_manager(self.manager)

    def tearDown(self):
        set_memory_manager(None)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_and_custom_directory_override(self):
        """Verify MemoryManager correctly uses provided directory."""
        self.assertEqual(self.manager.data_dir, os.path.abspath(self.temp_dir))
        self.assertTrue(os.path.exists(self.temp_dir))

    def test_user_memory_read_write(self):
        """Verify user profile reading and writing."""
        initial = self.manager.load_profile()
        self.assertEqual(initial, [])

        profile_data = ["uzivatel se zajima o python", "uzivatel se zajima o ai"]
        self.manager.save_profile(profile_data)

        loaded = self.manager.load_profile()
        self.assertEqual(loaded, profile_data)

    def test_update_profile(self):
        """Verify updating profile facts based on user messages."""
        res = self.manager.update_profile("Rád programuji v pythonu.")
        self.assertIn("uzivatel se zajima o python", res)
        self.assertEqual(self.manager.load_profile(), res)

    def test_conversation_memory_read_write(self):
        """Verify chat history reading and writing."""
        chats = {"Chat 1": {"messages": ["Ty: ahoj", "Jarvis: Ahoj!"], "model": "auto"}}
        self.manager.save_chats(chats)

        loaded = self.manager.load_chats()
        self.assertEqual(loaded, chats)

    def test_task_memory_read_write_reset(self):
        """Verify task execution memory reading, writing, and reset."""
        task_data = {
            "current_task": "zapni chrome",
            "steps": [{"tool": "open_app", "input": {"name": "chrome"}, "status": "pending"}],
            "last_result": "",
        }
        self.manager.save_task_memory(task_data)

        loaded = self.manager.load_task_memory()
        self.assertEqual(loaded["current_task"], "zapni chrome")

        self.manager.reset_task_memory()
        reset_data = self.manager.load_task_memory()
        self.assertEqual(reset_data["current_task"], "")
        self.assertEqual(reset_data["steps"], [])

    def test_app_preferences_read_write(self):
        """Verify application preferences reading and writing."""
        prefs = {"chrome": "C:\\Program Files\\Chrome\\chrome.exe"}
        self.manager.save_app_preferences(prefs)

        loaded = self.manager.load_app_preferences()
        self.assertEqual(loaded, prefs)

    def test_persistence_between_instances(self):
        """Verify data persists when a new MemoryManager instance opens the same data_dir."""
        self.manager.save_profile(["fact 1"])
        self.manager.save_chats({"Default": {"messages": ["msg1"]}})

        # New instance pointing to same directory
        new_manager = MemoryManager(data_dir=self.temp_dir)
        self.assertEqual(new_manager.load_profile(), ["fact 1"])
        self.assertEqual(new_manager.load_chats(), {"Default": {"messages": ["msg1"]}})

    def test_atomic_write_behavior(self):
        """Verify atomic file writing leaves no temporary files behind."""
        self.manager.save_profile(["fact A"])
        files_in_dir = os.listdir(self.temp_dir)
        # Check no .tmp files remain
        tmp_files = [f for f in files_in_dir if ".tmp" in f]
        self.assertEqual(tmp_files, [])

    def test_legacy_app_memory_migration(self):
        """Verify legacy app_memory.json file is safely migrated and deleted from root."""
        legacy_file = os.path.join(os.getcwd(), "app_memory.json")
        try:
            with open(legacy_file, "w", encoding="utf-8") as f:
                json.dump({"legacy_pref": "val123"}, f)

            migrated_manager = MemoryManager(data_dir=self.temp_dir)
            prefs = migrated_manager.load_app_preferences()

            self.assertIn("migrated_app_memory", prefs)
            self.assertEqual(prefs["migrated_app_memory"], {"legacy_pref": "val123"})
            self.assertFalse(os.path.exists(legacy_file))
        finally:
            if os.path.exists(legacy_file):
                os.remove(legacy_file)

    def test_idempotent_migration(self):
        """Verify running migration multiple times does not throw or corrupt data."""
        self.manager.migrate_legacy_data()
        self.manager.migrate_legacy_data()
        self.assertTrue(os.path.exists(self.temp_dir))

    def test_corrupted_json_handling(self):
        """Verify resilience when reading corrupted memory files."""
        corrupted_file = self.manager.profile_file
        with open(corrupted_file, "w", encoding="utf-8") as f:
            f.write("{invalid json content...")

        loaded = self.manager.load_profile()
        self.assertEqual(loaded, [])

    def test_concurrent_thread_safety(self):
        """Verify thread-safety when multiple threads concurrently write and read memory."""
        errors = []

        def worker(idx):
            try:
                for i in range(10):
                    self.manager.update_profile(f"python interest {idx}_{i}")
                    with self.manager._lock:
                        chats = self.manager.load_chats()
                        chats[f"Thread_{idx}"] = {"messages": [f"step {i}"]}
                        self.manager.save_chats(chats)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        chats = self.manager.load_chats()
        self.assertEqual(len(chats), 5)

    def test_core_memory_wrapper_delegation(self):
        """Verify core/memory.py legacy wrappers correctly delegate to MemoryManager."""
        chats_data = {"WrapperChat": {"messages": ["hello"]}}
        save_json(self.manager.chats_file, chats_data)

        read_chats = load_json(self.manager.chats_file)
        self.assertEqual(read_chats, chats_data)

        updated_profile = update_profile([], "zajimam se o trading")
        self.assertIn("uzivatel se zajima o trading", updated_profile)

    def test_task_memory_class_delegation(self):
        """Verify TaskMemory class delegates persistence to MemoryManager."""
        tm = TaskMemory()
        tm.start_task("test goal", [{"tool": "open_app", "input": {"name": "calc"}}])

        loaded_task_data = self.manager.load_task_memory()
        self.assertEqual(loaded_task_data["current_task"], "test goal")
        self.assertEqual(len(loaded_task_data["steps"]), 1)

        tm.update_step_status(0, "completed", "opened calc")
        updated_data = self.manager.load_task_memory()
        self.assertEqual(updated_data["steps"][0]["status"], "completed")

        tm.reset()
        cleared_data = self.manager.load_task_memory()
        self.assertEqual(cleared_data["current_task"], "")


if __name__ == "__main__":
    unittest.main()
