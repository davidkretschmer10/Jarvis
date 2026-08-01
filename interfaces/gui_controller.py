import random
import re
import threading
import time
import unicodedata

from PySide6.QtCore import QObject, QTimer, Signal

from ai.engine import generate_stream, send_agent_command
from ai.model_manager import save_settings
from ai.prompts.master_prompt import build_user_task_prompt
from core.autonomous_agent import AutonomousAgent
from core.memory import CHATS_FILE, PROFILE_FILE, load_json, save_json, update_profile
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
        self.agent = AutonomousAgent()
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
                
                def resume_task():
                    self.status_changed.emit("Provádím...")
                    self.start_ai_bubble.emit()
                    
                    state.data["action_confirmed"] = True
                    steps = task_info["steps"]
                    start_idx = task_info["step_index"]
                    
                    # We execute remaining steps
                    remaining_steps = steps[start_idx:]
                    executor = task_info["executor"]
                    
                    state.data.pop("user_help_required", None)
                    state.data.pop("paused_step_index", None)
                    
                    try:
                        results = executor.run_plan(remaining_steps)
                        if "paused_step_index" in state.data:
                            # Paused again
                            self.paused_task = {
                                "steps": steps,
                                "state": state,
                                "step_index": start_idx + state.data["paused_step_index"],
                                "executor": executor,
                                "goal": task_info["goal"]
                            }
                            prompt_msg = state.data.get("user_help_required", "Akce vyžaduje potvrzení.")
                            self.chunk_received.emit(prompt_msg)
                            self.end_ai_bubble.emit()
                            self.chats[self.current_chat]["messages"].append(f"Jarvis: {prompt_msg}")
                            save_json(CHATS_FILE, self.chats)
                            self.status_changed.emit("Ready")
                            self.event_bus.emit("ai_response", prompt_msg)
                            return
                            
                        help_required = state.data.get("user_help_required")
                        if help_required:
                            summary = f"Chyba během provádění: {help_required}"
                            success = False
                        else:
                            if results and not results[-1]["output"].get("ok", False):
                                summary = f"Úkol selhal na kroku {start_idx + len(results)}: {results[-1]['output'].get('error', 'Neznámá chyba')}"
                                success = False
                            else:
                                summary = f"Úkol byl úspěšně dokončen! Celkem provedeno {len(steps)} kroků."
                                success = True
                    except Exception as e:
                        summary = f"Neočekávaná chyba při provádění úkolu: {e}"
                        success = False

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

        self.event_bus.emit("ai_request", message)

    def process_agent_request(self, parsed):
        self.clear_input.emit()
        
        def agent_task():
            import time
            import logging
            from run import build_registry
            from core.executor import Executor
            from core.task_memory import TaskMemory
            from core.state import JarvisState
            from tools.base import ToolContext
            from core.intents.fast_command_router import (
                classify_routing_level,
                increment_router_stat
            )
            from core.intents.target_extractor import normalize_text
            import os
            
            goal = parsed.original_text
            reg = build_registry()
            
            # 1. Routing classification
            start_time = time.perf_counter()
            route_info = classify_routing_level(goal)
            level = route_info["route"]
            confidence = route_info["confidence"]
            step = route_info["step"]
            candidates = route_info["candidates"]
            
            print(f"[ROUTER] {level}")
            
            # Handle confidence < 0.70 confirmation request
            if confidence < 0.70 and candidates:
                self.pending_router_choice = {
                    "query": "prohlizec" if "prohlizec" in normalize_text(goal) else "browser",
                    "candidates": candidates,
                    "original_text": goal
                }
                
                # Prompt user for choices
                prompt_msg = f"Nalezl jsem více možností:\n" + "\n".join([f"* {c}" for c in candidates]) + "\nKterý chceš otevřít?"
                self.chunk_received.emit(prompt_msg)
                self.end_ai_bubble.emit()
                self.chats[self.current_chat]["messages"].append(f"Jarvis: {prompt_msg}")
                save_json(CHATS_FILE, self.chats)
                self.status_changed.emit("Ready")
                self.event_bus.emit("ai_response", prompt_msg)
                
                # Speak it if voice read enabled or voice is active
                if self.voice_read_enabled or (hasattr(self, "voice_active") and self.voice_active):
                    speak(prompt_msg)
                return

            # Execute, and warning log if 0.70 <= confidence < 0.90
            if 0.70 <= confidence < 0.90:
                msg = f"Low confidence routing: {confidence:.2f} for route {level}"
                print(f"[WARNING] {msg}")
                logging.getLogger(__name__).warning(msg)

            steps = []
            use_task_memory = False
            fallback_occurred = False
            fallback_reason = None
            
            if level == "FAST_COMMAND":
                if step:
                    steps = [step]
                    from ai.engine import get_current_request
                    req_id = get_current_request().request_id
                    app_name = step["input"].get("name") or step["input"].get("url") or goal
                    print(f"[FAST_COMMAND]\nSTART\n\nTool:\n{step['tool']}\n\nApplication:\n{app_name}\n\nConfidence:\n{confidence:.2f}\n\nRequest ID:\n{req_id}\n")
                else:
                    # In case step is None but matched FAST_COMMAND, we fallback to MINI_PLANNER
                    level = "MINI_PLANNER"
                    fallback_occurred = True
                    fallback_reason = "FAST_COMMAND step was not generated"
                    print(f"[ROUTER] FALLBACK FAST_COMMAND -> MINI_PLANNER: {fallback_reason}")
            
            if level == "MINI_PLANNER":
                from core.planner import Planner
                planner = Planner(registry=reg)
                try:
                    steps = planner.plan(goal)
                    if len(steps) > 5 or not steps:
                        # Fallback to PLANNER_V2
                        level = "PLANNER_V2"
                        fallback_occurred = True
                        fallback_reason = "plan contains more than 5 steps" if steps else "empty plan generated by MINI_PLANNER"
                        print(f"[ROUTER] FALLBACK MINI_PLANNER -> PLANNER_V2: {fallback_reason}")
                except Exception as e:
                    level = "PLANNER_V2"
                    fallback_occurred = True
                    fallback_reason = f"MINI_PLANNER planning exception: {e}"
                    print(f"[ROUTER] FALLBACK MINI_PLANNER -> PLANNER_V2: {fallback_reason}")
            
            if level == "PLANNER_V2":
                use_task_memory = True
                from core.planner import Planner
                planner = Planner(registry=reg)
                steps = planner.plan(goal)
                
            # If no steps after planning, run direct fallback
            if not steps:
                from core.intents import route_and_execute_command
                try:
                    result = route_and_execute_command(parsed)
                except Exception as e:
                    result = f"Chyba při provádění akce: {e}"
                
                self.chunk_received.emit(result)
                self.end_ai_bubble.emit()
                self.status_changed.emit("Ready")
                self.chats[self.current_chat]["messages"].append(f"Jarvis: {result}")
                save_json(CHATS_FILE, self.chats)
                self.event_bus.emit("ai_response", result)
                return

            # Log metrics format
            elapsed = time.perf_counter() - start_time
            tool_names = ", ".join([s.get("tool", "") for s in steps])
            
            print(f"[ROUTER]\n{level}\n\nTool:\n{tool_names}\n\nTime:\n{elapsed:.2f}s")
            
            # Save statistics
            increment_router_stat(
                level=level,
                elapsed_time=elapsed,
                fallback=fallback_occurred,
                fallback_reason=fallback_reason
            )
            
            # Execute steps
            step_descs = [step.get("description") or f"Spustit tool {step.get('tool')}" for step in steps]
            self.task_started.emit(goal, step_descs)
            
            if use_task_memory:
                task_memory = TaskMemory()
                task_memory.start_task(goal, steps)
            else:
                task_memory = None
                
            ctx = ToolContext(
                dry_run=False,
                agent_base_url="http://127.0.0.1:5000",
                workspace_root=os.getcwd()
            )
            state = JarvisState()
            
            def update_gui(idx: int, status: str):
                self.step_updated.emit(idx, status)
                
            executor = Executor(registry=reg, ctx=ctx, state=state, task_memory=task_memory, on_step_update=update_gui)
            self.status_changed.emit("Provádím...")
            
            fast_duration = 0.0
            if level == "FAST_COMMAND":
                fast_start = time.perf_counter()

            try:
                results = executor.run_plan(steps)
                if level == "FAST_COMMAND":
                    fast_duration = time.perf_counter() - fast_start
                
                if "paused_step_index" in state.data:
                    self.paused_task = {
                        "steps": steps,
                        "state": state,
                        "step_index": state.data["paused_step_index"],
                        "executor": executor,
                        "goal": goal
                    }
                    prompt_msg = state.data.get("user_help_required", "Akce vyžaduje potvrzení.")
                    self.chunk_received.emit(prompt_msg)
                    self.end_ai_bubble.emit()
                    self.chats[self.current_chat]["messages"].append(f"Jarvis: {prompt_msg}")
                    save_json(CHATS_FILE, self.chats)
                    self.status_changed.emit("Ready")
                    self.event_bus.emit("ai_response", prompt_msg)
                    return
                
                help_required = state.data.get("user_help_required")
                if help_required:
                    summary = f"Chyba během provádění: {help_required}"
                    success = False
                    if level == "FAST_COMMAND":
                        from ai.engine import fail_current_request
                        fail_current_request()
                else:
                    if results and not results[-1]["output"].get("ok", False):
                        summary = f"Úkol selhal na kroku {len(results)}: {results[-1]['output'].get('error', 'Neznámá chyba')}"
                        success = False
                        if level == "FAST_COMMAND":
                            from ai.engine import fail_current_request
                            fail_current_request()
                    else:
                        summary = f"Úkol byl úspěšně dokončen! Celkem provedeno {len(steps)} kroků."
                        success = True
                        if level == "FAST_COMMAND":
                            from ai.engine import complete_current_request, get_current_request
                            complete_current_request()
                            req_id = get_current_request().request_id
                            print(f"[FAST_COMMAND]\nEXECUTION_COMPLETE\n\nRequest ID:\n{req_id}\n\nDuration:\n{fast_duration:.2f}s\n\nResult:\nSUCCESS\n")
            except Exception as e:
                summary = f"Neočekávaná chyba při provádění úkolu: {e}"
                success = False
                if level == "FAST_COMMAND":
                    from ai.engine import fail_current_request
                    fail_current_request()
                
            self.chunk_received.emit(summary)
            if self.voice_read_enabled or (hasattr(self, "voice_active") and self.voice_active):
                speak(summary)
                
            self.end_ai_bubble.emit()
            self.chats[self.current_chat]["messages"].append(f"Jarvis: {summary}")
            save_json(CHATS_FILE, self.chats)
            self.status_changed.emit("Ready")
            self.task_finished.emit(success, summary)
            self.event_bus.emit("ai_response", summary)
            
        import threading
        t = threading.Thread(target=agent_task, daemon=True)
        t.start()
        return t

    def process_ai_request(self, message: str):
        self.profile = update_profile(self.profile, message)
        save_json(PROFILE_FILE, self.profile)
        prompt = self.build_prompt(message)
        self.status_changed.emit("Premyslim...")

        threading.Thread(
            target=speak,
            args=(random.choice(["Mrknu na to.", "Moment.", "Zpracovavam.", "Rozumim."]),),
            daemon=True,
        ).start()

        chat_model = self.chats[self.current_chat]["model"]

        def ai_task():
            self.start_ai_bubble.emit()
            response_generator = generate_stream(prompt, chat_model)
            buffer = ""
            full_reply = ""
            for chunk in response_generator:
                full_reply += chunk
                buffer += chunk
                self.chunk_received.emit(chunk)
                if buffer.endswith(".") or buffer.endswith("?") or buffer.endswith("!"):
                    if self.voice_read_enabled:
                        speak(buffer)
                    buffer = ""

            if buffer.strip() and self.voice_read_enabled:
                speak(buffer)

            self.end_ai_bubble.emit()
            self.chats[self.current_chat]["messages"].append(f"Jarvis: {full_reply}")
            save_json(CHATS_FILE, self.chats)
            self.status_changed.emit("Ready")
            self.event_bus.emit("ai_response", full_reply)

        threading.Thread(target=ai_task, daemon=True).start()
        self.clear_input.emit()



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
        from ai.engine import reset_current_request
        reset_current_request()

        self.user_message_received.emit(f"Voice: {text}")
        self.chats[self.current_chat]["messages"].append(f"Ty: {text}")
        save_json(CHATS_FILE, self.chats)
        self.status_changed.emit("Thinking...")

        if self.handle_router_preference_choice(text):
            return None

        from core.intents import IntentType, classify_intent
        parsed = classify_intent(text)

        if parsed.intent != IntentType.CHAT and not parsed.requires_llm:
            worker = self.process_agent_request(parsed)
            from core.intents.fast_command_router import classify_routing_level
            route_info = classify_routing_level(text)
            if route_info["route"] == "FAST_COMMAND":
                if hasattr(self, "voice_active") and self.voice_active:
                    self.stop_voice_chat()
            return worker

        prompt = self.build_prompt(text)
        chat_model = self.chats[self.current_chat]["model"]

        def ai_task():
            self.start_ai_bubble.emit()
            self.status_changed.emit("Speaking...")
            response_generator = generate_stream(prompt, chat_model)

            def gui_stream():
                for chunk in response_generator:
                    yield chunk

            def emit_chunk(chunk: str):
                self.chunk_received.emit(chunk)

            full_reply = voice_speak_stream(_emit_stream(gui_stream(), emit_chunk))

            self.end_ai_bubble.emit()
            self.chats[self.current_chat]["messages"].append(f"Jarvis: {full_reply}")
            save_json(CHATS_FILE, self.chats)
            self.status_changed.emit("Ready")
            self.event_bus.emit("ai_response", full_reply)

        worker = threading.Thread(target=ai_task, daemon=True)
        worker.start()
        return worker

    def start_voice_chat(self):
        if self.voice_active:
            return
        self.voice_active = True
        self.voice_status_changed.emit("Voice: Listening")
        threading.Thread(target=self.voice_conversation_loop, daemon=True).start()

    def stop_voice_chat(self):
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
