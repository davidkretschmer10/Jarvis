from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox, QButtonGroup, QRadioButton

class ModelsWidget(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.model_boxes = {}
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        models = ["llama3", "mistral", "phi3", "gemma", "qwen", "deepseek-coder"]
        
        model_widget = QWidget()
        model_layout = QVBoxLayout(model_widget)
        model_layout.addWidget(QLabel("AI Models"))

        for m in models:
            box = QCheckBox(m)
            box.setChecked(True)
            self.model_boxes[m] = box
            model_layout.addWidget(box)
            box.stateChanged.connect(self.update_settings)

        mode_widget = QWidget()
        mode_layout = QVBoxLayout(mode_widget)
        mode_layout.addWidget(QLabel("Quick Mode"))

        self.mode_group = QButtonGroup()
        self.mode_auto = QRadioButton("Auto")
        self.mode_programming = QRadioButton("Programming")
        self.mode_creative = QRadioButton("Creative")
        self.mode_logic = QRadioButton("Logic")
        self.mode_planning = QRadioButton("Planning")
        self.mode_auto.setChecked(True)

        for m in [self.mode_auto, self.mode_programming, self.mode_creative, self.mode_logic, self.mode_planning]:
            self.mode_group.addButton(m)
            mode_layout.addWidget(m)
            m.toggled.connect(self.update_settings)

        layout.addWidget(model_widget)
        layout.addWidget(mode_widget)

    def get_enabled_models(self):
        enabled = []
        for name, box in self.model_boxes.items():
            if box.isChecked():
                enabled.append(name)
        return enabled

    def get_mode(self):
        if self.mode_programming.isChecked(): return "programming"
        if self.mode_creative.isChecked(): return "creative"
        if self.mode_logic.isChecked(): return "logic"
        if self.mode_planning.isChecked(): return "planning"
        return "auto"

    def update_settings(self):
        # We emit settings upstream via a public method the settings_widget uses, or direct to controller
        pass
