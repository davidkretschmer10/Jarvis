# VISION ARCHITECTURE – PHASE 10: REAL VISION + OCR + GUI INTERACTION KERNEL

Authoritative Architecture and Reference Guide for Jarvis Vision, OCR, and GUI Interaction.

---

## 1. Executive Summary

Phase 10 establishes a local-first, deterministic, and safe Vision and GUI interaction kernel for Jarvis.
It does **not** introduce a secondary agent loop. Instead, it integrates directly as a sensory and verification adapter on top of the established `One True Runtime`, `SecurityPolicy`, `Executor`, `Observation`, and `Verification` stack.

```
USER REQUEST / VOICE COMMAND
            ↓
       JarvisRuntime
            ↓
        Executor
            ↓
Pre-Action Observation (VisionService)
            ↓
      TargetResolver (Deterministic -> OCR -> Vision -> Coordinates)
            ↓
      SecurityPolicy (CLICK_SAFE / CLICK_MEDIUM / CLICK_HIGH)
            ↓
          Action (PyAutoGUI / Windows Controls)
            ↓
Post-Action Observation (VisionService)
            ↓
Verification (UIInteractionVerifier / Screen Delta / Expected State)
            ↓
  Repair / Replan (Bounded by MAX_REPAIRS)
```

---

## 2. Core Components

### 2.1 Observation Layer (`core/observation.py`)
- Standardized `ObservationType.VISION`, `SCREEN`, `OCR`, `WINDOW`, `PROCESS`, `FILE`, `DIRECTORY`, `BROWSER`, `TOOL_RESULT`, `SYSTEM`.
- `BoundingBox(x, y, width, height)`:
  - Boundary containment check: `is_inside(screen_width, screen_height)`.
  - Geometric center calculation: `center -> (cx, cy)`.
  - Negative or out-of-screen coordinates are rejected immediately.
- `VisionElement`:
  - Encapsulates recognized GUI element with `id`, `text`, `bbox`, `confidence`, `element_type`, `source`.
- `VisionObservation`:
  - Structured snapshot containing `screen_width`, `screen_height`, `window_title`, `elements`, `screenshot_path`, `timestamp`, `image_hash`.
  - Staleness evaluation: `is_stale(max_age_seconds=5.0)` prevents using outdated screen observations.

### 2.2 Vision Service & Providers (`core/vision.py`)
- Single authoritative entry point for visual screen capture and OCR analysis.
- `BaseOCRProvider` & `TesseractOCRProvider`:
  - Differentiates statuses: `OCR_AVAILABLE`, `OCR_UNAVAILABLE`, `OCR_FAILED`.
  - If Tesseract is not installed on the system, the provider returns `OCR_UNAVAILABLE` gracefully without raising unhandled exceptions.
  - When available, extracts words and groups adjacent tokens on the same line into coherent UI elements.
- `BaseVisionModelProvider` & `OllamaVisionProvider`:
  - Differentiates statuses: `VISION_AVAILABLE`, `VISION_UNAVAILABLE`, `VISION_FAILED`.
  - Connects to the local Ollama instance (using the central HTTP session).
  - Checks if a multimodal vision model (e.g. `qwen2.5-vl:7b`) is installed. If absent, reports `VISION_UNAVAILABLE`.
  - Completely local; no cloud API keys or external services required.
- `VisionService`:
  - Coordinates screenshot capture (`pyautogui`), active window detection (`ctypes.windll.user32`), and fast SHA-256 screen thumbnail hashing (`image_hash`).
  - Implements TTL caching (`max_observation_age`).

---

## 3. Target Resolver (`core/target_resolver.py`)

The centralized `TargetResolver` enforces a strict resolution hierarchy:

1. **Deterministic Window / Control Information**:
   - Queries matching active window titles or Win32 controls are resolved first.
2. **OCR Elements**:
   - Matches visible text on screen using exact and fuzzy matching, with support for semantic types (e.g. *"tlačítko Přihlásit"*, *"checkbox Souhlasím"*, *"pole Heslo"*) and dialog synonyms (*"potvrdit"* -> OK, *"zrušit"* -> Cancel).
3. **Local Vision Model**:
   - Semantic visual element detection if a multimodal model is active.
4. **Explicit Coordinates**:
   - Coordinates (`"500, 300"`) are checked against screen boundaries. They cannot bypass verification or safety rules.

### Resolution Safeguards
- **Confidence Threshold**: Elements with OCR confidence below the threshold (default `0.70`) receive status `LOW_CONFIDENCE` and cannot be clicked without user confirmation or replan.
- **Ambiguity Detection**: If two or more elements have matching scores within `0.05` delta, status `AMBIGUOUS` is returned with the candidate list, requiring confirmation.
- **Screen Bounds Check**: Any candidate whose bounding box extends outside the active screen dimensions is marked `OUT_OF_BOUNDS`.

---

## 4. Security Boundary (`core/security_policy.py`)

Vision is a **sensory observation tool**, never a security authority.
- Vision reports: *"A button with text 'Delete Account' is likely located at [450, 215]."*
- `SecurityPolicy` decides: *"Is clicking 'Delete Account' allowed?"*
- Destructive target keywords (`delete`, `smazat`, `odstranit`, `purchase`, `koupit`, `shutdown`, `format`, `submit`) automatically escalate risk to `ActionRisk.HIGH`.
- Actions at `HIGH` risk require explicit user confirmation via `ConfirmationManager`.
- Sensitive screen contents (passwords, tokens) are redacted in `ActionAuditLogger`.

---

## 5. Screen Change Verification (`core/verification.py`)

After a GUI action is executed, `UIInteractionVerifier` independently evaluates the resulting state:
1. **Screen Hash Delta**:
   - Compares `pre_hash` and `post_hash`. If the screen image changed, a visual delta is confirmed.
2. **Expected GUI State**:
   - Supports step expectations:
     - `"text appears: <Text>"`: verifies that expected text appeared on screen.
     - `"button disappears: <Target>"`: verifies that a clicked dialog or button vanished.
     - `"window title contains: <Title>"`: verifies active window change.
3. **Strict Truthfulness**:
   - If OCR is unavailable, text-based verification evaluates to `UNKNOWN` (never falsely claiming `VERIFIED` or `SUCCESS`).
   - If no verifiable delta can be confirmed, the outcome is `UNKNOWN`.

---

## 6. Bounded Repair Loop

If GUI verification fails:
1. A fresh screenshot observation is captured.
2. The target is re-resolved.
3. `Executor` attempts an auto-repair action.
4. The action is **re-verified**.
5. Repairs are hard-bounded by `max_repairs = 1`. If recovery fails, execution stops safely and does not enter an infinite loop.
