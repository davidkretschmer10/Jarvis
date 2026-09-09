# ONE TRUE RUNTIME – Sjednocená architektura zpracování požadavků

Tento dokument popisuje autoritativní architekturu systému Jarvis po dokončení sjednocení všech vstupních cest do jednoho společného runtime (`JarvisRuntime`).

---

## 1. Hlavní architektonický princip

**"Každý HIGH-LEVEL USER REQUEST jde přes `JarvisRuntime`."**

Všechny uživatelské vstupy (z GUI, hlasového vstupu, příkazové řádky CLI, HTTP API endpointu `/task` i autonomního agenta) slouží výhradně jako **vstupní/výstupní adaptéry**. Žádný adaptér neobsahuje vlastní autonomní plánovací cyklus, samostatné volání LLM pro řízení exekuce ani paralelní exekuční smyčku obcházející bezpečnostní a verifikační jádro.

---

## 2. Diagram toku požadavku

### Vstupní adaptéry do Runtime

```
GUI ────────┐
VOICE ──────┤
CLI ────────┼───> [ JARVIS RUNTIME ] ───> RequestResult ───> GUI (zobrazení / bublina)
HTTP /task ─┤                                           ───> VOICE (Piper TTS)
AUTO AGENT ─┘                                           ───> CLI (stdout)
                                                        ───> HTTP (JSON response)
```

### Vnitřní zpracování v JarvisRuntime

```
                 JARVIS RUNTIME (run_task / resume_task)
                            ↓
                     REQUEST CONTEXT
             (request_id, lifecycle status,
              source, cancellation token)
                            ↓
                    AUTHORITATIVE ROUTER
               (classify_routing_level)
                            ↓
     ┌──────────────────────┬──────────────────────┐
     ↓                      ↓                      ↓
  [ CHAT ]          [ FAST_COMMAND ]     [ PLANNER_V2 / MIXED ]
  (LLM provider         (1 deterministický       (vícekrokový plán
   stream tokenů)        krok, např. open_app)    znalostního grafu)
     │                      │                      │
     │                      └──────────┬───────────┘
     │                                 ↓
     │                             PLANNER
     │                                 ↓
     │                             EXECUTOR
     │                                 ↓
     │                                TOOL
     │                                 ↓
     │                              OBSERVE
     │                                 ↓
     │                              VERIFY
     │                         (State vs World)
     │                                 ↓
     │                         REPAIR / REPLAN
     │                       (při chybě ověření)
     └──────────────────────┬──────────────────────┘
                            ↓
                      REQUEST RESULT
            (status: RequestExecutionStatus,
             request_id, response_text, summary,
             execution_result, metadata)
```

---

## 3. Autoritativní moduly vs. Kompatibilní wrappery

| Modul | Účel | Typ komponenty |
|---|---|---|
| `core/runtime.py` (`JarvisRuntime`) | Jediný autoritativní vstupní bod exekuce pro všechny high-level požadavky. Řídí životní cyklus, směrování, streaming, exekuci i verifikaci. | **Autoritativní jádro** |
| `core/lifecycle.py` (`RequestContext`) | Globální thread-local stav požadavku, stavový automat, storno token, neměnné `request_id`. | **Autoritativní jádro** |
| `core/intents/fast_command_router.py` | Jediný autoritativní klasifikátor záměrů: rozlišuje `CHAT`, `FAST_COMMAND`, `MINI_PLANNER`, `PLANNER_V2`, `MIXED`. | **Autoritativní jádro** |
| `core/planner.py` (`Planner`) | Plánovač vícekrokových akcí pro složité dotazy. | **Autoritativní jádro** |
| `core/executor.py` (`Executor`) | Zabezpečené jádro exekuce (Observe → Act → Verify → Repair). | **Autoritativní jádro** |
| `tools/registry.py` (`ToolRegistry`) | Centrální registr všech deterministických nástrojů. | **Autoritativní jádro** |
| `interfaces/gui_controller.py` | Grafické uživatelské rozhraní. Veškeré požadavky deleguje do `self.runtime.run_task` / `resume_task`. | **Vstupní adaptér** |
| `Voice/voice_manager.py` / `Voice/pipeline/` | Hlasový adaptér (STT, TTS, VAD, wake word). Neřídí plánování ani vlastní mozek. | **Vstupní/výstupní adaptér** |
| `core/autonomous_agent.py` | Dříve paralelní agent loop. Nyní deleguje `run(goal)` výhradně do `JarvisRuntime.run_task(goal)`. | **Kompatibilní wrapper** |
| `core/intents/command_router.py` | Starý router příkazů. Nyní deleguje `route_and_execute_command` přímo do `JarvisRuntime`. | **Kompatibilní wrapper** |
| `ai/engine.py` | Poskytovatel LLM (Ollama konektor, streaming, sanitizace). Neobsahuje plánovací ani exekuční smyčku. | **LLM Provider** |
| `POST /task` (`core/agent.py`) | High-level HTTP endpoint pro spuštění úlohy přes `JarvisRuntime`. | **High-level Transport** |
| `POST /command` (`core/agent.py`) | Nízkoúrovňový transport pro zpětnou kompatibilitu a přímé volání systémových API. | **Low-level Transport** |

