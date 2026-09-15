# INTEGRATION AUDIT – JARVIS LOCAL RUNTIME
**Datum:** 2026-09-15  
**Projekt:** Jarvis – Lokální autonomní Windows AI asistent  
**Fáze:** 11 – Integration & Real-World Hardening  

---

## 1. Souhrn auditu

Tento audit podrobně zkoumá reálné runtime cesty, vazby mezi komponentami, duplicitní implementace, bezpečnostní záruky, verifikační mechanismy a zacházení se vstupy.

Jarvis je navržen jako lokální Windows asistent běžící v architektuře:
```
USER (GUI / Voice / CLI / HTTP)
  ↓
JarvisRuntime.run_task()
  ↓
Router (FastRouter / MiniPlanner / Planner)
  ↓
Executor
  ↓
SecurityPolicy & ConfirmationManager
  ↓
ToolRegistry (Windows Tools, Vision Tools, File Tools)
  ↓
Observation (Screen, Process, Window, Filesystem)
  ↓
Verification (UIInteractionVerifier, ProcessVerifier, FileVerifier, etc.)
  ↓
Repair / Replan (pokud selže a zbývá budget)
  ↓
RequestResult
```

Při auditu bylo identifikováno **7 klíčových problémů a zranitelností** (od P0 po P2), které narušovaly celistvost a pravdivost systému:

---

## 2. Nalezené problémy a zranitelnosti

### Nález 1: UNKNOWN verifikace byla v Runtime převáděna na SUCCESS
- **Soubor:** `core/runtime.py` (řádek 678–680), `core/executor.py` (řádek 83–89, 1002)
- **Konkrétní funkce / třída:** `JarvisRuntime._summarize_execution()`, `StepResult.is_success`, `Executor.run_plan()`
- **Skutečná runtime cesta:**
  `run_task()` → `executor.run_plan()` → `UIInteractionVerifier.verify()` (vrátí `status=UNKNOWN`) → `StepResult(status=SUCCESS)` → `_summarize_execution()` → `if has_unknown: return True, "Ukol byl uspesne proveden (stav nekterych kroku zustal UNKNOWN)..."`
- **Proč je to problém:**
  Pravidlo **UNKNOWN ≠ SUCCESS** bylo porušeno. Pokud se kliknutí myší nepodařilo verifikovat (např. žádný vizuální posun, chybějící OCR), Jarvis hlásil uživateli i stavovému stroji `ok=True` a `status=COMPLETED`.
- **Severity:** **P0 (Kritická)**
- **Doporučená oprava:**
  Pokud krok vrátí verifikaci `UNKNOWN`, nesmí být `StepResult` označen jako `is_success=True`. Runtime musí vrátit `ok=False`, stav `RequestExecutionStatus.UNKNOWN` a pravdivou informaci, že výsledek akce nelze prokázat.

---

### Nález 2: `SmartClickTool`, `SmartWriteTool` a `SmartCheckboxTool` obcházely centrální `TargetResolver` a `VisionService`
- **Soubor:** `tools/pc_control.py` (řádky 287–335, 388–435, 467–505)
- **Konkrétní funkce / třída:** `SmartClickTool.run()`, `SmartWriteTool.run()`, `SmartCheckboxTool.run()`
- **Skutečná runtime cesta:**
  `SmartClickTool.run()` → přímá instance `vision.ui_detector.UIDetector()` → ad-hoc fuzzy matching a bounds kontrola → přímé volání `_post_agent(ctx, "click")`.
- **Proč je to problém:**
  Centrální `core/target_resolver.py` a `core/vision.py` byly zcela ignorovány reálnými nástroji v `ToolRegistry`. Nástroje si samy volaly `UIDetector`, nekontrolovaly stáří snímku (`stale observation`), ignorovaly hierarchii rozlišení cíle a duplikovaly logiku.
