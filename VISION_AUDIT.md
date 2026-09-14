# VISION AUDIT – PHASE 10: REAL VISION + OCR + GUI INTERACTION KERNEL

Datum: 2026-09-14
Projekt: Jarvis (David Kretschmer)
Poslední commit: `c106061` (*feat: harden deterministic Windows tools*)

---

## 1. Souhrnná tabulka komponent

| Component | Location | Current Role | Used by Runtime | Verification | Duplicate | Problem |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ScreenshotManager** | `vision/screenshot_manager.py` | Snímání obrazovky pomocí `pyautogui.screenshot()`, crop, resize, ukládání do PNG | Ano (v `UIDetector` a `VisionEngine`) | Žádná (pouze vrátí `ScreenshotResult` s cestou) | Ano (`core/agent.py:take_screenshot`) | Hardcoded cesty, chybí standardizovaná integrace s `Observation`, nekontroluje stáří screenshotu (`max_observation_age`). |
| **TesseractValidator** | `vision/tesseract_validator.py` | Detekce Tesseractu přes `pytesseract` nebo `shutil.which("tesseract")` | Ano (při startu `GuiController` a v `UIDetector`) | Vrátí `(bool, str)` | Částečně (v `core/agent.py:read_screen` je vlastní try/except) | Nerozlišuje stavy `OCR_AVAILABLE`, `OCR_UNAVAILABLE`, `OCR_FAILED`; vrací pouze boolean a text pro UI. |
| **UIDetector** | `vision/ui_detector.py` | Extrakce OCR prvků přes `pytesseract.image_to_data`, seskupení slov, prompt do Llama 3 LLM | Ano (`SmartClickTool`, `SmartWriteTool`, `SmartCheckboxTool`, `ConfirmDialogTool`, `CancelDialogTool`) | `UIResponseValidator` (ověřuje meze a typy) | Ne | Selže s výjimkou `VisionError`, pokud Tesseract chybí; volá LLM na každý screen detect (pomalé, nedeterministické); neprodukuje standardizovaný `Observation`. |
| **VisionEngine** | `vision/vision_engine.py` | Analýza obrazovky přes Ollama HTTP API (`qwen2.5-vl:7b`) | Částečně (volán v `UIDetector`, ale chybí v `Executor`) | Žádná | Částečně (`ai/engine.py` má centrální Ollama session) | Vytváří vlastní `requests.post` mimo `ai/engine.py`; model `qwen2.5-vl` není nainstalován v lokálním Ollama; chybí fallback. |
| **PromptBuilder** | `vision/prompt_builder.py` | Tvorba promptů pro UI detekci a popis obrazovky | Ano (v `UIDetector` a `VisionEngine`) | N/A | Ne | Pevně svázáno s LLM generováním namísto deterministického parsování elementů. |
| **UI Parsers & Schemas** | `vision/parsers/`, `vision/schemas/` | Pydantic/dataclass schémata `UIElement`, `UIResponse`, validátor výstupu z LLM | Ano (v `UIDetector`) | Validace souřadnic uvnitř obrazovky | Ne | Izolované schéma oddělené od `core/observation.py`. |
| **Observation** | `core/observation.py` | Třída `Observation` a výčet `ObservationType` (`SCREEN`, `OCR`, `PROCESS`, `WINDOW`, ...) | Ano (`Executor`, `VerificationResult`, `ScreenshotTool`) | Dataclass s confidence a evidence | Ne | Chybí pole `id`, `request_id`, `step_id`, typ `VISION` a helpery pro GUI bounding boxy. |
| **SmartClickTool** | `tools/pc_control.py:268` | Kliknutí na prvek nalezený OCR podle textu a fuzzy matching | Ano (registrovaný nástroj v `ToolRegistry`) | `UIInteractionVerifier` (vrací UNKNOWN) | Částečně (`ClickTool`, `ConfirmDialogTool`) | Spoléhá na `UIDetector` + LLM, nekontroluje stáří snímku; vlastní ad-hoc confidence logika; neprochází jednotným `TargetResolver`. |
| **SmartWriteTool / SmartCheckboxTool** | `tools/pc_control.py:350, 430` | Psaní do vstupu / klik na checkbox podle OCR labelu | Ano (registrovaný v `ToolRegistry`) | `UIInteractionVerifier` | Ne | Duplikují vyhledávací smyčky z `SmartClickTool`, nepoužívají jednotný target resolver. |
| **ConfirmDialogTool / CancelDialogTool** | `tools/pc_control.py:514, 560` | Hledání potvrzovacích/storno tlačítek (OK, Ano, Cancel, Storno) | Ano (registrovaný v `ToolRegistry`) | `UIInteractionVerifier` | Částečně (`SmartClickTool`) | Mají hardcoded seznamy slov ("ok", "ano", "cancel", "storno") přímo v run metodě namísto semantického target resolveru. |
| **ClickTool / DoubleClickTool** | `tools/pc_control.py:125, 150` | Kliknutí na absolutní x, y souřadnice přes `_post_agent` | Ano (registrovaný v `ToolRegistry`) | `UIInteractionVerifier` | Ano (`SmartClickTool`) | Umožňuje přímé klikání na libovolné souřadnice bez ověření existence prvku a bez pre/post verifikace. |
| **ScreenshotTool / ReadScreenTool** | `tools/pc_control.py:208, 243` | Pořízení screenshotu a vyčtení celého textu obrazovky přes agent HTTP | Ano (registrovaný v `ToolRegistry`) | `PassThroughVerifier` / částečná | Ano (`ScreenshotManager`, `core/agent.py`) | Volají Flask server `core/agent.py` přes HTTP místo lokálního Python volání. |
| **UIInteractionVerifier** | `core/verification.py:630` | Verifikace kliknutí a stisků kláves po provedení akce | Ano (`Executor` po každém UI kroku) | Vrací `VERIFIED` pouze při `observed_delta=True`, jinak `UNKNOWN` | Ne | Chybí skutečná detekce změny obrazovky (screen hash, porovnání ROI, zmizení targetu, objevení dialogu). |
| **Local HTTP Agent** | `core/agent.py` | Flask server na portu 5000 s endpointy `/command` a `/task` | Používán přes `_post_agent` v `tools/pc_control.py` | Částečná security policy na `/command` | Ano (duplikuje screenshot a OCR logiku) | Zbytečná síťová režiie pro lokální volání; `take_screenshot` a `read_screen` obchází modul `vision/`. |
| **RealtimeVoicePipeline** | `Voice/pipeline/realtime_pipeline.py` | Starý streaming voice orchestrator (`process_text` volá přímo AI stream a TTS) | Ne v produkčním GUI (`GuiController` používá `JarvisRuntime.run_task`) | Žádná | Ano (`JarvisRuntime`) | Pokud by byl spuštěn přímo, obešel by `JarvisRuntime`, `SecurityPolicy`, `Executor` i `Verification`. Musí být explicitně označen jako deprecated. |
| **Browser Automation** | N/A (žádný Playwright/Selenium) | Pouze spouštění URL v defaultním browseru přes `webbrowser` / `os.startfile` | Ano (`OpenWebsiteTool`, `OpenUrlTool`) | `BrowserVerifier` (ověřuje běžící proces browseru) | Ne | Neexistuje DOM automatizace. Je nutné jasně definovat hierarchii: DOM (pokud bude dostupný) -> OCR/Vision -> souřadnice. |
| **OpenCV (`cv2`)** | N/A | V projektu se nevyskytuje a v `.venv` není nainstalován | Ne | N/A | Ne | Všechny obrazové operace (diff, hash, crop) musí bezpečně běžet přes standardní `PIL` (Pillow). |
| **`win32gui` / Win32 API** | `core/verification.py:96` | `win32gui` není nainstalován; Windows okna jsou snímána přímo přes `ctypes.windll.user32.EnumWindows` | Ano (`WindowVerifier`, `_get_visible_window_titles_windows`) | Deterministická kontrola titulků oken | Ne | Správné řešení bez nutnosti instalovat externí `pywin32`. |

