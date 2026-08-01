from PySide6.QtWidgets import QButtonGroup, QLabel, QPushButton, QRadioButton, QVBoxLayout, QWidget

from interfaces.gui.models_widget import ModelsWidget


class SettingsWidget(QWidget):
    def __init__(self, controller, event_bus, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.event_bus = event_bus
        self.models_widget = ModelsWidget(controller)
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.back_button = QPushButton("Zpet")
        self.back_button.setObjectName("ActionBtn")
        layout.addWidget(self.back_button)
        layout.addWidget(self.models_widget)

        response_widget = QWidget()
        response_layout = QVBoxLayout(response_widget)
        response_layout.addWidget(QLabel("Response Mode"))

        self.response_group = QButtonGroup()
        self.mode_fast = QRadioButton("Fast")
        self.mode_balanced = QRadioButton("Balanced")
        self.mode_precise = QRadioButton("Precise")
        self.mode_balanced.setChecked(True)

        for button in [self.mode_fast, self.mode_balanced, self.mode_precise]:
            self.response_group.addButton(button)
            response_layout.addWidget(button)
            button.toggled.connect(self.update_settings)

        layout.addWidget(response_widget)
        layout.addStretch()

    def connect_signals(self):
        for model_box in self.models_widget.model_boxes.values():
            model_box.stateChanged.connect(self.update_settings)
        for mode_button in self.models_widget.mode_group.buttons():
            mode_button.toggled.connect(self.update_settings)

    def get_response_mode(self):
        if self.mode_fast.isChecked():
            return "fast"
        if self.mode_precise.isChecked():
            return "precise"
        return "balanced"

    def update_settings(self):
        settings = {
            "mode": self.models_widget.get_mode(),
            "response_mode": self.get_response_mode(),
            "enabled_models": self.models_widget.get_enabled_models(),
        }
        self.controller.update_settings(settings)
