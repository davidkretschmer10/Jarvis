from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from interfaces.gui.voice.voice_scene import VoiceScene


class VoiceWidget(QWidget):
    """Wrapper page for the new immersive fullscreen VoiceScene."""
    
    def __init__(self, controller, event_bus, parent: QWidget | None = None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Instantiate full-screen VoiceScene
        self.scene = VoiceScene(controller, event_bus, self)
        layout.addWidget(self.scene)
