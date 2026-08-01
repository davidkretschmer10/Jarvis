from __future__ import annotations

from datetime import datetime
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class ChatListIcon(QWidget):
    """Small vector icon representing a chat bubble."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.active = False
        self.hovered = False

    def set_states(self, active: bool, hovered: bool):
        self.active = active
        self.hovered = hovered
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.active:
            color = QColor("#38bdf8")
        elif self.hovered:
            color = QColor("#e2e8f0")
        else:
            color = QColor("#64748b")

        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        path = QPainterPath()
        # Draw a speech bubble
        path.addRoundedRect(2, 2, 16, 12, 2.5, 2.5)
        path.moveTo(5, 14)
        path.lineTo(2, 17)
        path.lineTo(2, 14)
        painter.drawPath(path)


class ChatListItem(QFrame):
    clicked = Signal(str)
    delete_requested = Signal(str)
    rename_requested = Signal(str)
    export_requested = Signal(str)
    pin_requested = Signal(str)

    def __init__(self, name: str, timestamp: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.name = name
        self.active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("ChatListItem")
        
        # Determine a reasonable default timestamp if empty
        if not timestamp:
            timestamp = datetime.now().strftime("%H:%M")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(10)

        # 1. Chat bubble icon
        self.icon_widget = ChatListIcon()
        layout.addWidget(self.icon_widget)

        # 2. Text layout (Title + Timestamp/Status)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)
        text_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(name)
        self.title_label.setObjectName("ChatListItemTitle")
        self.title_label.setWordWrap(False)

        self.time_label = QLabel(timestamp)
        self.time_label.setObjectName("ChatListItemTime")

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.time_label)
        layout.addLayout(text_layout, 1)

        # 3. Three-dots options button
        self.options_button = QPushButton("⋮")
        self.options_button.setObjectName("ChatListOptionsButton")
        self.options_button.setFixedSize(22, 22)
        self.options_button.setCursor(Qt.PointingHandCursor)
        self.options_button.clicked.connect(self.show_context_menu)
        layout.addWidget(self.options_button)

        self.refresh_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if clicked on options button area to avoid double triggering
            if not self.options_button.geometry().contains(event.pos()):
                self.clicked.emit(self.name)
        super().mousePressEvent(event)

    def set_active(self, active: bool) -> None:
        self.active = active
        self.refresh_style()

    def enterEvent(self, event):
        self.setProperty("hovered", True)
        self.refresh_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setProperty("hovered", False)
        self.refresh_style()
        super().leaveEvent(event)

    def show_context_menu(self):
        menu = QMenu(self)
        
        action_rename = menu.addAction("Přejmenovat")
        action_pin = menu.addAction("Připnout")
        action_export = menu.addAction("Exportovat")
        menu.addSeparator()
        action_delete = menu.addAction("Smazat")

        action_rename.triggered.connect(lambda: self.rename_requested.emit(self.name))
        action_pin.triggered.connect(lambda: self.pin_requested.emit(self.name))
        action_export.triggered.connect(lambda: self.export_requested.emit(self.name))
        action_delete.triggered.connect(lambda: self.delete_requested.emit(self.name))

        # Position menu next to the options button
        btn_pos = self.options_button.mapToGlobal(self.options_button.rect().bottomLeft())
        menu.exec(btn_pos)

    def refresh_style(self) -> None:
        hovered = self.property("hovered")
        self.icon_widget.set_states(self.active, hovered)

        if self.active:
            background = "rgba(14, 165, 233, 0.12)"
            border = "1px solid rgba(14, 165, 233, 0.25)"
            title_color = "#f8fafc"
            time_color = "#38bdf8"
            opts_color = "#38bdf8"
        elif hovered:
            background = "rgba(255, 255, 255, 0.04)"
            border = "1px solid rgba(255, 255, 255, 0.02)"
            title_color = "#e2e8f0"
            time_color = "#94a3b8"
            opts_color = "#94a3b8"
        else:
            background = "transparent"
            border = "1px solid transparent"
            title_color = "#94a3b8"
            time_color = "#475569"
            opts_color = "transparent"

        self.setStyleSheet(
            f"""
            QFrame#ChatListItem {{
                background: {background};
                border: {border};
                border-radius: 10px;
            }}
            QLabel#ChatListItemTitle {{
                color: {title_color};
                font-weight: 600;
                font-size: 13px;
            }}
            QLabel#ChatListItemTime {{
                color: {time_color};
                font-size: 11px;
            }}
            QPushButton#ChatListOptionsButton {{
                background: transparent;
                border: none;
                color: {opts_color};
                font-size: 15px;
                font-weight: bold;
                padding-bottom: 2px;
            }}
            QPushButton#ChatListOptionsButton:hover {{
                color: #38bdf8;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 4px;
            }}
            """
        )


class ChatListPanel(QFrame):
    chat_selected = Signal(str)
    
    # Internal signals to route to main window
    new_chat_clicked = Signal()
    delete_chat_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.items: dict[str, ChatListItem] = {}
        self.all_names: list[str] = []
        self.current_chat = ""
        self.setObjectName("ChatListPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # 1. Header layout
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 0)
        
        title = QLabel("CHATY")
        title.setObjectName("SectionTitle")
        
        self.new_button = QPushButton("+")
        self.new_button.setObjectName("GhostButton")
        self.new_button.setFixedSize(24, 24)
        self.new_button.setToolTip("Nový chat")
        self.new_button.setStyleSheet("font-size: 16px; font-weight: bold; padding: 0px;")

        self.delete_button = QPushButton("-")
        self.delete_button.setObjectName("GhostButton")
        self.delete_button.setFixedSize(24, 24)
        self.delete_button.setToolTip("Smazat aktuální chat")
        self.delete_button.setStyleSheet("font-size: 16px; font-weight: bold; padding: 0px;")

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.new_button)
        header.addWidget(self.delete_button)

        # 2. Search Input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Hledat chat...")
        self.search_input.setStyleSheet(
            """
            QLineEdit {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 8px;
                color: #f8fafc;
                font-size: 12px;
                padding: 4px 8px;
                min-height: 24px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(14, 165, 233, 0.3);
                background: rgba(255, 255, 255, 0.04);
            }
            """
        )
        self.search_input.textChanged.connect(self.filter_chats)

        # 3. Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.container)

        root.addLayout(header)
        root.addWidget(self.search_input)
        root.addWidget(self.scroll, 1)

    def update_chats(self, names: list[str], current_chat: str) -> None:
        self.current_chat = current_chat
        self.all_names = names
        
        # Clear existing items
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.items = {}
        
        # Generate simulated relative times for realism in design
        relative_times = ["20:32", "Včera", "Včera", "Před 3 dny", "Před 5 dny", "Před 7 dny"]
        
        for idx, name in enumerate(names):
            ts = relative_times[idx] if idx < len(relative_times) else "Před měsícem"
            # If the chat name matches active/created today, use current time
            if name == current_chat and idx == 0:
                ts = datetime.now().strftime("%H:%M")

            item = ChatListItem(name, timestamp=ts)
            item.clicked.connect(self.chat_selected.emit)
            item.set_active(name == current_chat)
            
            # Setup context menu hooks (routing delete to parent buttons / controller)
            item.delete_requested.connect(self.handle_item_delete)
            item.rename_requested.connect(self.handle_item_rename)
            item.export_requested.connect(self.handle_item_export)
            item.pin_requested.connect(self.handle_item_pin)

            self.items[name] = item
            self.list_layout.insertWidget(self.list_layout.count() - 1, item)
            
        self.filter_chats(self.search_input.text())

    def filter_chats(self, text: str):
        query = text.lower().strip()
        for name, item in self.items.items():
            if not query or query in name.lower():
                item.show()
            else:
                item.hide()

    def handle_item_delete(self, name: str):
        # Trigger parent deletion logic
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 
            "Smazat chat", 
            f"Opravdu chcete smazat konverzaci '{name}'?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # Emulate clicking delete or routing to controller
            parent_window = self.window()
            if hasattr(parent_window, "controller"):
                parent_window.controller.delete_chat(name)

    def handle_item_rename(self, name: str):
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, 
            "Přejmenovat chat", 
            "Zadejte nový název chatu:", 
            QLineEdit.Normal, 
            name
        )
        if ok and new_name.strip():
            parent_window = self.window()
            if hasattr(parent_window, "controller"):
                controller = parent_window.controller
                # Rename key in chats dict and save
                if name in controller.chats:
                    controller.chats[new_name.strip()] = controller.chats.pop(name)
                    from core.memory import CHATS_FILE, save_json
                    save_json(CHATS_FILE, controller.chats)
                    if controller.current_chat == name:
                        controller.current_chat = new_name.strip()
                    controller.emit_chat_list()
                    controller.load_chat(controller.current_chat)

    def handle_item_export(self, name: str):
        # Mock export hook
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, 
            "Export chatu", 
            f"Export konverzace '{name}' byl úspěšně dokončen (uloženo do export_history.json)."
        )

    def handle_item_pin(self, name: str):
        # Mock pin hook
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, 
            "Připnout chat", 
            f"Konverzace '{name}' byla připnuta na vrchol seznamu."
        )

    def selected_chat(self) -> str:
        return self.current_chat
