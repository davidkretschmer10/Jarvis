# SECURITY AUDIT: Permission Model, Confirmation & Action Authorization

**Projekt:** Jarvis – Lokální Windows AI Asistent  
**Datum:** 2026-09-09  
**Verze:** Fáze: Safe Permission Model / Action Authorization Kernel  
**Autor:** Antigravity Agent  

---

## 1. Současný stav bezpečnostní architektury

Před touto fází prošel Jarvis sjednocením běhového prostředí do **One True Runtime** (`JarvisRuntime`), zavedením **Execution Safety Kernel** a cyklu **Observe → Act → Verify**.

Přesto v systému přetrvávaly zásadní bezpečnostní mezery:
1. **Absence centrální bezpečnostní politiky (SecurityPolicy):** Před spuštěním kroku v `Executor` neprobíhala žádná evaluace rizika ani oprávnění. Rozhodování bylo buď zcela volné, nebo ad-hoc uvnitř konkrétního nástroje.
2. **Nebezpečný mechanismus `action_confirmed == True`:** Potvrzení uživatelem bylo reprezentováno prostou boolean hodnotou v `state.data["action_confirmed"]`. Tento flag neměl vazbu na `request_id`, `step_id`, konkrétní nástroj ani expiraci.
3. **Nízká ochrana endpointu `/command`:** HTTP endpoint `/command` v `core/agent.py` umožňoval přímé volání akcí typu `open_path` (spouštějící `os.startfile(path)` nebo `subprocess.Popen([path])`) pro jakoukoliv cestu v souborovém systému bez jakékoliv autorizace.
4. **Chybějící metadata nástrojů v ToolRegistry:** Nástroje v `ToolRegistry` deklarovaly pouze `name`, `description` a `input_schema`. Chyběla metadata o schopnostech (`capability`), rizikovosti (`risk`), časovém limitu a požadavcích na autorizaci.

---

## 2. Audit nástrojů a systémových akcí

