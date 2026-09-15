# Jarvis Integration & Runtime Architecture (Phase 11)

## 1. Overview & Core Invariants

Jarvis is a fully local, deterministic Windows AI assistant. It operates entirely on-device without external cloud AI dependencies or secret tokens. All user requests across all interaction modalities flow through a single, authoritative execution kernel:

```
                      USER
                       │
       ┌───────────────┼───────────────┬───────────────┐
       ▼               ▼               ▼               ▼
      GUI            VOICE            CLI          HTTP /task
       │               │               │               │
       └───────────────┼───────────────┴───────────────┘
                       ▼
              [ JarvisRuntime.run_task() ]
                       │
                       ▼
             [ Fast Router / Planner ]
                       │
                       ▼
                  [ Executor ]
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
[ SecurityPolicy ]         [ ConfirmationManager ]
(Risk & Path Guards)        (Single-use Action Tokens)
         │                           │
         └─────────────┬─────────────┘
                       ▼
               [ ToolRegistry ]
                       │
                       ▼
               [ Windows Tools ]
                       │
                       ▼
          [ Observation (RAM Only) ]
                       │
                       ▼
                 [ Verifier ]
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
    [ VERIFIED ]             [ UNKNOWN / FAILED ]
         │                           │
         │                           ▼
         │                 [ Repair / Replan Loop ]
         │                           │
         └─────────────┬─────────────┘
                       ▼
               [ RequestResult ]
          (Truthful Status & Summary)
                       │
       ┌───────────────┼───────────────┐
       ▼                               ▼
 [ GUI Event Bus ]              [ TTS Speech ]
```

---

## 2. Invariants & Guardrails

### 2.1 One True Execution Path
High-level requests (whether from GUI buttons/chat, Voice wake words, CLI commands, HTTP `/task` endpoints, or the AutonomousAgent loop) never execute system tools directly. They instantiate or invoke `JarvisRuntime.run_task()`, which establishes a unique `RequestContext`, evaluates the security boundary, executes planned steps, and verifies real-world outcomes.

### 2.2 UNKNOWN ≠ SUCCESS
A step or request is **only** successful when its outcome is deterministically proven:
- `VERIFIED`: Deterministic verification passed (process active, window title matched, file created/modified/deleted, or UI screen visual delta confirmed).
- `NOT_APPLICABLE`: Read-only queries or dry-run simulated steps where no world mutation occurred.
- `UNKNOWN`: Tool returned `ok=True`, but the actual physical delta on the system could not be proven. **UNKNOWN is never coerced into SUCCESS.** The request terminates with `RequestExecutionStatus.UNKNOWN` and `ok=False`.
- `FAILED`: Reality check directly contradicted expected outcome, triggering Repair -> Replan -> Budget exhaustion.

### 2.3 Single-Use Bound Confirmation
Confirmations are strictly bound to `(request_id, step_id, tool, resource, risk, expires_at)`. Once a confirmed step completes, `ConfirmationManager.consume()` permanently invalidates the token to prevent replay attacks or stale state reuse across different steps.

### 2.4 Screenshot Privacy & Memory Safety
`VisionService.capture_observation()` maintains captures entirely in RAM (`PIL.Image`). Screenshots are discarded after processing unless disk persistence is explicitly requested for diagnostic export (`save_to_disk=True` or `save_screenshots=True`).

### 2.5 Central Local AI Stack
Parallel, ad-hoc HTTP sessions (`requests.post`, `requests.Session()`) for Ollama are prohibited. All vision and LLM modules use the central connection pool provided by `ai.engine.get_ollama_session()`, which enforces connection reuse, keep-alive, and health tracking.

---

## 3. Subsystem Breakdown

### 3.1 TargetResolver Hierarchy
GUI element resolution enforces a strict 4-tier hierarchy:
1. **Deterministic Window / Control**: Inspects Windows active foreground titles via `user32.dll`.
2. **OCR Elements & Bounding Boxes**: Parses text via Tesseract with fuzzy matching, spatial grouping, and confidence scoring.
3. **Local Vision Model**: Uses `qwen2.5-vl` via Ollama for semantic coordinate detection when installed.
4. **Explicit Coordinates**: Fallback for explicit coordinate pairs (`[x, y]`), validating screen bounds.

**Rejection Safeguards:**
- `AMBIGUOUS`: Flagged when multiple candidates have competing confidence scores (< 0.05 delta). Rejects blind clicking.
- `STALE_OBSERVATION`: Flagged when observation age exceeds 5.0 seconds. Requires fresh capture.
- `LOW_CONFIDENCE`: Flagged when element confidence is below 0.70, prompting confirmation.
- `OUT_OF_BOUNDS`: Flagged when bounding box exceeds physical screen dimensions.

### 3.2 Real GUI Verification Loop
Desktop actions (`click`, `smart_click`, `type_text`, `press`) do not assume success upon tool return:
1. **T0 Observation**: Screen captured in RAM, image hash `pre_hash` computed.
2. **Act**: OS input dispatched via PyAutoGUI.
3. **T1 Observation**: Screen re-captured in RAM, `post_hash` computed.
4. **Verify**:
   - Visual delta: `pre_hash != post_hash`.
   - Expected text: element appearance or disappearance verified.
   - If no verifiable delta is detected, status is marked `UNKNOWN`.

### 3.3 Repair & Replan Loop
When a step verification fails:
1. **Auto-Repair (Max 1)**: Evaluates registered repair actions (wait, refocus window, scroll).
2. **Re-Verification**: Re-runs step verifier after repair action.
3. **Replan (Max 2)**: If repair fails or is unavailable, `Planner.replan()` generates alternative sub-steps given the error message and failure observation.
4. **Budget Guard**: Aborts when max steps (15), max repairs (1), or max replans (2) are exhausted.

### 3.4 Request Lifecycle & GUI Synchronization
Every request transitions through authoritative states on `RequestContext`:
`CREATED` -> `ROUTING` -> `PLANNING` -> `EXECUTING` -> `VERIFYING` -> `COMPLETED` / `FAILED` / `UNKNOWN` / `CANCELLED` / `WAITING_FOR_USER`.

The GUI (`GuiController` and `VoiceStateManager`) subscribes to these real event bus signals, dynamically updating the status labels and visuals without simulated timers.

---

## 4. Integration Test Matrix

| Entry Point | Runtime Path | SecurityPolicy | Verifier | Real Windows Test Result |
| :--- | :--- | :--- | :--- | :--- |
| **GUI** | `GuiController.process_request()` -> `JarvisRuntime.run_task()` | Evaluated | UI / File / Window Verifiers | **PASS** |
| **CLI** | `main.py --task` -> `JarvisRuntime.run_task()` | Evaluated | Deterministic Verifiers | **PASS** |
| **Voice** | `RealtimeVoicePipeline` -> `JarvisRuntime.run_task()` | Evaluated | Deterministic Verifiers | **PASS** |
| **HTTP /task** | `AgentServer.handle_task()` -> `JarvisRuntime.run_task()` | Evaluated | Deterministic Verifiers | **PASS** |
| **AutonomousAgent** | `AutonomousAgent.run_goal()` -> `JarvisRuntime.run_task()` | Evaluated | Deterministic Verifiers | **PASS** |
| **PC Control GUI** | `SmartClickTool` -> `TargetResolver` -> `UIInteractionVerifier` | Evaluated | Screen Delta & OCR Verifiers | **PASS** |
