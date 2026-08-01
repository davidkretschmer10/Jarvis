from __future__ import annotations

import json
import logging
import re
from typing import Any


LOGGER = logging.getLogger(__name__)


class UIParseError(ValueError):
    pass


class UIParser:
    def parse(self, text: str) -> dict[str, Any]:
        if not text or not text.strip():
            raise UIParseError("Vision model returned an empty UI detection response")

        cleaned = self._strip_markdown_fence(text.strip())
        candidates = [cleaned]

        extracted = self._extract_first_json_object(cleaned)
        if extracted and extracted != cleaned:
            candidates.append(extracted)

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = exc
                continue

            if not isinstance(parsed, dict):
                raise UIParseError("UI detection response must be a JSON object")
            return parsed

        LOGGER.error("Could not parse UI detection JSON: %s", text[:500])
        raise UIParseError(f"Invalid JSON from vision model: {last_error}") from last_error

    def _strip_markdown_fence(self, text: str) -> str:
        match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text

    def _extract_first_json_object(self, text: str) -> str | None:
        start = text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return None
