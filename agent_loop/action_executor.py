from __future__ import annotations

import logging
import time
from typing import Any
import asyncio

import requests

from agent_loop.step_result import ActionRequest, ActionResult


LOGGER = logging.getLogger(__name__)


class ActionExecutor:
    def __init__(
        self,
        agent_base_url: str = "http://127.0.0.1:5000",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.agent_base_url = agent_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def open_app(self, name: str) -> ActionResult:
        return self.execute(ActionRequest(type="open_app", value=name, description=f"Open app: {name}"))

    def write_text(self, text: str) -> ActionResult:
        return self.execute(ActionRequest(type="write_text", value=text, description="Write text"))

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> ActionResult:
        return self.execute(
            ActionRequest(
                type="click",
                value={"x": x, "y": y, "button": button, "clicks": clicks},
                description=f"Click at {x},{y}",
            )
        )

    def press_key(self, key: str) -> ActionResult:
        return self.execute(ActionRequest(type="press_key", value=key, description=f"Press key: {key}"))

    def hotkey(self, keys: list[str]) -> ActionResult:
        return self.execute(ActionRequest(type="hotkey", value=keys, description=f"Hotkey: {'+'.join(keys)}"))

    def execute(self, action: ActionRequest) -> ActionResult:
        started = time.perf_counter()
        try:
            agent_action, value = self._to_agent_payload(action)
        except ValueError as exc:
            elapsed = time.perf_counter() - started
            LOGGER.error("Invalid deterministic action: %s", exc)
            return ActionResult(False, action, error=str(exc), elapsed_seconds=elapsed)

        LOGGER.info("Executing deterministic action: %s value=%s", agent_action, value)

        try:
            response = requests.post(
                f"{self.agent_base_url}/command",
                json={"action": agent_action, "value": value},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            elapsed = time.perf_counter() - started
            LOGGER.error("Action timed out: %s", action)
            return ActionResult(False, action, error=f"Action timed out after {self.timeout_seconds:.1f}s", elapsed_seconds=elapsed)
        except requests.RequestException as exc:
            elapsed = time.perf_counter() - started
            LOGGER.error("Action request failed: %s", exc)
            return ActionResult(False, action, error=str(exc), elapsed_seconds=elapsed)
        except ValueError as exc:
            elapsed = time.perf_counter() - started
            LOGGER.error("Action returned invalid JSON")
            return ActionResult(False, action, error="Agent returned invalid JSON", elapsed_seconds=elapsed)

        ok = bool(data.get("ok", False)) if isinstance(data, dict) else False
        error = None if ok else str(data.get("result", "Agent action failed"))
        return ActionResult(
            ok=ok,
            action=action,
            data=data if isinstance(data, dict) else {"raw": data},
            error=error,
            elapsed_seconds=time.perf_counter() - started,
        )

    async def execute_async(self, action: ActionRequest) -> ActionResult:
        return await asyncio.to_thread(self.execute, action)

    def _to_agent_payload(self, action: ActionRequest) -> tuple[str, Any]:
        if action.type == "open_app":
            return "open", str(action.value)
        if action.type == "write_text":
            return "write", str(action.value)
        if action.type == "click":
            if not isinstance(action.value, dict):
                raise ValueError("click action requires dict value")
            return "click", action.value
        if action.type == "press_key":
            return "press", str(action.value)
        if action.type == "hotkey":
            if isinstance(action.value, list):
                return "hotkey", [str(key) for key in action.value]
            return "hotkey", [str(action.value)]
        raise ValueError(f"Unsupported deterministic action: {action.type}")
