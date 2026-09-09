# Architektonický Audit Voice Subsystému (Fáze 7)

**Datum:** 9. září 2026  
**Cíl:** Kompletní audit, sjednocení a stabilizace hlasového subsystému Jarvise, odstranění duplicit a mrtvého kódu, zajištění vazby na `JarvisRuntime.run_task()`, `RequestContext`, `EventBus`, a bezpečné ukládání nahrávek do AppData.

---

## 1. Současná Architektura

V repozitáři v současnosti existují **dvě paralelní implementace hlasového subsystému** umístěné v adresáři `Voice/`:

```
Voice/
├── __init__.py                # Exportuje VoiceManager, get_voice_manager
├── voice_manager.py           # Hlavní aktivní fasáda VoiceManager pro GUI a interfaces/voice.py
├── whisper_engine.py          # STT implementace (faster-whisper, fallback mechanismus)
├── tts_engine.py              # TTS implementace (PiperTTS, sentence chunking, EQ, pitch)
├── microphone.py              # Nahrávání zvuku (sounddevice, VAD, noise reduction)
├── audio_output.py            # Výstup zvuku (sounddevice, queue worker)
├── vad.py                     # Voice Activity Detection (webrtcvad + RMS fallback)
├── wake_word.py               # Lokální offline wake word placeholder (disabled default)
├── interruption.py            # Detekce řeči uživatele během promluvy Jarvise
├── streaming.py               # LatencyTimer a streaming pomocníci
├── config.py                  # VoiceConfig dataclass a normalizace legacy klíčů
│
├── audio/                     # [DUPLICITNÍ PODVĚTEV]
│   ├── __init__.py
│   ├── audio_capture.py       # Duplikát Voice/microphone.py
│   └── vad.py                 # Duplikát Voice/vad.py
├── stt/                       # [DUPLICITNÍ PODVĚTEV]
│   ├── __init__.py
│   └── whisper_engine.py      # Duplikát Voice/whisper_engine.py
├── tts/                       # [DUPLICITNÍ PODVĚTEV]
│   ├── __init__.py
│   ├── piper_engine.py        # Duplikát Voice/tts_engine.py
│   └── audio_player.py        # Duplikát Voice/audio_output.py
├── wakeword/                  # [DUPLICITNÍ PODVĚTEV]
│   ├── __init__.py
│   └── porcupine_engine.py    # Cloud-dependent Picovoice Porcupine (vyžaduje API klíč)
├── utils/                     # [DUPLICITNÍ PODVĚTEV]
│   ├── __init__.py
│   └── config.py              # Starší verze VoiceConfig
└── pipeline/                  # [DUPLICITNÍ PODVĚTEV]
    ├── __init__.py
    └── realtime_pipeline.py   # Izolovaná pipeline netestovaná s reálným GUI/Runtime
```

V kořeni `Voice/` se navíc nachází **279 audio souborů** typu `user_voice_YYYYMMDD-HHMMSS.wav` (cca 10.2 MB), které vznikly při dřívějším manuálním testování, protože výchozí konfigurace ukládala nahrávky přímo do `Voice/`.

---

## 2. Všechny Voice Entry Points

1. **`interfaces/voice.py`**:
   - `start_recording(volume_callback=None)` -> `VoiceManager.start_recording()`
   - `stop_recording()` -> `VoiceManager.stop_recording()`
   - `speech_to_text()` -> `VoiceManager.speech_to_text()`
   - `listen_once_to_text(volume_callback=None)` -> `VoiceManager.listen_once_to_text()`
   - `speak(text)` -> `VoiceManager.speak()`
   - `speak_stream(chunks)` -> `VoiceManager.speak_stream()`
   - `interrupt_speech()` -> `VoiceManager.interrupt_speech()`
   - `wake_listener(callback)` -> `VoiceManager.wake_listener()`
   - `stop_wake_listener()` -> `VoiceManager.stop_wake_listener()`
   - `get_voice_config()` -> `VoiceManager.config`

