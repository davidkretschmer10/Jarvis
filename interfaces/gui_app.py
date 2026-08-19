import sys
from PySide6.QtWidgets import QApplication

from core.startup import ensure_ai_engine_started
from interfaces.gui_controller import GuiController
from interfaces.gui.main_window import JarvisMainWindow
from core.event_bus import EventBus

def start_gui():
    print("Starting AI engine...")
    ensure_ai_engine_started()
    print("AI ready")

    app = QApplication(sys.argv)
    event_bus = EventBus()
    controller = GuiController(event_bus)
    window = JarvisMainWindow(controller, event_bus)
    window.show()
    sys.exit(app.exec())
