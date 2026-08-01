from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from interfaces.gui.chat.input_bar import ModernInputBar
from interfaces.gui.chat.message_bubble import MessageBubble
from interfaces.gui.chat.timeline import ChatTimeline
from interfaces.gui.voice.waveform import NeonWaveform as WaveformWidget


class ChatWidget(QWidget):
    on_agent_response_signal = Signal(str)
    on_error_signal = Signal(str)

    def __init__(self, controller, event_bus, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.event_bus = event_bus
        self.current_ai_bubble: MessageBubble | None = None
        self.setup_ui()
        self.connect_signals()

        self.on_agent_response_signal.connect(self.handle_agent_response_ui)
        self.on_error_signal.connect(self.handle_error_ui)
        self.event_bus.on("agent_response", lambda res: self.on_agent_response_signal.emit(str(res) if res else ""))
        self.event_bus.on("error", lambda message: self.on_error_signal.emit(str(message)))

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        self.timeline = ChatTimeline()
        self.audio_level = WaveformWidget()
        self.input_bar = ModernInputBar()

        self.input = self.input_bar.input
        self.send_button = self.input_bar.send_button
        self.voice_button = self.input_bar.voice_button
        self.send_voice_button = self.input_bar.send_voice_button
        self.voice_read_checkbox = self.input_bar.voice_read_checkbox
        self.wake_checkbox = self.input_bar.wake_checkbox

        outer.addWidget(self.timeline, 1)
        outer.addWidget(self.input_bar)

    def connect_signals(self):
        self.send_button.clicked.connect(self.send_input)
        self.input.returnPressed.connect(self.send_input)
        self.send_voice_button.clicked.connect(self.controller.send_voice)
        self.voice_button.pressed.connect(self.controller.start_recording)
        self.voice_button.released.connect(self.controller.stop_recording)
        self.wake_checkbox.stateChanged.connect(self.controller.toggle_wake_word)
        self.voice_read_checkbox.stateChanged.connect(self.controller.set_voice_read_enabled)
        self.controller.clear_input.connect(self.input.clear)
        self.controller.audio_volume.connect(self.audio_level.setVolume)
        self.controller.audio_volume_zero.connect(self.audio_level.setVolumesZero)
        self.controller.audio_volume.connect(self.voice_button.set_volume)
        self.controller.audio_volume_zero.connect(self.voice_button.reset_volume)
        self.controller.chunk_received.connect(self.append_chunk)
        self.controller.start_ai_bubble.connect(self.start_ai_bubble)
        self.controller.end_ai_bubble.connect(self.end_ai_bubble)
        self.controller.user_message_received.connect(self.append_user_message)
        self.controller.system_message_received.connect(self.append_system_message)
        self.controller.chat_loaded.connect(self.load_chat_history)

    def send_input(self):
        text = self.input.text().strip()
        if text:
            self.event_bus.emit("user_message", text)

    @Slot(str)
    def handle_agent_response_ui(self, response):
        if response:
            self.append_system_message(f"Agent: {response}")

    @Slot(str)
    def handle_error_ui(self, message):
        if message:
            self.append_system_message(f"Chyba: {message}")

    @Slot()
    def start_ai_bubble(self):
        self.current_ai_bubble = self.timeline.add_message("jarvis", "")
        self.current_ai_bubble.content_changed.connect(self.timeline.scroll_to_bottom)
        self.current_ai_bubble.start_thinking()

    @Slot()
    def end_ai_bubble(self):
        if self.current_ai_bubble:
            self.current_ai_bubble.stop_thinking()
            self.current_ai_bubble.finish_typing()
        self.current_ai_bubble = None
        self.timeline.scroll_to_bottom()

    @Slot(str)
    def append_user_message(self, text):
        self.timeline.add_message("user", text)

    @Slot(str)
    def append_system_message(self, text):
        self.timeline.add_message("system", text)

    @Slot(str)
    def append_chunk(self, chunk):
        if not self.current_ai_bubble:
            self.current_ai_bubble = self.timeline.add_message("jarvis", "", animate=False)
            self.current_ai_bubble.content_changed.connect(self.timeline.scroll_to_bottom)
        self.current_ai_bubble.append_text(chunk)
        self.timeline.scroll_to_bottom()

    @Slot(list, str)
    def load_chat_history(self, messages, model):
        self.timeline.clear_messages()
        self.current_ai_bubble = None
        for msg in messages:
            if msg.startswith("Ty: "):
                self.timeline.add_message("user", msg[4:], animate=False)
            elif msg.startswith("Jarvis: "):
                self.timeline.add_message("jarvis", msg[8:], animate=False)
            elif msg.startswith("Voice: Ty: "):
                self.timeline.add_message("user", "Voice: " + msg[11:], animate=False)
            else:
                self.timeline.add_message("system", msg, animate=False)
        self.timeline.scroll_to_bottom(animated=False)