2. **`interfaces/gui_controller.py`**:
   - `start_recording()` / `stop_recording()`: manuální nahrávání z GUI tlačítka.
   - `send_voice()`: spustí vlákno `transcribe_task` -> `vs_stt()` -> `handle_voice_text(text)`.
   - `start_voice_chat()` / `stop_voice_chat()`: zapne/vypne kontinuální voice loop (`voice_conversation_loop`).
   - `voice_conversation_loop()`: běží ve vlákně `daemon=True`, dokud platí `self.voice_active`, volá `listen_once_to_text()` a předává text do `handle_voice_text()`.
   - `toggle_wake_word()` / `start_wake_listener()` / `on_wake_word()` / `handle_wake_capture()`: probuzení slovem -> `listen_once_to_text()` -> `handle_voice_text()`.

3. **`handle_voice_text(text)` v `interfaces/gui_controller.py`**:
   - Zde dochází ke zpracování rozpoznaného textu.
   - Pro příkazy mimo chat (`parsed.intent != IntentType.CHAT and not parsed.requires_llm`) volá `process_agent_request(parsed)`, což deleguje na `self.runtime.run_task(...)`.
   - Pro chat (`IntentType.CHAT`) volá `generate_stream(...)` a výstup posílá do `voice_speak_stream(...)`.
   - **Problém:** Volalo se `from ai.engine import reset_current_request` namísto autoritativního `core.lifecycle.reset_current_request` z Fáze 4/5.

---

## 3. Skutečně Používané STT

- **Aktivní modul:** `Voice/whisper_engine.py` (třída `WhisperEngine`), inicializovaná ve `Voice/voice_manager.py`.
- **Backend:** `faster-whisper` (`ctranslate2`).
- **Model:** Výchozí `large-v3-turbo` s automatickým fallbackem na `small`.
- **Device & Compute:** Automatická detekce CUDA (`ctranslate2.get_cuda_device_count() > 0`), při úspěchu `cuda` s `float16`, fallback na `cpu` s `int8`.
- **Rozhraní:** `transcribe_audio(audio, sample_rate, partial_callback)` a `transcribe_recording(recording, partial_callback)`.
- **Duplicitní modul:** `Voice/stt/whisper_engine.py` – totožná logika, importovaná pouze z `Voice/pipeline/realtime_pipeline.py`.

---

## 4. Skutečně Používané TTS

- **Aktivní modul:** `Voice/tts_engine.py` (třída `PiperTTS`, factory `create_tts()`), inicializovaná ve `Voice/voice_manager.py`.
- **Backend:** `piper-tts` (`piper.voice.PiperVoice`).
- **Hlas:** Výchozí `cs_CZ-jirka-medium.onnx`.
- **Post-processing:** Úprava rychlosti (`SynthesisConfig.length_scale`), posun tónu (`librosa.effects.pitch_shift`), EQ filtr (`scipy.signal.iirpeak` pro simulaci AI hlasu), normalizace amplitudy.
- **Přehrávání:** Výstup je enqueuován do dedikovaného vlákna `AudioOutput` (`Voice/audio_output.py`), které volá `sounddevice.play()`.
- **Duplicitní modul:** `Voice/tts/piper_engine.py` + `Voice/tts/audio_player.py` – duplikát téže logiky s menší výbavou.

---

## 5. Skutečný Audio Flow

### Vstup (Capture & STT)
```
[Mikrofon]
    ↓ sounddevice.InputStream (Voice/microphone.py)
[Frame Queue / VAD]
    ↓ webrtcvad / RMS (Voice/vad.py)
[Silence Threshold Reached (1.1s)]
    ↓ normalize_audio() + filter_audio()
[RecordingResult]
    ↓ transcribe_audio() (Voice/whisper_engine.py)
[Text]
```

### Zpracování (Routing & Runtime)
```
[Text]
    ↓ handle_voice_text() (interfaces/gui_controller.py)
    ↓ classify_intent() (core/intents)
[JarvisRuntime.run_task()] (core/runtime.py)
    ↓ RequestContext (core/lifecycle.py)
    ↓ Fast Command Router / Planner / Executor
[RuntimeResult / Text Response]
```

### Výstup (TTS & Playback)
```
[Response Text]
    ↓ speak() / speak_stream() (Voice/voice_manager.py)
[Sentence Splitter & Normalizer] (Voice/tts_engine.py)
    ↓ synthesize() (PiperTTS via piper-tts)
[PCM float32 Audio Array]
    ↓ enqueued to AudioOutput._queue (Voice/audio_output.py)
[sounddevice.play()]
    ↓
[Reproduktor]
```

