from __future__ import annotations

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QLabel

from interfaces.gui.voice.face import JarvisFaceWidget
from interfaces.gui.voice.particles import ParticleSystem
from interfaces.gui.voice.wave import VoiceWaveWidget


class VoiceStateManager(QObject):
    """Orchestrates state mapping from backend controller signals to GUI visual assets."""
    
    def __init__(
        self,
        controller,
        face: JarvisFaceWidget,
        particles: ParticleSystem,
        wave: VoiceWaveWidget,
        state_label: QLabel,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.face = face
        self.particles = particles
        self.wave = wave
        self.state_label = state_label
        
        self.current_state = "ready"
        self.connect_signals()

    def connect_signals(self):
        self.controller.status_changed.connect(self.handle_global_status)
        self.controller.voice_status_changed.connect(self.handle_voice_status)
        self.controller.audio_volume.connect(self.handle_volume)
        self.controller.audio_volume_zero.connect(self.handle_volume_zero)
        self.controller.system_message_received.connect(self.handle_system_status)

    @Slot(str)
    def handle_global_status(self, status: str):
        lower = status.lower()
        if "listening" in lower or "posloucham" in lower or "poslouchám" in lower:
            self.set_state("listening", "Poslouchám...")
        elif "thinking" in lower or "premyslim" in lower or "přemýšlím" in lower or "transcribing" in lower:
            self.set_state("thinking", "Přemýšlím...")
        elif "speaking" in lower or "mluvim" in lower or "mluvím" in lower:
            self.set_state("speaking", "Mluvím...")
        elif "ready" in lower:
            self.set_state("ready", "READY")

    @Slot(str)
    def handle_voice_status(self, status: str):
        lower = status.lower()
        if "listening" in lower:
            self.set_state("listening", "Poslouchám...")
        elif "disconnected" in lower:
            self.set_state("ready", "READY")

    @Slot(str)
    def handle_system_status(self, message: str):
        lower = message.lower()
        if "recording" in lower:
            self.set_state("listening", "Poslouchám...")
        elif "wake word detected" in lower:
            self.set_state("listening", "Poslouchám...")

    @Slot(int)
    def handle_volume(self, volume: int):
        self.face.set_volume(volume)
        self.particles.set_volume(volume)
        self.wave.set_volume(volume)

    @Slot()
    def handle_volume_zero(self):
        self.face.reset_volume()
        self.particles.set_volume(0)
        self.wave.reset_volume()

    def set_state(self, state: str, label_text: str):
        self.current_state = state
        self.face.set_state(state)
        self.particles.set_state(state)
        self.wave.set_state(state)
        self.state_label.setText(label_text)
