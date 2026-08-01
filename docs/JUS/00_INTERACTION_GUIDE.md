# INTERACTION GUIDE

Version: 1.0

Status: Draft

Last Updated: 2026-07-06 22:03:07 +02:00

Purpose: Define how users should interact with Jarvis across voice, chat, GUI, desktop mode, and automation.

---

## 1. Interaction Model

Jarvis supports four primary interaction modes: voice, text chat, desktop mode, and GUI control. All modes must share the same assistant state, memory, permissions, and task context.

The user can start in one mode and continue in another. A spoken command can appear in chat. A chat task can show progress in the GUI. A desktop action can ask for confirmation by voice and GUI.

## 2. Voice Interaction

Voice interaction is intended for natural, fast commands. Jarvis should support wake word, continuous listening, push-to-talk, barge-in, and hands-free workflows. It must speak clearly, avoid long unnecessary responses, and adapt to contexts like gaming mode or meeting mode.

When Jarvis is speaking, the user must be able to interrupt it. After interruption, Jarvis should stop speaking immediately and listen for the next command.

## 3. Chat Interaction

Chat interaction is intended for precision, long prompts, code, explanations, and reviewable history. Chat must support streaming responses, readable message bubbles, Markdown, code blocks, import/export, search, and long conversation continuity.

Chat should show system actions when Jarvis performs automation. It should not hide tool usage when the action affects the user's computer.

## 4. GUI Interaction

The GUI is the command center. It must provide chat, voice mode, desktop mode, settings, memory, tools, models, logs, vision, automation, plugins, developer console, statistics, and performance views as the product matures.

The GUI must make assistant state visible: waiting, listening, recording, transcribing, thinking, acting, speaking, waiting for confirmation, completed, failed, or blocked.

## 5. Desktop Mode

Desktop mode is a lightweight always-available presence on the Windows desktop. The target is a floating transparent orb that stays on top, opens chat when clicked, activates by voice, shows system state, and animates based on Jarvis activity.

Desktop mode must never obscure important user work or interfere with games, meetings, or fullscreen workflows.

## 6. Automation Interaction

Automation must be step-based and understandable. Jarvis should show what it plans to do, what step is running, what succeeded, what failed, and what needs user help.

Dangerous actions require confirmation. Ambiguous actions require clarification. Repeated workflows should become macros only when the user understands and approves them.

## 7. Failure Interaction

When something fails, Jarvis must be clear and calm. It should explain what failed, why it likely failed, what it can try next, and what the user can do. It must not pretend success.