### Přerušení (Interruption Flow)
```
Uživatel začne mluvit během promluvy Jarvise
    ↓ on_user_speech() (Voice/interruption.py)
    ↓ interrupt_speech() (Voice/voice_manager.py)
    ↓ AudioOutput.stop() -> sd.stop() + vyčištění TTS fronty
Jarvis okamžitě ztichne
```

---

## 6. Všechny Duplicity

| Aktivní komponenta (Authoritative) | Duplicitní podsložková komponenta | Kdo ji používá? |
|---|---|---|
| `Voice/whisper_engine.py` | `Voice/stt/whisper_engine.py` | Pouze `realtime_pipeline.py` |
| `Voice/tts_engine.py` | `Voice/tts/piper_engine.py` | Pouze `test_tts.py`, `realtime_pipeline.py` |
| `Voice/audio_output.py` | `Voice/tts/audio_player.py` | Pouze `piper_engine.py` |
| `Voice/microphone.py` | `Voice/audio/audio_capture.py` | Pouze `realtime_pipeline.py` |
| `Voice/vad.py` | `Voice/audio/vad.py` | Pouze `audio_capture.py` |
| `Voice/wake_word.py` | `Voice/wakeword/porcupine_engine.py` | Pouze `test_wakeword.py`, vyžaduje Picovoice cloud klíč |
| `Voice/config.py` | `Voice/utils/config.py` | Pouze podsložky a staré testy |
| `Voice/voice_manager.py` | `Voice/pipeline/realtime_pipeline.py` | Pouze `test_voice_pipeline.py` |

---

## 7. Dead Code

1. **`Voice/stt/`, `Voice/tts/`, `Voice/audio/`, `Voice/wakeword/`, `Voice/utils/`, `Voice/pipeline/`**:
   - Celé podsložkové stromy jsou mrtvou paralelní větví.
   - Pro zachování 100% zpětné kompatibility s existujícími testy (`test_tts.py`, `test_wakeword.py`, `test_voice_pipeline.py`) budou v těchto souborech ponechány pouze **tenké jednořádkové wrappery / aliasy** odkazující na autoritativní `Voice/` moduly.
2. **`porcupine_engine.py`**:
   - Závislost na `pvporcupine` s API klíčem porušuje lokální offline princip Jarvise. Nahradí se tenkým offline bezpečným wrapperem.
3. **`test_piper.py` v kořeni repozitáře**:
   - Manuální ad-hoc skript. Může být přesunut nebo upraven tak, aby importoval autoritativní stack.
4. **279 nahrávek `Voice/user_voice_*.wav` a root soubory `test.wav`, `jarvis_voice.mp3`**:
   - Mrtvý vygenerovaný obsah, který nepatří do stromu zdrojových kódů.

---

## 8. Threading Model & Race Conditions

### Problémy v současném stavu:
1. **Double Start v `Microphone`**:
   - Pokud se zavolá `start()` opakovaně, vytvoří se nový `sounddevice.InputStream` bez uzavření předchozího.
2. **Double Start v `GuiController`**:
   - `start_voice_chat()` nekontroluje atomicky stav před spuštěním nového vlákna `voice_conversation_loop`.
   - Chybí synchronizační zámek nad přepínáním stavů.
3. **AudioOutput Stop Race**:
   - V `AudioOutput.stop()` se nastaví `_stop_event`, zavolá se `sd.stop()`, vyčistí se fronta, a okamžitě se zavolá `_stop_event.clear()`. Běžící worker mezitím mohl znovu začít přehrávat další položku.
4. **Daemon Threads bez kontrolovaného ukončení**:
   - Vlákna TTS workeru a AudioOutput workeru končí až s ukončením procesu, chybí explicitní clean teardown v testech.
5. **Nekontrolované `reset_current_request()`**:
   - `handle_voice_text()` importoval `reset_current_request` z `ai.engine`, což nekorelovalo s `core.lifecycle`.

---

## 9. Lifecycle

