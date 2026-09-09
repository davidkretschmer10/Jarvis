import random
import re
import threading
import time
import unicodedata

from PySide6.QtCore import QObject, QTimer, Signal

from ai.engine import generate_stream
from ai.model_manager import save_settings
from ai.prompts.master_prompt import build_user_task_prompt
from core.memory import CHATS_FILE, PROFILE_FILE, load_json, save_json, update_profile
from core.runtime import JarvisRuntime
from interfaces.voice import (
    interrupt_speech,
    listen_once_to_text,
    speak,
    speech_to_text as vs_stt,
    start_recording as vs_start,
    stop_wake_listener,
    stop_recording as vs_stop,
    wake_listener,
)

try:
    from interfaces.voice import speak_stream as voice_speak_stream
except ImportError:
    def voice_speak_stream(chunks):
        return "".join(chunks)


def _emit_stream(chunks, callback):
    for chunk in chunks:
        callback(chunk)
        yield chunk


class GuiController(QObject):
    chunk_received = Signal(str)
    start_ai_bubble = Signal()
    end_ai_bubble = Signal()
    user_message_received = Signal(str)
    system_message_received = Signal(str)
    status_changed = Signal(str)
    chat_loaded = Signal(list, str)
    chat_list_updated = Signal(list, str)
    audio_volume = Signal(int)
    audio_volume_zero = Signal()
    voice_status_changed = Signal(str)
    clear_input = Signal()
    ollama_status_changed = Signal(dict)
    vision_status_changed = Signal(str)
    
    # Task progress tracking signals
    task_started = Signal(str, list)
    step_updated = Signal(int, str)
    task_finished = Signal(bool, str)

    def __init__(self, event_bus):
        super().__init__()
        self.event_bus = event_bus
        self.event_bus.on("user_message", self.handle_user_message)
        self.event_bus.on("ai_request", self.process_ai_request)
        self.event_bus.on("agent_request", self.process_agent_request)
        self.event_bus.on("verification_started", self._on_verification_started)
        self.event_bus.on("verification_completed", self._on_verification_completed)
        self.event_bus.on("verification_failed", self._on_verification_failed)
        self.event_bus.on("step_repair", self._on_step_repair)
        self.event_bus.on("replanning_started", self._on_replanning_started)
        self.chats = load_json(CHATS_FILE)

        for chat in self.chats:
            if isinstance(self.chats[chat], list):
                self.chats[chat] = {"messages": self.chats[chat], "model": "auto"}
            elif isinstance(self.chats[chat], dict) and "model" not in self.chats[chat]:
                self.chats[chat]["model"] = "auto"

        if not self.chats:
            self.chats = {"Chat": {"messages": [], "model": "auto"}}

        self.profile = load_json(PROFILE_FILE) or []
        self.current_chat = list(self.chats.keys())[0]
        self.recording = False
        self.voice_active = False
        self._voice_chat_lock = threading.RLock()
        try:
            from interfaces.voice import set_event_bus
            set_event_bus(event_bus)
        except Exception:
            pass
        self.runtime = JarvisRuntime(event_bus=event_bus)
        self.voice_read_enabled = False
        self.pending_router_choice = None

        # Check Tesseract status
        from vision.tesseract_validator import check_tesseract
        self.tesseract_ok, self.tesseract_msg = check_tesseract()

        self._ollama_status_timer = QTimer(self)
        self._ollama_status_timer.setInterval(5000)
        self._ollama_status_timer.timeout.connect(self.refresh_ollama_status)
        self._ollama_status_timer.start()
        self.refresh_ollama_status()

    def emit_vision_status(self):
        self.vision_status_changed.emit(self.tesseract_msg)

    def _on_verification_started(self, data):
        self.status_changed.emit("Ověřuji...")

    def _on_verification_completed(self, data):
        st = data.get("status", "")
        if st == "VERIFIED":
            self.status_changed.emit("Ověřeno")
        elif st == "UNKNOWN":
            self.status_changed.emit("Provádím...")

    def _on_verification_failed(self, data):
        self.status_changed.emit("Ověření selhalo")

    def _on_step_repair(self, data):
        self.status_changed.emit("Opravuji...")

    def _on_replanning_started(self, data):
        self.status_changed.emit("Přeplánovávám...")

    def refresh_ollama_status(self):
        def status_task():
            from ai.engine import get_ollama_status
            self.ollama_status_changed.emit(get_ollama_status())

        threading.Thread(target=status_task, daemon=True).start()

    def emit_chat_list(self):
        self.chat_list_updated.emit(list(self.chats.keys()), self.current_chat)

    def load_chat(self, name):
        if name in self.chats:
            self.current_chat = name
            messages = self.chats[name]["messages"]
            model = self.chats[name].get("model", "auto")
            self.chat_loaded.emit(messages, model)

    def new_chat(self):
        name = f"Chat {len(self.chats) + 1}"
        self.chats[name] = {"messages": [], "model": "auto"}
        save_json(CHATS_FILE, self.chats)
        self.current_chat = name
        self.emit_chat_list()
        self.load_chat(name)

    def delete_chat(self, name):
        if name in self.chats and len(self.chats) > 1:
            del self.chats[name]
            save_json(CHATS_FILE, self.chats)
            self.current_chat = list(self.chats.keys())[0]
            self.emit_chat_list()
            self.load_chat(self.current_chat)

    def change_model(self, model):
        self.chats[self.current_chat]["model"] = model
        save_json(CHATS_FILE, self.chats)

    def build_prompt(self, text):
        history = self.chats[self.current_chat]["messages"][-10:]
        return build_user_task_prompt(
            user_text=text,
            history=history,
            profile_facts=self.profile,
        )

    def handle_router_preference_choice(self, message: str) -> bool:
        if hasattr(self, "pending_router_choice") and self.pending_router_choice:
            from core.intents.target_extractor import normalize_text
            from core.intents.fast_command_router import save_user_preference, increment_router_stat
            
            choice = normalize_text(message)
            candidates = self.pending_router_choice["candidates"]
            matched_candidate = None
            for cand in candidates:
                norm_cand = normalize_text(cand)
                if norm_cand in choice or choice in norm_cand:
                    matched_candidate = cand
                    break
            
            if matched_candidate:
                query_key = self.pending_router_choice["query"]
                save_user_preference(query_key, matched_candidate.lower())
                
                # Log stats confirmation
                increment_router_stat("FAST_COMMAND", confirmation=True)
                
                orig_text = self.pending_router_choice["original_text"]
                self.pending_router_choice = None
                
                # Re-run original command now that the preference is saved
                self.handle_user_message(orig_text)
                return True
            else:
                self.pending_router_choice = None
        return False

    def handle_user_message(self, message: str):
        if not message:
            return

        from ai.engine import reset_current_request
        reset_current_request()

        self.user_message_received.emit(message)
        self.chats[self.current_chat]["messages"].append(f"Ty: {message}")

        if self.handle_router_preference_choice(message):
            self.clear_input.emit()
            return

        if hasattr(self, "paused_task") and self.paused_task:
            reply = message.strip().lower()
            clean_reply = "".join(
                c for c in unicodedata.normalize("NFD", reply)
                if unicodedata.category(c) != "Mn"
            )
            is_yes = clean_reply in ("ano", "jo", "yes", "pokracovat", "y")
            
            task_info = self.paused_task
            state = task_info["state"]
            pending_candidates = state.data.get("pending_candidates", [])
            chosen_candidate = None
            
            if pending_candidates:
                if is_yes:
                    chosen_candidate = pending_candidates[0]
                else:
                    for cand in pending_candidates:
                        cand_name = cand["name"].lower()
                        clean_cand = "".join(
                            c for c in unicodedata.normalize("NFD", cand_name)
                            if unicodedata.category(c) != "Mn"
                        )
                        if clean_reply == clean_cand or clean_reply in clean_cand or clean_cand in clean_reply:
                            chosen_candidate = cand
                            break
            
            if is_yes or chosen_candidate:
                self.paused_task = None
                if chosen_candidate:
                    state.data["pending_app_path"] = chosen_candidate["path"]
                    state.data["pending_app_name"] = chosen_candidate["name"]

                req_ctx = task_info.get("request_context")

                def resume_task():
                    if req_ctx:
                        from core.lifecycle import set_current_request
                        set_current_request(req_ctx)

                    self.status_changed.emit("Provadim...")
                    self.start_ai_bubble.emit()

                    def update_gui(idx: int, status: str):
                        self.step_updated.emit(idx, status)

                    try:
                        result = self.runtime.resume_task(
                            goal=task_info["goal"],
                            steps=task_info["steps"],
                            state=state,
                            start_index=task_info["step_index"],
                            on_step_update=update_gui,
                            on_task_start=lambda task_goal, steps: self.task_started.emit(task_goal, steps),
                            expected_request_id=task_info.get("request_id"),
                            request_context=req_ctx,
                        )
                    except Exception as e:
                        summary = f"Neocekavana chyba pri provadeni ukolu: {e}"
                        success = False
                    else:
                        summary = result.summary
                        success = result.ok
                        if result.pending_confirmation:
                            self.paused_task = {
                                "steps": result.steps,
                                "state": result.state,
                                "step_index": result.state.data.get("paused_step_index", 0),
                                "goal": result.goal,
                                "request_id": result.request_id,
                                "request_context": req_ctx,
                            }

                    self.chunk_received.emit(summary)
                    if self.voice_read_enabled:
                        speak(summary)
                    self.end_ai_bubble.emit()
                    self.chats[self.current_chat]["messages"].append(f"Jarvis: {summary}")
                    save_json(CHATS_FILE, self.chats)
                    self.status_changed.emit("Ready")
                    self.task_finished.emit(success, summary)
                    self.event_bus.emit("ai_response", summary)

                threading.Thread(target=resume_task, daemon=True).start()
                self.clear_input.emit()
                return
            else:
                req_id = task_info.get("request_id")
                if hasattr(self.runtime, "cancel_task"):
                    self.runtime.cancel_task(request_id=req_id, reason="User denied confirmation")
                self.paused_task = None
                cancel_msg = "Úkol byl zrušen."
                self.chunk_received.emit(cancel_msg)
                self.chats[self.current_chat]["messages"].append(f"Jarvis: {cancel_msg}")
                save_json(CHATS_FILE, self.chats)
                self.status_changed.emit("Ready")
                self.task_finished.emit(False, cancel_msg)
                self.event_bus.emit("ai_response", cancel_msg)
                self.clear_input.emit()
                return

        from core.intents import IntentType, classify_intent
        parsed = classify_intent(message)

        if parsed.intent != IntentType.CHAT and not parsed.requires_llm:
            self.process_agent_request(parsed)
            return

        self.process_ai_request(message)

    def process_request(self, message: str, source: str = "gui", voice_output: bool = False):
        from core.lifecycle import reset_current_request, set_current_request

        self.clear_input.emit()
        self.profile = update_profile(self.profile, message)
        save_json(PROFILE_FILE, self.profile)

        req_ctx = reset_current_request(goal=message, source=source)

        def task_worker():
            set_current_request(req_ctx)
            self.status_changed.emit("Premyslim...")
            self.start_ai_bubble.emit()

            def update_gui(idx: int, status: str):
                self.step_updated.emit(idx, status)

            def on_chunk(chunk: str):
                self.chunk_received.emit(chunk)

            try:
                result = self.runtime.run_task(
                    message,
                    on_step_update=update_gui,
                    on_task_start=lambda task_goal, steps: self.task_started.emit(task_goal, steps),
                    on_chunk=on_chunk,
                    reset_request=False,
                    request_context=req_ctx,
                )
            except Exception as e:
                summary = f"Neocekavana chyba pri provadeni ukolu: {e}"
                self.chunk_received.emit(summary)
                self.end_ai_bubble.emit()
                self.status_changed.emit("Ready")
                self.chats[self.current_chat]["messages"].append(f"Jarvis: {summary}")
                save_json(CHATS_FILE, self.chats)
                self.task_finished.emit(False, summary)
                self.event_bus.emit("ai_response", summary)
                return

            reply_text = getattr(result, "response_text", "") or getattr(result, "summary", "")

            if getattr(result, "pending_confirmation", False) and getattr(result, "state", None) and result.state.data.get("router_candidates"):
                from core.intents.target_extractor import normalize_text

                self.pending_router_choice = {
                    "query": "prohlizec" if "prohlizec" in normalize_text(message) else "browser",
                    "candidates": result.state.data.get("router_candidates", []),
                    "original_text": message,
                }
                prompt_msg = getattr(result, "confirmation_message", "") + "\nKtery chces otevrit?"
                self.chunk_received.emit(prompt_msg)
                self.end_ai_bubble.emit()
                self.chats[self.current_chat]["messages"].append(f"Jarvis: {prompt_msg}")
                save_json(CHATS_FILE, self.chats)
                self.status_changed.emit("Ready")
                self.event_bus.emit("ai_response", prompt_msg)
                if self.voice_read_enabled or voice_output or (hasattr(self, "voice_active") and self.voice_active):
                    speak(prompt_msg)
                return

            if getattr(result, "pending_confirmation", False):
                self.paused_task = {
                    "steps": getattr(result, "steps", []),
                    "state": getattr(result, "state", None),
                    "step_index": result.state.data.get("paused_step_index", 0) if getattr(result, "state", None) else 0,
                    "goal": message,
                    "request_id": getattr(result, "request_id", ""),
                    "request_context": req_ctx,
                }

            if getattr(result, "route", "") != "CHAT":
                self.chunk_received.emit(reply_text)

            if self.voice_read_enabled or voice_output or (hasattr(self, "voice_active") and self.voice_active):
                speak(reply_text)

            self.end_ai_bubble.emit()
            self.chats[self.current_chat]["messages"].append(f"Jarvis: {reply_text}")
            save_json(CHATS_FILE, self.chats)
            self.status_changed.emit("Ready")
            self.task_finished.emit(getattr(result, "ok", False), reply_text)
            self.event_bus.emit("ai_response", reply_text)

            if getattr(result, "route", "") == "FAST_COMMAND" and hasattr(self, "voice_active") and self.voice_active:
                self.stop_voice_chat()

        t = threading.Thread(target=task_worker, daemon=True, name="UnifiedRequestWorker")
        t.start()
        return t

    def process_agent_request(self, parsed):
        goal = parsed.original_text if hasattr(parsed, "original_text") else str(parsed)
        return self.process_request(goal, source="gui_agent")

    def process_ai_request(self, message: str):
        return self.process_request(message, source="gui_chat")

    def start_recording(self):
        interrupt_speech()
        self.system_message_received.emit("Recording...")
        self.audio_volume_zero.emit()

        def volume_callback(volume):
            self.audio_volume.emit(volume)

        vs_start(volume_callback)

    def stop_recording(self):
        vs_stop()
        self.audio_volume_zero.emit()

    def send_voice(self):
        self.status_changed.emit("Transcribing...")
        def transcribe_task():
            text = vs_stt()

            if not text or text.strip() == "":
                self.system_message_received.emit("Jarvis: nerozumel jsem nebo nic nebylo nahrano")
                self.status_changed.emit("Ready")
                return

            self.handle_voice_text(text)

        threading.Thread(target=transcribe_task, daemon=True).start()

    def handle_voice_text(self, text: str):
        self.user_message_received.emit(f"Voice: {text}")
        self.chats[self.current_chat]["messages"].append(f"Ty: {text}")
        save_json(CHATS_FILE, self.chats)

        if self.handle_router_preference_choice(text):
            return None

        # Route through unified request handler
        worker = self.process_request(text, source="voice", voice_output=True)
        return worker

    def start_voice_chat(self):
        with self._voice_chat_lock:
            if self.voice_active:
                return
            self.voice_active = True
            self.voice_status_changed.emit("Voice: Listening")
            threading.Thread(target=self.voice_conversation_loop, daemon=True, name="VoiceConversationLoop").start()

    def stop_voice_chat(self):
        with self._voice_chat_lock:
            if not self.voice_active:
                return
            self.voice_active = False
            interrupt_speech()
            vs_stop()
            self.voice_status_changed.emit("Voice: Disconnected")

    def voice_conversation_loop(self):
        while self.voice_active:
            def volume_callback(volume):
                self.audio_volume.emit(volume)

            self.audio_volume_zero.emit()
            self.status_changed.emit("Listening...")
            text = listen_once_to_text(volume_callback)
            if not text:
                continue

            self.handle_voice_text(text)
            time.sleep(0.1)

    def toggle_wake_word(self, state):
        if state:
            self.system_message_received.emit("Wake word listening enabled")
            self.start_wake_listener()
        else:
            stop_wake_listener()
            self.system_message_received.emit("Wake word disabled")

    def start_wake_listener(self):
        wake_listener(self.on_wake_word)

    def on_wake_word(self):
        self.system_message_received.emit("Wake word detected")
        threading.Thread(target=self.handle_wake_capture, daemon=True).start()

    def handle_wake_capture(self):
        self.status_changed.emit("Listening...")
        self.audio_volume_zero.emit()

        def volume_callback(volume):
            self.audio_volume.emit(volume)

        text = listen_once_to_text(volume_callback)
        self.audio_volume_zero.emit()
        if text:
            self.handle_voice_text(text)
        else:
            self.system_message_received.emit("Jarvis: nerozumel jsem nebo nic nebylo nahrano")
            self.status_changed.emit("Ready")

    def set_voice_read_enabled(self, state):
        self.voice_read_enabled = bool(state)

    def update_settings(self, settings):
        settings.setdefault("personality", "jarvis")
        save_settings(settings)