---

## 2. Klíčová zjištění a nedostatky

1. **Stav OCR a Tesseractu:**
   - Binárka Tesseractu není na systému nainstalována (`check_tesseract()` vrací `(False, 'Chybí Tesseract')`).
   - Knihovna `pytesseract` je přítomna v Python virtuálním prostředí.
   - Systém proto **musí** rozlišovat stavy `OCR_AVAILABLE`, `OCR_UNAVAILABLE`, `OCR_FAILED` a při nedostupnosti vracet `UNKNOWN`, nikoliv selhávat neošetřenou výjimkou nebo falešným `SUCCESS`.

2. **Stav lokálních Vision modelů:**
   - Lokální Ollama běží na portu 11434 a má modely: `deepseek-coder:latest`, `qwen:latest`, `gemma:latest`, `mistral:latest`, `phi3:latest`, `llama3:latest`.
   - Vision model `qwen2.5-vl` v Ollama nainstalován **není**.
   - `VisionEngine` proto musí hlásit `VISION_UNAVAILABLE` a pokračovat přes bezpečný fallback.

3. **Neexistence jednotného Target Resolveru:**
   - Každý nástroj (`SmartClickTool`, `SmartWriteTool`, `ConfirmDialogTool`, `ClickTool`) si dnes řeší hledání cíle sám, ad-hoc fuzzy matchingem, vlastními prahy confidence a přímými souřadnicemi.
   - Chybí centrální autoritativní `TargetResolver`, který by uplatňoval přísnou prioritu:
     1. Deterministické prvky / okna (Windows controls / titles)
     2. OCR (lokální textové rozpoznání)
     3. Lokální Vision model (pokud je dostupný)
     4. Explicitní souřadnice (pouze pokud jsou validovány a bezpečné)

4. **Absence Screen Change Verification:**
   - `UIInteractionVerifier` po kliknutí na GUI vrací `UNKNOWN`, protože nemá mechanismus pro porovnání stavu před a po akci.
   - Po kliknutí musí proběhnout nový screenshot a vyhodnocení změny (rozdíl obrazu, změna titulku okna, zmizení tlačítka, výskyt očekávaného textu).

5. **Starý RealtimeVoicePipeline:**
   - V `Voice/pipeline/realtime_pipeline.py` je paralelní orchestrátor, který nepoužívá `JarvisRuntime`.
   - Všechny hlasové příkazy (např. *"klikni na Přihlásit"*) již v `GuiController` prochází sjednocenou metodou `process_request` do `JarvisRuntime`. `RealtimeVoicePipeline` musí být formálně označen jako deprecated / adapter, aby nikdy neobcházel bezpečnostní a verifikační jádro.
