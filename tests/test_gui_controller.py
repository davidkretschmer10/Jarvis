import sys
import types
import unittest
from unittest.mock import Mock, patch

from core.event_bus import EventBus


fake_voice = types.ModuleType("interfaces.voice")
fake_voice.interrupt_speech = Mock()
fake_voice.listen_once_to_text = Mock(return_value="")
fake_voice.speak = Mock()
fake_voice.speech_to_text = Mock(return_value="")
fake_voice.start_recording = Mock()
fake_voice.stop_recording = Mock()
fake_voice.stop_wake_listener = Mock()
fake_voice.wake_listener = Mock()

sys.modules.setdefault("interfaces.voice", fake_voice)

from interfaces.gui_controller import GuiController


class FakeSignal:
    def connect(self, callback):
        self.callback = callback


class FakeTimer:
    def __init__(self, parent=None):
        self.timeout = FakeSignal()

    def setInterval(self, value):
        self.interval = value

    def start(self):
        self.started = True


class GuiControllerTests(unittest.TestCase):
    def test_new_chat_persists_and_emits_current_chat(self):
        bus = EventBus()
        with patch("interfaces.gui_controller.load_json", side_effect=[{}, []]), patch(
            "interfaces.gui_controller.save_json"
        ) as save_json, patch("interfaces.gui_controller.QTimer", FakeTimer), patch.object(
            GuiController, "refresh_ollama_status"
        ):
            controller = GuiController(bus)
            controller.new_chat()

        self.assertIn("Chat 2", controller.chats)
        save_json.assert_called()

    def test_handle_user_message_routes_non_chat_intent_to_agent(self):
        bus = EventBus()
        with patch("interfaces.gui_controller.load_json", side_effect=[{}, []]), patch(
            "interfaces.gui_controller.save_json"
        ), patch("interfaces.gui_controller.QTimer", FakeTimer), patch.object(
            GuiController, "refresh_ollama_status"
        ), patch.object(
            GuiController, "process_agent_request"
        ) as process_agent:
            controller = GuiController(bus)
            controller.handle_user_message("zapni epic")

        process_agent.assert_called_once()


if __name__ == "__main__":
    unittest.main()