- **Severity:** **P1 (Vysoká)**
- **Doporučená oprava:**
  Přepojit všechny smart UI nástroje v `tools/pc_control.py` na centrální `TargetResolver` a `VisionService`. Pokud `TargetResolver` vrátí `AMBIGUOUS`, `LOW_CONFIDENCE`, `OUT_OF_BOUNDS`, `STALE_OBSERVATION` nebo `NOT_FOUND`, nástroj nesmí kliknout naslepo a musí vrátit přesnou chybu.

---

### Nález 3: Nebezpečí staré observace (`STALE_OBSERVATION`) v `TargetResolver`
- **Soubor:** `core/target_resolver.py` (řádky 126–135)
- **Konkrétní funkce / třída:** `TargetResolver.resolve()`, `TargetResolver._check_coordinate_target()`
- **Skutečná runtime cesta:**
  `resolve()` nejprve zkontrolovala explicitní souřadnice (`_check_coordinate_target`) bez ověření, zda dodaná observace není stará nebo zda se okno nezměnilo. Navíc při detekci staré observace tiše zachytila nový snímek, místo aby volajícímu umožnila validovat změnu GUI stavu.
- **Proč je to problém:**
  Pokud se stav obrazovky v čase T0 změnil a volající použil zastaralou observaci, systém mohl kliknout na souřadnice, které již neodpovídaly původnímu kontextu.
- **Severity:** **P1 (Vysoká)**
- **Doporučená oprava:**
  Zavést striktní prioritu: 1. Deterministic window/control, 2. OCR, 3. Local vision model, 4. Explicit coordinates fallback. Při explicitní validaci stáří vrátit `TargetResolutionStatus.STALE_OBSERVATION`.

---

### Nález 4: Narušení soukromí snímků obrazovky (ukládání každého snímku na disk)
- **Soubor:** `core/vision.py` (řádky 383–392), `vision/screenshot_manager.py` (řádky 49–51)
- **Konkrétní funkce / třída:** `VisionService.capture_observation()`, `ScreenshotManager.capture()`
- **Skutečná runtime cesta:**
  Každé volání `capture_observation()` vytvořilo soubor v `screenshots/vision/screenshot_YYYYMMDD-HHMMSS_xxxx.png` na pevném disku, i při rutinním vyhledávání prvku.
- **Proč je to problém:**
  Porušení požadavku na **Screenshot Privacy**: Běžný capture obrazovky má běžet výhradně v paměti RAM (`PIL.Image`) a po zpracování být zahozen. Trvalé ukládání má být umožněno pouze pro explicitní debug nebo diagnostiku.
- **Severity:** **P1 (Vysoká)**
- **Doporučená oprava:**
  V `VisionService.capture_observation()` ukládat na disk pouze v případě, že je předán parametr `save_to_disk=True` nebo je aktivován debug režim. Jinak držet snímek pouze v paměti.

---

### Nález 5: Znovupoužitelnost schválení v `ConfirmationManager` / nebezpečí globálního autorizačního stavu
- **Soubor:** `core/executor.py` (řádky 355, 462, 950)
- **Konkrétní funkce / třída:** `Executor.run_plan()`
- **Skutečná runtime cesta:**
  Při schválení potvrzení byl nastaven token v `ConfirmationManager`, ale po úspěšném provedení kroku nebyl token označen jako spotřebovaný. Navíc `self.state.data["action_authorized"] = True` zůstával v paměti a mohl teoreticky autorizovat další krok.
- **Proč je to problém:**
  Potvrzení uživatele musí být vázáno na konkrétní akci `(request_id, step_id, tool, resource, risk, expiration)`. Po vykonání kroku musí být autorizace spotřebována.
- **Severity:** **P1 (Vysoká)**
- **Doporučená oprava:**
  Po úspěšném či neúspěšném spuštění autorizovaného kroku okamžitě zneplatnit / spotřebovat token v `ConfirmationManager` a smazat autorizační flag z `state.data`.

---

### Nález 6: Duplicitní a nestandardní HTTP klient pro Ollama ve Vision
- **Soubor:** `vision/vision_engine.py` (řádky 68–73)
- **Konkrétní funkce / třída:** `VisionEngine.analyze_screenshot()`
- **Skutečná runtime cesta:**
  Volá přímo ad-hoc `requests.post(f"{self.config.ollama_url}/api/generate", ...)` bez connection poolingu a centrální správy sessions z `ai/engine.py`.
