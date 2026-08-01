from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Qt, Slot, QVariantAnimation
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

from interfaces.gui.chat_widget import ChatWidget
from interfaces.gui.models_widget import ModelsWidget
from interfaces.gui.settings_widget import SettingsWidget
from interfaces.gui.sidebar.navigation import TopNavigationBar
from interfaces.gui.sidebar.sliding_panel import SlidingChatPanel
from interfaces.gui.themes.jarvis_theme import JARVIS_QSS
from interfaces.gui.voice_widget import VoiceWidget
from interfaces.gui.widgets.edge_handle import EdgeHandle
from interfaces.gui.widgets.effects import apply_soft_shadow
from interfaces.gui.widgets.panel import Panel
from interfaces.gui.widgets.slide_stack import SlideStack
from interfaces.gui.widgets.task_progress import TaskProgressWidget


class JarvisMainWindow(QMainWindow):
    def __init__(self, controller, event_bus):
        super().__init__()
        self.controller = controller
        self.event_bus = event_bus
        self.nav_bars: dict[str, TopNavigationBar] = {}
        self.status_labels: list[QLabel] = []
        self.info_body_labels: dict[str, QLabel] = {}
        self.setWindowTitle("Jarvis")
        self.resize(1440, 860)
        self.setMinimumSize(1100, 680)
        self.setup_ui()
        self.connect_signals()
        self.controller.emit_chat_list()
        self.controller.load_chat(self.controller.current_chat)
        self.controller.emit_vision_status()

    def setup_ui(self):
        self.setStyleSheet(JARVIS_QSS)

        shell = QFrame()
        shell.setObjectName("AppShell")
        self.setCentralWidget(shell)

        self.root_layout = QVBoxLayout(shell)
        self.root_layout.setContentsMargins(14, 14, 14, 14)
        self.root_layout.setSpacing(0)

        self.split_layout = QHBoxLayout()
        self.split_layout.setContentsMargins(0, 0, 0, 0)
        self.split_layout.setSpacing(14)

        self.chat_drawer = SlidingChatPanel(self)
        self.split_layout.addWidget(self.chat_drawer)

        self.drawer_handle = EdgeHandle("left", self)
        self.drawer_handle.clicked.connect(self.toggle_chat_drawer)
        self.split_layout.addWidget(self.drawer_handle, 0, Qt.AlignVCenter)

        self.main_surface = QFrame()
        self.main_surface.setObjectName("MainSurface")
        apply_soft_shadow(self.main_surface, blur=42, y_offset=16, strength=86)

        self.surface_layout = QVBoxLayout(self.main_surface)
        self.surface_layout.setContentsMargins(0, 0, 0, 0)
        self.surface_layout.setSpacing(0)

        self.stack = SlideStack()
        self.pages: dict[str, QWidget] = {}
        self.build_pages()
        self.surface_layout.addWidget(self.stack, 1)

        self.split_layout.addWidget(self.main_surface, 1)

        self.info_handle = EdgeHandle("right", self)
        self.info_handle.clicked.connect(self.toggle_info_panel)
        self.split_layout.addWidget(self.info_handle, 0, Qt.AlignVCenter)

        self.info_panel = self.build_info_panel()
        self.split_layout.addWidget(self.info_panel)
        self.root_layout.addLayout(self.split_layout, 1)

    def build_pages(self):
        self.chat_widget = ChatWidget(self.controller, self.event_bus)
        self.voice_widget = VoiceWidget(self.controller, self.event_bus)
        self.settings_widget = SettingsWidget(self.controller, self.event_bus)
        self.models_widget = ModelsWidget(self.controller)

        self.pages["chat"] = self.build_standard_page("chat", self.chat_widget, title="Jarvis chat", status=True)
        self.pages["voice"] = self.build_voice_page()
        self.pages["settings"] = self.build_standard_page("settings", self.settings_widget)
        self.pages["models"] = self.build_standard_page("models", self.models_widget)
        self.pages["memory"] = self.build_standard_page("memory", self.build_memory_content())
        self.pages["tools"] = self.build_standard_page("tools", self.build_tools_content())

        for key, page in self.pages.items():
            self.stack.add_page(key, page)
        self.sync_navigation("chat")

    def make_nav(self, active_key: str) -> TopNavigationBar:
        nav = TopNavigationBar(self)
        nav.section_changed.connect(self.show_section)
        nav.set_active(active_key)
        self.nav_bars[active_key] = nav
        return nav

    def build_nav_row(self, active_key: str) -> QWidget:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addStretch()
        row_layout.addWidget(self.make_nav(active_key))
        row_layout.addStretch()
        return row_widget

    def build_standard_page(self, key: str, widget: QWidget, title: str = "", status: bool = False) -> QWidget:
        page = QWidget()
        page.setObjectName("PageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 20, 26, 22)
        layout.setSpacing(12)
        layout.addWidget(self.build_nav_row(key))

        panel = Panel(margins=(18, 18, 18, 18))
        if title or status:
            header = QFrame()
            header.setObjectName("TopBar")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(2, 0, 2, 8)
            title_label = QLabel(title or key.title())
            title_label.setObjectName("PageTitle")
            header_layout.addWidget(title_label)
            header_layout.addStretch()
            if status:
                status_label = QLabel("Ready")
                status_label.setObjectName("StatusPill")
                self.status_labels.append(status_label)
                header_layout.addWidget(status_label)
            panel.layout.addWidget(header)
        panel.layout.addWidget(widget)
        layout.addWidget(panel, 1)
        return page

    def build_voice_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("VoicePageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_nav_row("voice"))
        layout.addWidget(self.voice_widget, 1)
        return page

    def build_memory_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Paměť asistenta")
        title.setObjectName("SectionTitle")
        profile_count = len(self.controller.profile)
        chat_count = len(self.controller.chats)
        current = self.controller.current_chat
        summary = QLabel(
            f"Uložené profily: {profile_count}\n"
            f"Konverzace: {chat_count}\n"
            f"Aktuální chat: {current}"
        )
        summary.setObjectName("MutedLabel")
        layout.addWidget(title)
        layout.addWidget(summary)
        layout.addStretch()
        return content

    def build_tools_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Nástroje")
        title.setObjectName("SectionTitle")
        tools = QLabel("Web routing\nPC control agent\nFile manager\nScreenshot / OCR pipeline\nVoice STT / TTS")
        tools.setObjectName("MutedLabel")
        layout.addWidget(title)
        layout.addWidget(tools)
        layout.addStretch()
        return content

    def build_info_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("RightInfoPanel")
        panel.setFixedWidth(0)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        # Task memory & steps viewer
        self.task_progress_widget = TaskProgressWidget()
        layout.addWidget(self.task_progress_widget)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.05); max-height: 1px;")
        layout.addWidget(sep)

        blocks = [
            ("system", "SYSTÉM", "Režim: pracovní chat\nCPU/GPU: připraveno\nLokální služby: aktivní"),
            ("ai", "STAV AI", "Stav: Ready\nAktivní model: neznámý\nOllama: kontroluji..."),
            ("vision", "VISION", "OCR: Kontroluji..."),
            ("voice", "VOICE", "STT: připraveno\nTTS: připraveno\nWake word: podle nastavení"),
        ]
        for block in blocks:
            key, title_text, body_text = block
            title_label = QLabel(title_text)
            title_label.setObjectName("InfoTitle")
            body_label = QLabel(body_text)
            body_label.setObjectName("InfoBody")
            body_label.setWordWrap(True)
            self.info_body_labels[key] = body_label
            layout.addWidget(title_label)
            layout.addWidget(body_label)
        layout.addStretch()
        return panel

    def connect_signals(self):
        self.chat_drawer.chat_list.new_button.clicked.connect(self.controller.new_chat)
        self.chat_drawer.chat_list.delete_button.clicked.connect(self.delete_current_chat)
        self.chat_drawer.chat_list.chat_selected.connect(self.controller.load_chat)
        self.controller.status_changed.connect(self.update_assistant_state)
        self.controller.ollama_status_changed.connect(self.update_ollama_status)
        self.controller.vision_status_changed.connect(self.update_vision_status)
        self.controller.chat_list_updated.connect(self.update_chat_list)
        self.settings_widget.back_button.clicked.connect(lambda: self.show_section("chat"))
        
        # Task Progress Widget signals
        self.controller.task_started.connect(self._on_task_started)
        self.controller.step_updated.connect(self.task_progress_widget.update_step)
        self.controller.task_finished.connect(self._on_task_finished)
        
        for model_box in self.models_widget.model_boxes.values():
            model_box.stateChanged.connect(self.update_model_page_settings)
        for mode_button in self.models_widget.mode_group.buttons():
            mode_button.toggled.connect(self.update_model_page_settings)

    def _on_task_started(self, title: str, steps: list[str] | list[dict]):
        self.task_progress_widget.set_task(title, steps)
        self.show_info_panel(True)

    def _on_task_finished(self, success: bool, message: str):
        # We keep the completed checklist on screen for user visual feedback.
        pass

    def show_info_panel(self, show: bool = True):
        current_w = self.info_panel.width()
        target_w = 300 if show else 0
        if current_w == target_w:
            return

        if not hasattr(self, "_info_anim"):
            self._info_anim = QVariantAnimation(self)
            self._info_anim.setDuration(260)
            self._info_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._info_anim.valueChanged.connect(lambda value: self.info_panel.setFixedWidth(int(value)))

        self._info_anim.stop()
        self._info_anim.setStartValue(current_w)
        self._info_anim.setEndValue(target_w)
        self._info_anim.start()
        self.info_handle.set_open(show)

    def update_assistant_state(self, status: str):
        for label in self.status_labels:
            label.setText(status)
        lower = status.lower()
        if "listening" in lower or "posloucham" in lower or "poslouchám" in lower:
            state = "listening"
        elif "thinking" in lower or "premyslim" in lower or "přemýšlím" in lower or "transcribing" in lower:
            state = "thinking"
        elif "speaking" in lower or "mluvim" in lower or "mluvím" in lower:
            state = "speaking"
        else:
            state = "ready"
        for nav in self.nav_bars.values():
            nav.logo.set_state(state)

    @Slot(dict)
    def update_ollama_status(self, status: dict):
        label = self.info_body_labels.get("ai")
        if not label:
            return
        running = "běží" if status.get("running") else "neběží"
        active_model = status.get("active_model") or "neznámý"
        downloading = status.get("downloading_model") or "žádné"
        error = status.get("error") or "žádná"
        label.setText(
            f"Ollama: {running}\n"
            f"Aktivní model: {active_model}\n"
            f"Stahování modelu: {downloading}\n"
            f"Chyba: {error}"
        )

    @Slot(str)
    def update_vision_status(self, status: str):
        label = self.info_body_labels.get("vision")
        if label:
            label.setText(f"OCR: {status}")

    def sync_navigation(self, key: str):
        for nav in self.nav_bars.values():
            nav.set_active(key)

    def show_section(self, key: str):
        if key not in self.pages:
            return

        previous_key = self.stack.current_key or "chat"
        to_voice = key == "voice"
        from_voice = previous_key == "voice" and key != "voice"

        if to_voice:
            self.root_layout.setContentsMargins(0, 0, 0, 0)
            self.split_layout.setSpacing(0)
            self.chat_drawer.hide()
            self.drawer_handle.hide()
            self.info_handle.hide()
            self.info_panel.hide()
            self.main_surface.setStyleSheet("QFrame#MainSurface { border: none; background: transparent; }")
            if self.main_surface.graphicsEffect():
                self.main_surface.graphicsEffect().setEnabled(False)
        elif from_voice:
            self.root_layout.setContentsMargins(14, 14, 14, 14)
            self.split_layout.setSpacing(14)
            self.chat_drawer.show()
            self.drawer_handle.show()
            self.info_handle.show()
            self.info_panel.show()
            self.main_surface.setStyleSheet("")
            if self.main_surface.graphicsEffect():
                self.main_surface.graphicsEffect().setEnabled(True)

        self.sync_navigation(key)
        self.stack.set_current(key, animated=True)

        if key == "memory":
            self.refresh_memory_page()

    def toggle_chat_drawer(self):
        current_w = self.chat_drawer.width()
        target_w = 310 if current_w == 0 else 0

        if not hasattr(self, "_drawer_anim"):
            self._drawer_anim = QVariantAnimation(self)
            self._drawer_anim.setDuration(260)
            self._drawer_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._drawer_anim.valueChanged.connect(lambda value: self.chat_drawer.setFixedWidth(int(value)))

        self._drawer_anim.stop()
        self._drawer_anim.setStartValue(current_w)
        self._drawer_anim.setEndValue(target_w)
        self._drawer_anim.start()
        self.drawer_handle.set_open(target_w == 310)

    def toggle_info_panel(self):
        current_w = self.info_panel.width()
        target_w = 300 if current_w == 0 else 0

        if not hasattr(self, "_info_anim"):
            self._info_anim = QVariantAnimation(self)
            self._info_anim.setDuration(260)
            self._info_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._info_anim.valueChanged.connect(lambda value: self.info_panel.setFixedWidth(int(value)))

        self._info_anim.stop()
        self._info_anim.setStartValue(current_w)
        self._info_anim.setEndValue(target_w)
        self._info_anim.start()
        self.info_handle.set_open(target_w == 300)

    def refresh_memory_page(self):
        content = self.build_memory_content()
        page = self.build_standard_page("memory", content)
        self.pages["memory"] = page
        self.stack.replace_page("memory", page)
        self.sync_navigation("memory")

    def delete_current_chat(self):
        name = self.chat_drawer.chat_list.selected_chat()
        if name:
            self.controller.delete_chat(name)

    def update_model_page_settings(self):
        settings = {
            "mode": self.models_widget.get_mode(),
            "response_mode": "balanced",
            "enabled_models": self.models_widget.get_enabled_models(),
        }
        self.controller.update_settings(settings)

    @Slot(list, str)
    def update_chat_list(self, names, current_chat):
        self.chat_drawer.chat_list.update_chats(names, current_chat)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.show_section("chat")
        super().keyPressEvent(event)