Navržený stavový automat pro Voice:
```
STOPPED
  ↓ start_voice_chat() / start_recording()
STARTING
  ↓ inicializace mikrofonu
LISTENING
  ↓ detekce řeči a ticha
TRANSCRIBING
  ↓ WhisperEngine
PROCESSING
  ↓ JarvisRuntime.run_task() / LLM
SPEAKING
  ↓ PiperTTS + AudioOutput
LISTENING / READY (podle režimu jednorázový vs kontinuální)
  ↓ stop_voice_chat() / stop_recording()
STOPPING
  ↓
STOPPED
```

Stavy budou explicitně reprezentovány enumem `VoiceState` v autoritativním modulu `Voice/voice_manager.py`.

---

## 10. EventBus Integrace

V současnosti Voice neemituje žádné `event_bus` události. Zavedeme standardizované události emitované přes `EventBus`:

- `voice_status_changed`: `{"state": state.value, "details": ...}`
- `voice_listening`: `{"mode": "continuous" | "manual" | "wake"}`
- `voice_transcribing`: `{}`
- `voice_transcribed`: `{"text": text}`
- `voice_processing`: `{"text": text}`
- `voice_speaking`: `{"text": text}`
- `voice_finished`: `{}`
- `voice_error`: `{"error": str(exc)}`
- `voice_interrupted`: `{}`

GUI `VoiceStateManager` se může na tyto události spolehnout nezávisle na Qt signálech.

---

## 11. Konfigurace

### Problém:
`VoiceConfig.recordings_dir` mělo výchozí hodnotu `"Voice"`, což vedlo k zahlcení source-code repozitáře audio nahrávkami.

### Řešení:
1. Použít autoritativní `ApplicationResolver.get_default_appdata_path("audio")` (nebo `%APPDATA%\Jarvis\audio`).
2. `save_recordings: bool = False` ve výchozím stavu (zapíná se pouze při diagnostice).
3. Pokud je zapnuto, nahrávky se ukládají striktně do AppData adresáře.
4. Sjednotit `Voice/config.py` a zachovat legacy gettery/settery (`whisper_model`, `tts_rate`, `tts_voice`, `realtime_mode`, `porcupine_access_key` apod.) jako vlastnosti delegující na standardní položky.

---

## 12. Timeouty

Zavedeme bezpečné timeouty pro zamezení deadlocku nebo nekonečného visení:
- Inicializace mikrofonu: ochrana proti blokování audio zařízení jinou aplikací.
- Detekce ticha: 1.1s (konfigurovatelné).
- Maximální délka nahrávání: 20.0s (konfigurovatelné).
- TTS syntéza: přerušitelné cykly po větách s timeoutem na větu.
- Shutdown: `join(timeout=2.0)` pro korektní ukončení pomocných vláken.

---

## 13. Bezpečnostní Problémy

1. **Žádné cloudové závislosti:** Odstranění požadavku na Picovoice access key.
2. **Žádný zápis do source tree:** Striktní zákaz ukládání zvuků do složek projektu.
3. **Ochrana proti výjimkám v audio vláknech:** Chyba zvukové karty nebo mikrofonu nesmí shodit celý Jarvis Runtime.

---

## 14. Doporučená Cílová Architektura

1. **Jeden autoritativní adresář `Voice/`:**
   - Všechny produkční třídy žijí přímo ve `Voice/`:
     - `voice_manager.py`
     - `whisper_engine.py`
     - `tts_engine.py`
     - `microphone.py`
     - `audio_output.py`
     - `vad.py`
     - `wake_word.py`
     - `interruption.py`
     - `config.py`
2. **Tenké zpětně kompatibilní wrappery v podsložkách:**
   - Podsložky `Voice/stt/`, `Voice/tts/`, `Voice/audio/`, `Voice/wakeword/`, `Voice/utils/`, `Voice/pipeline/` budou obsahovat pouze importy z hlavního `Voice/` balíčku, aby žádný existující test neselhal.
3. **Jednotné směrování do `JarvisRuntime.run_task()`:**
   - Hlasové příkazy jdou přes jednotný RequestContext z `core/lifecycle.py`.
4. **Čištění nahrávek:**
   - Smazání 279 souborů `Voice/user_voice_*.wav`, kořenového `test.wav` a `jarvis_voice.mp3`.
   - Zápis nového výchozího umístění do `%APPDATA%\Jarvis\audio`.

