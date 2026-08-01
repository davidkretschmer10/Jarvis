from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget


class TaskProgressWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps_labels: list[QLabel] = []
        self.steps_data: list[dict] = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Title/Header
        self.task_title = QLabel("Žádný aktivní úkol")
        self.task_title.setObjectName("InfoTitle")
        self.task_title.setWordWrap(True)
        layout.addWidget(self.task_title)

        # Scroll area for steps
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.steps_layout = QVBoxLayout(self.scroll_content)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(8)
        self.steps_layout.addStretch()

        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll, 1)

    def set_task(self, title: str, steps: list[str] | list[dict]):
        """Initializes the widget with a new task title and list of step descriptions."""
        self.clear_task()
        self.task_title.setText(f"AKTIVNÍ ÚKOL:\n{title}")

        # Remove the stretch at the bottom to insert items
        self.steps_layout.takeAt(self.steps_layout.count() - 1)

        for i, step in enumerate(steps):
            step_desc = step if isinstance(step, str) else step.get("description", f"Krok {i+1}")
            
            # Step container
            step_frame = QFrame()
            step_frame.setStyleSheet(
                "QFrame { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04); border-radius: 6px; padding: 6px; }"
            )
            step_layout = QVBoxLayout(step_frame)
            step_layout.setContentsMargins(8, 4, 8, 4)

            # Label for icon + description
            label = QLabel(f"⬜  {step_desc}")
            label.setWordWrap(True)
            label.setStyleSheet("color: #94a3b8; font-size: 12px;")
            step_layout.addWidget(label)
            
            self.steps_layout.addWidget(step_frame)
            self.steps_labels.append(label)
            
            step_info = {"desc": step_desc, "frame": step_frame}
            if isinstance(step, dict):
                step_info.update(step)
            self.steps_data.append(step_info)

        self.steps_layout.addStretch()

    def update_step(self, index: int, status: str):
        """Updates the visual indicator for a specific step index."""
        if 0 <= index < len(self.steps_labels):
            label = self.steps_labels[index]
            desc = self.steps_data[index]["desc"]
            frame = self.steps_data[index]["frame"]

            if status == "completed":
                label.setText(f"✓  {desc}")
                label.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px;") # Green
                frame.setStyleSheet(
                    "QFrame { background: rgba(16,185,129,0.04); border: 1px solid rgba(16,185,129,0.15); border-radius: 6px; padding: 6px; }"
                )
            elif status == "in_progress":
                label.setText(f"⏳  {desc}")
                label.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;") # Blue
                frame.setStyleSheet(
                    "QFrame { background: rgba(14,165,233,0.04); border: 1px solid rgba(14,165,233,0.2); border-radius: 6px; padding: 6px; }"
                )
            elif status == "failed":
                label.setText(f"✗  {desc}")
                label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 12px;") # Red
                frame.setStyleSheet(
                    "QFrame { background: rgba(239,68,68,0.04); border: 1px solid rgba(239,68,68,0.2); border-radius: 6px; padding: 6px; }"
                )
            elif status == "paused":
                label.setText(f"⏸  {desc}")
                label.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 12px;") # Yellow/Amber
                frame.setStyleSheet(
                    "QFrame { background: rgba(245,158,11,0.04); border: 1px solid rgba(245,158,11,0.2); border-radius: 6px; padding: 6px; }"
                )
            else:
                label.setText(f"⬜  {desc}")
                label.setStyleSheet("color: #94a3b8; font-size: 12px;")
                frame.setStyleSheet(
                    "QFrame { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04); border-radius: 6px; padding: 6px; }"
                )

    def clear_task(self):
        """Clears the task steps checklist."""
        self.task_title.setText("Žádný aktivní úkol")
        
        # Clear existing widgets from layout
        while self.steps_layout.count() > 0:
            item = self.steps_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.steps_labels.clear()
        self.steps_data.clear()
        self.steps_layout.addStretch()
