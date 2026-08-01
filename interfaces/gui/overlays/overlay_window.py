from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication, QVBoxLayout

from interfaces.gui.overlays.floating_orb import FloatingOrb
from interfaces.gui.overlays.overlay_animation_manager import OverlayAnimationManager
from interfaces.gui.overlays.overlay_status import OverlayStatus
from interfaces.gui.overlays.transparent_layer import TransparentLayer


class OverlayWindow(TransparentLayer):
    state_changed = Signal(str)

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.click_through_enabled = False
        self.drag_start: QPoint | None = None
        self.animation_manager = OverlayAnimationManager(self)
        self.setWindowTitle("Jarvis Overlay")
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.resize(260, 168)
        self.setup_ui()
        self.move_to_default_position()
        if controller is not None:
            self.connect_controller(controller)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        self.orb = FloatingOrb()
        self.status = OverlayStatus()
        self.status.hide()

        layout.addWidget(self.orb, alignment=Qt.AlignCenter)
        layout.addWidget(self.status, alignment=Qt.AlignCenter)
        self.orb.clicked.connect(lambda: self.show_status("Připraven"))

    def connect_controller(self, controller) -> None:
        controller.status_changed.connect(self.handle_status)
        controller.voice_status_changed.connect(self.handle_voice_status)
        controller.system_message_received.connect(self.handle_system_message)
        controller.audio_volume.connect(self.orb.set_volume)
        controller.audio_volume_zero.connect(self.orb.reset_volume)

    def move_to_default_position(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geometry = screen.availableGeometry()
        self.move(geometry.right() - self.width() - 32, geometry.bottom() - self.height() - 32)

    @Slot(str)
    def set_overlay_state(self, state: str, message: str | None = None) -> None:
        visual = self.animation_manager.visual_state(state)
        self.orb.set_visual_state(visual)
        self.state_changed.emit(visual.name)
        if message or visual.status_text:
            self.show_status(message or visual.status_text)

    def show_status(self, message: str, timeout_ms: int = 2400) -> None:
        self.status.show_message(message, timeout_ms=timeout_ms)
        target = QPoint((self.width() - self.status.width()) // 2, self.orb.y() + self.orb.height() + 4)
        self.animation_manager.show_status(self.status, target)

    def set_click_through(self, enabled: bool) -> None:
        self.click_through_enabled = enabled
        self.setAttribute(Qt.WA_TransparentForMouseEvents, enabled)
        transparent_flag = getattr(Qt, "WindowTransparentForInput", None)
        if transparent_flag is not None:
            flags = self.windowFlags()
            if enabled:
                flags |= transparent_flag
            else:
                flags &= ~transparent_flag
            self.setWindowFlags(flags)
            self.show()

    @Slot(str)
    def handle_voice_status(self, status: str) -> None:
        lower = status.lower()
        if "listening" in lower:
            self.set_overlay_state("LISTENING", "Poslouchám...")
        elif "disconnected" in lower:
            self.set_overlay_state("IDLE", "Připraven")

    @Slot(str)
    def handle_status(self, status: str) -> None:
        lower = status.lower()
        if "listening" in lower:
            self.set_overlay_state("LISTENING", "Poslouchám...")
        elif "thinking" in lower or "premyslim" in lower or "přemýšlím" in lower:
            self.set_overlay_state("THINKING", "Přemýšlím...")
        elif "speaking" in lower:
            self.set_overlay_state("SPEAKING", "Mluvím...")
        elif "transcribing" in lower:
            self.set_overlay_state("THINKING", "Přepisuji hlas...")
        elif "provadim" in lower or "provádím" in lower:
            self.set_overlay_state("ACTION_RUNNING", "Provádím akci...")
        elif "ready" in lower:
            self.set_overlay_state("IDLE", "Hotovo.")

    @Slot(str)
    def handle_system_message(self, message: str) -> None:
        lower = message.lower()
        if "recording" in lower:
            self.set_overlay_state("LISTENING", "Poslouchám...")
        elif "wake word detected" in lower:
            self.set_overlay_state("LISTENING", "Wake word zachycen")
        elif "agent mode" in lower:
            self.set_overlay_state("ACTION_RUNNING", "Provádím akci...")
        elif "chrome" in lower:
            self.set_overlay_state("ACTION_RUNNING", "Otevírám Chrome...")
        elif "obrazov" in lower or "screenshot" in lower or "ocr" in lower:
            self.set_overlay_state("ACTION_RUNNING", "Analyzuji obrazovku...")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.click_through_enabled:
            self.drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_start is not None and not self.click_through_enabled:
            self.move(event.globalPosition().toPoint() - self.drag_start)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_start = None
        super().mouseReleaseEvent(event)