---

## 15. Přesný Seznam Souborů ke Změně

1. `Voice/config.py` – sjednocení konfigurace, směrování nahrávek do AppData, zpětně kompatibilní property gettery.
2. `Voice/voice_manager.py` – zavedení `VoiceState`, thread-safe start/stop, napojení na EventBus, bezpečné ukládání do AppData.
3. `Voice/microphone.py` – thread-safe start/stop, ochrana proti double startu.
4. `Voice/audio_output.py` – thread-safe stop bez race condition, čistý shutdown.
5. `Voice/tts_engine.py` – spolehlivé ukončování workeru, interrupt mechanismus.
6. `interfaces/voice.py` – zachování stabilního API s napojením na autoritativní VoiceManager.
7. `interfaces/gui_controller.py` – oprava `handle_voice_text`, import `reset_current_request` z `core.lifecycle`, atomická kontrola stavu `voice_active`.
8. `Voice/stt/whisper_engine.py` – tenký wrapper na `Voice.whisper_engine`.
9. `Voice/tts/piper_engine.py` – tenký wrapper na `Voice.tts_engine`.
10. `Voice/tts/audio_player.py` – tenký wrapper na `Voice.audio_output`.
11. `Voice/audio/audio_capture.py` – tenký wrapper na `Voice.microphone`.
12. `Voice/audio/vad.py` – tenký wrapper na `Voice.vad`.
13. `Voice/utils/config.py` – tenký wrapper na `Voice.config`.
14. `Voice/wakeword/porcupine_engine.py` – offline bezpečný tenký wrapper bez cloud klíče.
15. `Voice/pipeline/realtime_pipeline.py` – tenký wrapper delegující na jednotné komponenty.
16. `.gitignore` – potvrzení ignorování `*.wav`, `*.mp3`, `%APPDATA%` audio struktur.

---

## 16. Soubory ke Smazání

1. `Voice/user_voice_*.wav` (279 vygenerovaných nahrávek v source tree).
2. `test.wav` v kořeni repozitáře.
3. `jarvis_voice.mp3` v kořeni repozitáře.

---

## 17. Soubory, Které Musí Zůstat Kvůli Kompatibilitě

Všechny existující podsložkové moduly (`Voice/stt/whisper_engine.py`, `Voice/tts/piper_engine.py`, `Voice/tts/audio_player.py`, `Voice/audio/audio_capture.py`, `Voice/audio/vad.py`, `Voice/utils/config.py`, `Voice/wakeword/porcupine_engine.py`, `Voice/pipeline/realtime_pipeline.py`) **zůstanou jako tenké wrappery**. Tím se garantuje, že jakýkoliv kód nebo starší test spoléhající na tyto cesty bude bezchybně fungovat.

---

## 18. Testovací Plán

Vytvořit komplexní testovací sadu `tests/test_voice_subsystem.py`, která pokryje:
1. **STT Mock:** Transkripce audia bez nutnosti reálného Whisper modelu.
2. **TTS Mock:** Syntéza a chunking bez nutnosti reálného Piper modelu.
3. **Microphone Mock:** Nahrávání a VAD bez fyzického mikrofonu.
4. **Voice Lifecycle:** Přechody mezi stavy `STOPPED -> STARTING -> LISTENING -> TRANSCRIBING -> PROCESSING -> SPEAKING -> STOPPED`.
5. **Double Start / Double Stop:** Ověření odolnosti proti souběžnému volání.
6. **Thread Cleanup:** Ověření, že po `shutdown()` nezůstávají viset běžící vlákna.
7. **EventBus Integrace:** Ověření emitování `voice_status_changed`, `voice_listening`, `voice_transcribed`, `voice_speaking`, `voice_error`.
8. **Runtime Routing:** Ověření, že hlasový požadavek správně přechází do `JarvisRuntime.run_task()` bez obcházení `RequestContext`.
9. **AppData Audio Persistence:** Ověření, že nahrávky se ukládají do AppData a neznečišťují source tree.
10. **Regresní test stávajících testů:** `test_tts.py`, `test_voice_pipeline.py`, `test_wakeword.py` a celá dosavadní 152-testová sada.
