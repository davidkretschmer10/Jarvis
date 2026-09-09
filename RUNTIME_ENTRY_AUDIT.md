# RUNTIME ENTRY AUDIT
## Komplexní audit všech vstupních bodů systému Jarvis

Tento dokument detailně mapuje všechny vstupní body v repozitáři, které mohou:
1. přijmout uživatelský požadavek (user request),
2. volat LLM,
3. rozhodovat CHAT vs. ACTION,
4. vytvářet plán,
5. spouštět nástroje (tools),
6. provádět kroky,
7. generovat odpověď.

---

## 1. Souhrnná tabulka vstupních bodů

| Vstupní bod | Soubor | Funkce / Metoda | Kdo volá | Účel / Co dělá | Používá Runtime? | Používá RequestContext? | Používá Planner? | Používá Executor? | Používá ToolRegistry? | Může obejít execution loop? |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **GUI Chat** | `interfaces/gui_controller.py` | `process_ai_request` | `GuiController.handle_user_message` (když `intent == CHAT`) | Přímo volá `generate_stream` z `ai.engine`, streamuje text do UI bubliny | **NE** | Částečně (resetuje ctx, ale bez lifecycle stavů) | **NE** | **NE** | **NE** | **ANO (Bypasses Runtime entirely!)** |
| **GUI Action** | `interfaces/gui_controller.py` | `process_agent_request` | `GuiController.handle_user_message` (když `intent != CHAT`) | Spustí vlákno a volá `JarvisRuntime.run_task` | **ANO** | **ANO** | **ANO** | **ANO** | **ANO** | **NE** |
| **GUI Task Resume** | `interfaces/gui_controller.py` | `resume_task` (v `handle_user_message`) | Uživatel potvrdí pozastavenou akci | Volá přímo `executor.run_plan` namísto `runtime.resume_task` | **NE** | **ANO** | **NE** | **ANO** | **ANO** | **ANO (Bypasses Runtime.resume_task)** |
| **CLI** | `run.py` | `main` | Uživatel z příkazové řádky (`python run.py "..."`) | Volá `JarvisRuntime.run_task` | **ANO** | **ANO** | **ANO** | **ANO** | **ANO** | **NE** |
| **HTTP /task** | `core/agent.py` | `run_task_endpoint` | HTTP klient (`POST /task`) | Volá `JarvisRuntime.run_task` | **ANO** | **ANO** | **ANO** | **ANO** | **ANO** | **NE** |
| **HTTP /command (task)** | `core/agent.py` | `command` (`action == "task"`) | HTTP klient (`POST /command`) | Volá `JarvisRuntime.run_task` | **ANO** | **ANO** | **ANO** | **ANO** | **ANO** | **NE** |
| **HTTP /command (low-level)** | `core/agent.py` | `command` (ostatní akce) | Lokální transport pro jednotlivé desktopové volání | Přímo volá python funkce (`open_program`, `click`, atd.) | **NE** | **NE** | **NE** | **NE** | **NE** | **Transport layer only** (není high-level vstup) |
| **Voice Input** | `interfaces/gui_controller.py` | `handle_user_message` | Whisper STT výstup z mikrofonu | Předá rozpoznaný text do `handle_user_message` | Dědí stav z GUI (Action -> Runtime, Chat -> Bypass) | Dědí stav z GUI | Dědí stav z GUI | Dědí stav z GUI | Dědí stav z GUI | **ANO u chatu** |
| **AutonomousAgent** | `core/autonomous_agent.py` | `AutonomousAgent.run` | Testy, skripty | Pokud není mockovaný `execute`, volá `JarvisRuntime.run_task`. Jinak drží paralelní starý engine. | **Částečně** | **ANO** (přes Runtime) | Má vlastní `plan()` | Má vlastní `execute()` | Má vlastní `tool_map` | **ANO** (pokud běží starý loop) |
| **Legacy Command Router** | `core/intents/command_router.py` | `route_and_execute_command` | Starší testy / volající | Deleguje na `JarvisRuntime.run_task` | **ANO** | **ANO** | **ANO** | **ANO** | **ANO** | **NE** |
| **Dead PC Control** | `core/intents/command_router.py` | `execute_control_pc`, `execute_vision` | Mrtvý kód (nikdo nevolá) | Posílá HTTP příkazy přes `send_agent_command` | **NE** | **NE** | **NE** | **NE** | **NE** | **Mrtvý kód** |
| **Realtime Voice Pipeline** | `Voice/pipeline/realtime_pipeline.py` | `RealtimeVoicePipeline.process_text` | Testy (`test_voice_pipeline.py`) | Volá dodanou `response_stream_factory` a předává do TTS | **NE** | **NE** | **NE** | **NE** | **NE** | Izolovaný audio transport |

