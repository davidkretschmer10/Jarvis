# JARVIS PRINCIPLES

Version: 1.0

Status: Draft

Last Updated: 2026-07-06 22:03:07 +02:00

Purpose: Define the guiding rules that every Jarvis feature, design decision, and implementation must respect.

---

## 1. Local First

Jarvis is local-first. Local operation has priority over cloud features, remote APIs, accounts, telemetry, and external servers. Private user data must stay on the user's machine. If a future feature requires the internet, it must be optional, explicit, and aligned with the local-first product goal.

## 2. UX First

Jarvis exists to improve the user's daily work. User experience has priority over technical spectacle. A feature is valuable only if it makes the assistant faster, clearer, safer, more natural, or more useful.

## 3. Predictability

Every action must be predictable. Jarvis must not surprise the user with hidden automation, unclear tool use, silent file changes, unexpected application control, or unexplained model behavior.

## 4. Explainability

Every important action must be explainable. Jarvis should be able to tell the user what it is doing, why it is doing it, what it needs, and what happened after the action finished.

## 5. Interruptibility

Every long, active, or spoken operation must be interruptible. The user must be able to stop speech, cancel a task, pause automation, or take control back without fighting the system.

## 6. Safety Before Automation

Automation is powerful only when it is safe. Actions that type, click, delete, move files, install software, run scripts, control terminals, or change system settings require clear guardrails and, when appropriate, confirmation.

## 7. Stability Before Expansion

Stable core workflows are more important than adding more features. Voice, GUI, desktop control, planner, memory, and vision must become reliable before the system grows into advanced plugins, workflows, learning, or multi-model routing.

## 8. Modular Architecture

Jarvis must be modular, but not over-engineered. Modules must have clear responsibilities and must be easy to test, replace, and extend. Complexity is allowed only when it reduces user-facing complexity or system risk.

## 9. Human Control

Jarvis is an assistant, not an uncontrolled operator. The user remains the final authority. Jarvis may suggest, plan, automate, and learn, but it must not take irreversible or sensitive action without user control.

## 10. Long-Term Product Thinking

Every change must fit the long-term goal: a local Windows AI assistant that feels coherent, capable, personal, and trustworthy. Short-term hacks that damage the product vision should be avoided.
