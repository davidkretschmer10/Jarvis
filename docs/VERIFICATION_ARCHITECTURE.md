# Verification Architecture (Observe → Act → Verify → Repair/Replan)

## 1. Overview and Core Philosophy

In previous versions of Jarvis, execution followed a naive model:
```
plan → tool execution → ok=True → next step
```
In this model, if a tool returned `ok=True`, Jarvis immediately assumed that the step succeeded in the physical world. However, a tool returning `ok=True` only means:
> *"The Python function or launch command was invoked without raising an unhandled exception."*

It did **not** prove that:
- The target application actually opened and stayed running.
- The target file was created on disk with valid bytes.
- The deleted file was actually removed.
- The UI element was actually focused or clicked.

The new **Observe → Act → Verify → Repair/Replan** loop establishes four distinct layers of truth:
1. **Tool Execution Success:** Did the tool function run without crashing?
2. **Observation:** What does the actual Windows environment state look like right now?
3. **Verified Result:** Does independent physical evidence match what was expected?
4. **Overall Task Success:** Did all steps achieve verified completion without hidden failures?

---

## 2. Core Data Models

### 2.1 `ToolResult`
The output of a tool's internal execution (`{"ok": bool, "result": Any, "error": Optional[str]}`). It only states what the tool attempted and reported.

### 2.2 `Observation` (`core/observation.py`)
Factual, objective observation of external environmental state:
- `source`: Name/identifier of observation source (e.g. `"ApplicationVerifier"`, `"FileVerifier"`, `"psutil"`).
- `type`: `ObservationType` enum (`PROCESS`, `WINDOW`, `FILE`, `DIRECTORY`, `SCREEN`, `OCR`, `BROWSER`, `TOOL_RESULT`, `SYSTEM`).
- `data`: Extracted state facts (e.g. `{"exists": True, "size": 1024}`).
- `confidence`: Observation confidence (0.0 to 1.0).
- `evidence`: Concrete supporting facts (process list samples, file stats, window titles).
- `timestamp`: Epoch timestamp.

### 2.3 `VerificationResult` (`core/verification.py`)
The evaluation comparing the step's expected outcome against independent observations:
- `status`: `VerificationStatus` (`VERIFIED`, `FAILED`, `UNKNOWN`, `NOT_APPLICABLE`).
- `verifier`: Name of the verifier that performed the check.
- `expected`: Description of what was expected.
- `observed`: Description of what was physically observed.
- `evidence`: Evidence dictionary.
- `message`: Diagnostic message.
- `timestamp`: Timestamp of verification.

---

## 3. The `UNKNOWN` Status Invariant

**`UNKNOWN` is NOT `VERIFIED`.**

If Jarvis cannot prove deterministically that an action produced the intended outcome (for example, typing raw keystrokes or blind mouse clicks without an active UI delta), the result status is explicitly marked `UNKNOWN`.

- `UNKNOWN` is never converted to `VERIFIED`.
- If an action cannot be verified, the runtime logs and reports that the step completed with `UNKNOWN` verification status.
- In summary outputs, the user is notified if any step completed unverified: `(stav některých kroků zůstal UNKNOWN)`.

---

## 4. Deterministic Verifiers First

Verifiers strictly follow the principle: **Deterministic Verifier First**. Heavy or probabilistic mechanisms (such as OCR or Vision models) are used only when deterministic OS-level checks are impossible.

| Priority | Category | Mechanism | Target Tools |
| :--- | :--- | :--- | :--- |
| **1** | **File Operations** | `os.path.isfile`, `os.path.getsize`, content inspection | `write_file`, `create_file`, `append_file`, `delete_file` |
| **2** | **Directory Operations** | `os.path.isdir`, `os.path.exists` | `make_directory`, `create_dir`, `delete_dir` |
| **3** | **Applications** | `tasklist` image scan + `ctypes.windll.user32` visible windows | `open_app`, `launch_app`, `close_app` |
| **4** | **Browser Operations** | Known browser processes (`chrome.exe`, `msedge.exe`, etc.) | `open_browser`, `open_url` |
| **5** | **UI Interactions** | Visual delta check (`observed_delta`) or fallback to `UNKNOWN` | `mouse_click`, `type_text`, `press_key` |
| **6** | **Pass-Through** | Read-only inspection (`NOT_APPLICABLE`) | `read_file`, `list_directory`, `system_info`, `search_web` |

---

## 5. Security & Safety Invariants

1. **Verifiers are Strictly Read-Only:**
   - Verifiers only **OBSERVE**, they never **ACT**.
   - A file deletion verifier checks if the file exists; it will never delete the file itself.
   - All verifiers inherit from `BaseVerifier` with `is_read_only = True`.

2. **Cooperative Cancellation & Timeout Propagation:**
   - Verifiers check `ctx.is_cancelled` and `ctx.is_timed_out` before running and after inspection.
   - If cancelled during verification, execution stops immediately with `StepExecutionStatus.CANCELLED`.

3. **Consistent `request_id`:**
   - The same `request_id` is propagated across Runtime → Executor → Verifier → Repair → Replan → EventBus.

---

## 6. Execution Loop: Repair, Re-verification, and Replan

When a tool executes:
```
[EXECUTE TOOL]
      ↓
[TOOL OK == TRUE] ─── No ───> [REPAIR / REPLAN / TERMINAL FAILURE]
      ↓ Yes
[VERIFY STEP]
      ↓
  Status?
  ├── VERIFIED / NOT_APPLICABLE ───> [STEP SUCCESS] ───> Next Step
  ├── UNKNOWN ─────────────────────> [STEP UNVERIFIED] ───> Next Step (Explicit UNKNOWN)
  └── FAILED ──────────────────────> [TREAT AS FAILED STEP]
                                            ↓
                                     [AUTO-REPAIR] (budget permitting)
                                            ↓
                                     [RE-VERIFY AFTER REPAIR]
                                       ├── VERIFIED ──> [STEP SUCCESS]
                                       └── FAILED ───> [REPLAN WITH OBSERVATION]
                                                            ↓
                                                       [NEW PLAN / TERMINAL FAILURE]
```

### Re-verification Invariant
If an auto-repair action runs, the verifier **re-checks the physical state**. If the physical state still fails verification, the repair is marked as unsuccessful and execution moves to replanning.

### Replan with Structured Observation
When replanning is triggered due to a verification failure, the `Planner` receives structured diagnostic context:
- Intended action and failed step
- Verification status (`FAILED`)
- Expected state vs. Observed state
- Concrete evidence dictionary
- Remaining budgets (`repairs_remaining`, `replans_remaining`)