---

## 4. Jednotný Response Model (`RequestResult`)

Výsledek každého požadavku je strukturovaný objekt:

```python
@dataclass
class RequestResult:
    ok: bool
    goal: str
    route: str
    confidence: float
    steps: List[Dict[str, Any]]
    results: List[Dict[str, Any]]
    state: JarvisState
    summary: str
    request_id: str
    status: RequestExecutionStatus | str
    response_text: str
    execution_result: Optional[List[Dict[str, Any]]]
    verification_summary: Optional[str]
    error: Optional[str]
    metadata: Dict[str, Any]
    pending_confirmation: bool
    confirmation_message: str
    fallback_occurred: bool
    fallback_reason: Optional[str]
```

### Explicitní stavy (`RequestExecutionStatus`):
- `COMPLETED`: Úloha byla úspěšně dokončena a její výsledek ověřen.
- `FAILED`: Úloha nebo krok selhal a oprava nebyla možná.
- `CANCELLED`: Požadavek byl stornován uživatelem (GUI Stop, Hlasové přerušení, CLI Ctrl+C).
- `WAITING_FOR_CONFIRMATION`: Úloha byla pozastavena pro potvrzení uživatelem (riskantní akce, výběr z více kandidátů).
- `PAUSED`: Úloha je dočasně pozastavena.
- `TIMEOUT`: Vypršel časový limit provádění.
- `CHAT_RESPONSE`: Požadavek byl konverzační a odpověď byla úspěšně vygenerována bez použití akčních nástrojů.

---

## 5. Průchod jednotlivých typů požadavků

### A. Běžná konverzace (CHAT Mode)
Uživatel se zeptá na znalostní nebo běžnou otázku ("Jak se máš?", "Co je gravitace?"):
1. Vstup (GUI / Hlas / CLI) zavolá `JarvisRuntime.run_task(message)`.
2. Router identifikuje route `CHAT` bez akčních sloves.
3. Runtime přejde do stavu `EXECUTING` pod aktivním `RequestContext`.
4. Runtime zavolá LLM providera s tokenovým streamováním (`on_chunk` callback).
5. **Executor a Planner jsou zcela vynechány**, ale veškeré RequestContext invarianty a životní cyklus jsou zachovány.
6. Runtime vrátí `RequestResult` se statusem `CHAT_RESPONSE`.
7. GUI zobrazí streamovanou odpověď, Hlasový výstup ji přečte přes Piper TTS.

### B. Akční požadavek (ACTION Mode)
Uživatel požaduje provedení akce ve Windows ("Otevři Chrome", "Spusť kalkulačku"):
1. Vstup zavolá `JarvisRuntime.run_task(message)`.
2. Router identifikuje `FAST_COMMAND` nebo `PLANNER_V2`.
3. Pokud akce vyžaduje potvrzení nebo víceznačný výběr aplikace, Runtime nastaví status `WAITING_FOR_CONFIRMATION` a uloží stav do `paused_task`.
4. Při potvrzení ("ano") GUI zavolá autoritativní metodu `JarvisRuntime.resume_task()`.
5. `Executor` provede kroky podle schématu **Observe → Act → Verify**.
6. Výsledek je ověřen proti skutečnému stavu Windows OS (hledání okna, spuštěného procesu atd.).
7. Runtime vrátí `RequestResult` se statusem `COMPLETED` a souhrnem provedených a ověřených kroků.

### C. Smíšený požadavek (MIXED Mode)
Uživatel zadá kombinaci více akcí ("Řekni mi kolik je hodin a potom otevři Chrome"):
1. Router detekuje víceakční vzor a nastaví route `MIXED`.
2. `Planner` sestaví sekvenci kroků pokrývajících oba požadavky.
3. `Executor` provede sekvenci přes jednotné Tool jádro.
4. Výsledek se zkompletuje do jediného `RequestResult`.