| Nástroj / Funkce | Vstup | Schopnost (Capability) | Riziko | Současná ochrana | Vyžaduje potvrzení? | Lze obejít? | Doporučené chování v Policy |
|---|---|---|---|---|---|---|---|
| `OpenAppTool` (`open_app`) | `name: str` | `LAUNCH_APPLICATION` | **LOW / MEDIUM** | Kontrola v cache aplikací; víceznačnost vyžaduje výběr | Jen při nejednoznačném výběru aplikace | Ano, při přesném názvu aplikace se spustí okamžitě | **ALLOW** pro běžné aplikace; **REQUIRE_CONFIRMATION** při spouštění systémových utilit |
| `open_path` (`/command`) | `value: str` (cesta) | `PROCESS_START` | **CRITICAL** | Žádná (pouze `os.path.exists`) | **NE** | **ANO (závažný bypass)** | **DENY** pro systémové/nebezpečné cesty; **REQUIRE_CONFIRMATION** pro uživatelské binárky |
| `WriteTextFileTool` (`write_text_file`) | `path: str`, `content: str` | `MODIFY_FILE` / `CREATE_FILE` | **MEDIUM** | `_resolve_under_root` (nepustí ven z workspace) + `action_confirmed` | Ano (přes `action_confirmed`) | Ano, pokud je nastaven globální `action_confirmed` | **REQUIRE_CONFIRMATION** pro existující soubory; **ALLOW** v dočasném workspace |
| `ReadTextFileTool` (`read_text_file`) | `path: str` | `READ_FILE` | **SAFE** | `_resolve_under_root` (pouze uvnitř workspace) | Ne | Ne (izolováno do workspace) | **ALLOW** v rámci povoleného scope |
| `ListDirTool` (`list_dir`) | `path: str` | `READ_FILE` | **SAFE** | `_resolve_under_root` | Ne | Ne | **ALLOW** |
| `ClickTool` (`click`) | `x: int`, `y: int` | `CLICK` | **LOW** | Žádná | Ne | Ano (libovolné kliknutí) | **ALLOW** |
| `SmartClickTool` (`smart_click`) | `target: str` | `UI_CLICK` | **LOW / MEDIUM** | Pokud confidence < 0.70 nebo více prvků, vyžaduje `action_confirmed` | Podmíněně podle confidence | Ano, při confidence ≥ 0.70 | **ALLOW** při vysoké spolehlivosti; **REQUIRE_CONFIRMATION** při nejednoznačnosti |
| `WriteTextTool` (`write_text`) | `text: str` | `TYPE_TEXT` | **LOW** | Žádná | Ne | Ano | **ALLOW** |
| `SmartWriteTool` (`smart_write`) | `target: str`, `text: str` | `TYPE_TEXT` | **MEDIUM** | Confidence < 0.70 vyžaduje `action_confirmed` | Podmíněně | Ano, při confidence ≥ 0.70 | **ALLOW** / **REQUIRE_CONFIRMATION** pro citlivá pole |
| `PressKeyTool` (`press_key`) | `key: str` | `PRESS_KEY` | **LOW** | Žádná | Ne | Ano | **ALLOW** |
| `HotkeyTool` (`hotkey`) | `keys: list[str]` | `PRESS_KEY` | **LOW / MEDIUM** | Žádná | Ne | Ano | **ALLOW** pro běžné; **REQUIRE_CONFIRMATION** pro destruktivní zkratky |
| `SmartCheckboxTool` (`smart_checkbox`) | `target: str`, `checked: bool` | `UI_CLICK` | **LOW** | Confidence check | Podmíněně | Ano | **ALLOW** |
| `CloseWindowTool` (`close_window`) | `{}` | `PROCESS_TERMINATE` | **HIGH** | `action_confirmed` kontrola | Ano | Ano, přes starý boolean flag | **REQUIRE_CONFIRMATION** vázané na konkrétní okno a `request_id` |
| `ConfirmDialogTool` (`confirm_dialog`) | `{}` | `UI_CLICK` | **HIGH** | `action_confirmed` kontrola | Ano | Ano | **REQUIRE_CONFIRMATION** se zobrazením textu dialogu |
| `CancelDialogTool` (`cancel_dialog`) | `{}` | `UI_CLICK` | **LOW** | Žádná | Ne | Ne | **ALLOW** |
| `OpenWebsiteTool` (`open_website`) | `url: str` | `OPEN_URL` | **LOW** | Žádná (otevře výchozí prohlížeč) | Ne | Ano | **ALLOW** pro bezpečné protokoly (http/https); **DENY** pro nebezpečná schémata (file://, javascript:) |
| `OpenSearchResultTool` (`open_search_result`) | `query: str`, `engine: str` | `OPEN_URL` | **LOW** | Žádná | Ne | Ne | **ALLOW** |
| `ScreenshotTool` (`screenshot`) | `{}` | `SCREEN_OBSERVATION` | **SAFE** | Ukládá do určené složky | Ne | Ne | **ALLOW** |
| `ReadScreenTool` (`read_screen`) | `lang: str` | `SCREEN_OBSERVATION` | **SAFE** | Žádná | Ne | Ne | **ALLOW** |
| `AgentHealthTool` (`agent_health`) | `{}` | `SCREEN_OBSERVATION` | **SAFE** | Žádná | Ne | Ne | **ALLOW** |
| `RefreshAppsTool` (`refresh_apps`) | `{}` | `LAUNCH_APPLICATION` | **SAFE** | Žádná | Ne | Ne | **ALLOW** |
| *Plánované destruktivní akce (Delete File / Shell)* | `path / cmd` | `DELETE_FILE` / `SHELL_COMMAND` | **HIGH / CRITICAL** | V současnosti neexistují v registry, ale Planner je může vygenerovat | Neexistuje | Ano (přímý pád nebo spuštění) | **REQUIRE_CONFIRMATION** pro smazání v user scope; **DENY** pro systémové cesty a nebezpečný shell |

---

## 3. Nalezené zranitelnosti a architektonické slabiny

### Zranitelnost 1: Bypassing Policy přes `/command open_path`
- **Popis:** `/command` s `{"action": "open_path", "value": "C:\\Windows\\System32\\cmd.exe"}` spustí proces přímo přes `os.startfile` nebo `subprocess.Popen`.
- **Dopad:** Kdokoliv na lokálním stroji může přes HTTP vyvolat libovolný proces bez vědomí uživatele.
- **Náprava:** Endpoint `/command` musí validovat cestu přes `SecurityPolicy` a vyžadovat autorizaci, nebo musí být chráněn lokálním autorizačním tokenem vytvořeným při startu aplikace v AppData.

### Zranitelnost 2: Cross-Request Confirmation Forgery
- **Popis:** `action_confirmed` je prostý klíč ve stavovém slovníku `JarvisState.data`.
- **Dopad:** Pokud požadavek A vyvolal pozastavení z důvodu potvrzení, a uživatel v mezidobí spustil požadavek B, potvrzení mohlo autorizovat jinou akci v jiném kontextu.
- **Náprava:** Zavedení strukturovaného objektu `ConfirmationToken` / `ConfirmationRequest` svázaného s `request_id`, `step_id`, konkrétním nástrojem, argumenty a časovou expirací.

### Zranitelnost 3: Expirace potvrzení neexistuje
- **Popis:** Jakmile byl stav nastaven na potvrzení nebo čekal v GUI, neexistoval časový limit, po kterém by schválení propadlo.
- **Náprava:** Přidání `expires_at` (výchozí hodnota např. 5 minut). Po vypršení je status `EXPIRED` a akce se odmítne.

### Zranitelnost 4: Chybějící Resource Scoping (Cesta k souborům)
- **Popis:** `WriteTextFileTool` brání pouze úniku z workspace, ale neexistuje obecná klasifikace cest (User Documents vs. System32 vs. Program Files).
- **Náprava:** Zavedení modulu pro klasifikaci cest:
  - `USER_DATA` (`Documents`, `Pictures`, `Desktop`, `Downloads`, Workspace)
  - `APP_DATA` (`AppData/Roaming/Jarvis`, `AppData/Local/Temp`)
  - `SYSTEM` (`C:\Windows`, `System32`, `Program Files`, registry, kořeny disků)
  - `UNKNOWN` / `EXTERNAL`
  Operace nad `SYSTEM` cestami jsou klasifikovány jako `CRITICAL` (**DENY**) nebo `HIGH` (**REQUIRE_CONFIRMATION**).

### Zranitelnost 5: Absence Audit Logu
- **Popis:** Akce se logovaly pouze do konzole nebo do nestrukturovaných log souborů. Chyběl auditní záznam o tom, kdo akci inicioval, jaké měla riziko, jak byla autorizována a jak dopadla verifikace.
- **Náprava:** Zavedení modulu `core/action_audit.py` s ukládáním do AppData, s ochranou proti poškození a automatickou redakcí citlivých údajů (hesla, tokeny).

---

## 4. Návrh autorizačního řetězce (Target Architecture)

```
       USER REQUEST (GUI / Voice / CLI / HTTP)
                         ↓
                  JARVIS RUNTIME
                         ↓
                  REQUEST CONTEXT
                         ↓
                      ROUTER
                         ↓
                     PLANNER
                         ↓
               ┌───────────────────┐
               │  SECURITY POLICY  │ <── Resource Scopes (Path / System / Net)
               │ (evaluate_action) │ <── Tool Metadata (Capability / Risk)
               └───────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
     [ ALLOW ]       [ CONFIRM ]       [ DENY ]
        │                │                │
        │       ┌─────────────────┐       └──> Terminal Failure (Security Denied)
        │       │  CONFIRMATION   │
        │       │  TOKEN ENGINE   │
        │       │ (ReqID, StepID, │
        │       │  Resource, Exp) │
        │       └─────────────────┘
        │                │
        │          USER APPROVAL?
        │          ├── ANO ──> Validated Token
        │          └── NE / EXPIRED ──> Terminal Cancel / Expired
        │                │
        └────────┬───────┘
                 ↓
             EXECUTOR (run_step)
                 ↓
               TOOL (run)
                 ↓
             OBSERVE → VERIFY
                 ↓
            ACTION AUDIT (append immutable entry with secret redaction)
                 ↓
              RESULT
```

---

## 5. Závěr auditu

Současná architektura má robustní základ v `JarvisRuntime`, `RequestContext` a `Executor`. Zavedení `SecurityPolicy`, explicitních `ToolCapability` a `ActionRisk`, strukturovaného `ConfirmationToken` a `ActionAudit` vyřeší všechny identifikované zranitelnosti a vytvoří bezpečný, spolehlivý lokální systém bez zásahu do funkčnosti schválených nástrojů.