- **Proč je to problém:**
  Projekt má centrální `ai.engine.get_ollama_session()` s keep-alive poolingem a health checkem. Samostatné ad-hoc volání obchází centrální konfiguraci a diagnostiku.
- **Severity:** **P2 (Střední)**
- **Doporučená oprava:**
  Sjednotit volání v `vision/vision_engine.py` na `ai.engine.get_ollama_session()`.

---

### Nález 7: Mrtvý bypass kód v `core/intents/command_router.py`
- **Soubor:** `core/intents/command_router.py` (řádky 107–178)
- **Konkrétní funkce / třída:** `execute_control_pc()`, `execute_vision()`
- **Skutečná runtime cesta:**
  Obsahuje staré funkce posílající HTTP příkazy přes `send_agent_command()` přímo na `/command` bez procházení `JarvisRuntime`, `SecurityPolicy` a `Executoru`.
- **Proč je to problém:**
  Potenciální zadní vrátka a matoucí kód, pokud by byl omylem importován.
- **Severity:** **P2 (Střední)**
- **Doporučená oprava:**
  Nahradit těla těchto funkcí delegací na `JarvisRuntime().run_task(original_text)`, čímž se zajistí bezpečnost i pro případné staré volající.

---

## 3. Matice vstupních cest (Entry Point Matrix)

| Vstupní bod | Vstupní soubor | Metoda / Handler | Cílová autoritativní cesta | Stav integrace |
| :--- | :--- | :--- | :--- | :--- |
| **GUI Chat** | `interfaces/gui_controller.py` | `process_request(source="gui_chat")` | `JarvisRuntime.run_task()` | **PASS** |
| **GUI Agent** | `interfaces/gui_controller.py` | `process_agent_request()` | `JarvisRuntime.run_task()` | **PASS** |
| **Voice** | `interfaces/gui_controller.py` | `handle_voice_text()` | `JarvisRuntime.run_task()` | **PASS** |
| **CLI** | `run.py` | `main()` | `JarvisRuntime.run_task()` | **PASS** |
| **HTTP /task** | `core/agent.py` | `run_task_endpoint()` | `JarvisRuntime.run_task()` | **PASS** |
| **AutonomousAgent** | `core/autonomous_agent.py` | `AutonomousAgent.run()` | `JarvisRuntime.run_task()` | **PASS** |
| **HTTP /command (low-level)** | `core/agent.py` | `command()` | Low-level transport; chráněn lokální auth a SecurityPolicy na `open_path` | **PASS (Transport)** |
| **Legacy Command Router** | `core/intents/command_router.py`| `route_and_execute_command()` | `JarvisRuntime.run_task()` | **PASS** |

---

## 4. Doporučený plán nápravy

1. **Oprava `core/runtime.py` a `core/executor.py`:** Zavedení striktního stavu `UNKNOWN`, `StepResult.is_success` odmítá `UNKNOWN`, `_summarize_execution()` nevrací `ok=True`.
2. **Přepojení nástrojů v `tools/pc_control.py` na `TargetResolver` a `VisionService`:** Odstranění ad-hoc instancí `UIDetector`.
3. **Hardening `core/target_resolver.py`:** Priorita 1-4, detekce `STALE_OBSERVATION`, `AMBIGUOUS`, `LOW_CONFIDENCE`, `OUT_OF_BOUNDS`.
4. **Screenshot Privacy v `core/vision.py`:** RAM-only capture ve výchozím stavu.
5. **Spotřeba potvrzení v `ConfirmationManager`:** Invariant jednorázové autorizace.
6. **Sjednocení Ollama session v `vision/vision_engine.py`:** Použití `get_ollama_session()`.
7. **Reálné Windows E2E integrační testy (`tests/test_real_windows_e2e_integration.py`):** Automatizované ověření celého řetězce nad živou bezpečnou Tkinter aplikací.