---

## 2. Detailní analýza klíčových komponent

### 2.1 GUI Controller (`interfaces/gui_controller.py`)
- **Problém:** V metodě `handle_user_message(message)` se provádí předčasné rozdělení:
  ```python
  parsed = classify_intent(message)
  if parsed.intent != IntentType.CHAT and not parsed.requires_llm:
      self.process_agent_request(parsed)  # -> runtime.run_task()
      return
  self.event_bus.emit("ai_request", message)  # -> process_ai_request() -> ai.engine.generate_stream()
  ```
  Zde normální chat obchází `JarvisRuntime`, čímž obchází jednotný `RequestContext`, `RequestStatus`, auditování, verifikaci i budoucí rozšíření (např. paměť a nástroje v konverzaci).
- **Problém č. 2:** Při potvrzení pozastavené akce (`resume_task` v `handle_user_message` řádky 296-302) GUI přímo volá `executor.run_plan(remaining_steps)` místo volání autoritativní metody `self.runtime.resume_task(...)`.

### 2.2 JarvisRuntime (`core/runtime.py`)
- **Problém:** `JarvisRuntime.run_task(goal)` v současnosti předpokládá, že každý cíl je akce:
  Směruje do `classify_routing_level(goal)` (`FAST_COMMAND`, `MINI_PLANNER`, `PLANNER_V2`), která vůbec nezná stav `CHAT`.
  Pokud uživatel pošle do `run_task` obyčejný dotaz ("Ahoj, jak se máš?" nebo "Co je to teorie relativity?"), runtime se pokusí vytvořit plán nástrojů přes `MINI_PLANNER`, což selže nebo vygeneruje nesmyslný krok.
- **Řešení:** `JarvisRuntime` musí mít autoritativní routing:
  - `CHAT` (čistá konverzace, otázky, vysvětlení): streamuje nebo generuje odpověď přes LLM providera pod jednotným `RequestContext` (stav `RequestStatus.COMPLETED` nebo `RequestExecutionStatus.CHAT_RESPONSE`), bez volání Executoru.
  - `FAST_COMMAND` (deterministický 1-krokový příkaz): okamžité spuštění nástroje přes Executor s verifikací.
  - `ACTION` / `PLANNER` (vícekroková úloha): Planner -> Executor -> Observe -> Verify -> Repair/Replan.
  - `MIXED` (úloha vyžadující zjištění informací i konverzační syntézu): Planner sestaví kroky, Executor je provede, verifikuje a runtime zformuje finální odpověď.

### 2.3 AutonomousAgent (`core/autonomous_agent.py`)
- **Problém:** Třída obsahuje 200 řádků starého duplicitního kódu:
  - `plan(goal)` – starý prompt
  - `parse_plan(text)` – starý parser
  - `deterministic_plan(goal)` – starý deterministický plánovač
  - `execute(action, value)` – starý mapper na tools
  - `evaluate(goal, history)` – stará evaluační smyčka
- **Řešení:** Ponechat `AutonomousAgent` jako tenký kompatibilní wrapper nad `JarvisRuntime.run_task(goal)`, zachovat rozhraní pro testy a odstranit duplicitní autonomní execution engine.

### 2.4 AI Engine (`ai/engine.py`)
- **Problém:** `ai/engine.py` obsahuje `send_agent_command(action, value)` – zastaralý HTTP wrapper posílající JSON na `/command`.
- **Řešení:** `ai/engine.py` má být striktně LLM providerem (volání Ollama, streaming, health check). Veškerá orchestrace úkolů patří do `JarvisRuntime`.

### 2.5 Jednotný model výsledku (Response Model)
- V současnosti `RuntimeResult` v `core/runtime.py` obsahuje `ok: bool`, `goal: str`, `route: str`, `summary: str`, atd.
- Chybí plnohodnotný `RequestResult` se strukturovanými explicitními stavy:
  - `COMPLETED`, `FAILED`, `CANCELLED`, `WAITING_FOR_CONFIRMATION`, `PAUSED`, `TIMEOUT`, `CHAT_RESPONSE`.
- Sjednotíme model tak, aby `RequestResult` (nebo rozšířený `RuntimeResult`) splňoval všechny požadavky a byl 100% zpětně kompatibilní.

---

## 3. Závěr auditu
Cíl této fáze je jasný: **Odstranit rozštěpení v `GuiController` a `AutonomousAgent`, rozšířit `JarvisRuntime` o nativní podporu režimu `CHAT`, sjednotit routing na jediné autoritativní místo a zavést strukturovaný `RequestResult`.**
