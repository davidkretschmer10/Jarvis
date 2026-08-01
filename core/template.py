from __future__ import annotations

import re
from typing import Any, Dict, List

from core.state import JarvisState


_STATE_VAR = re.compile(r"\{\{\s*(state\.[^}]+)\s*\}\}")


def _resolve_expr(expr: str, state: JarvisState) -> Any:
    """
    Supports a small subset:
      state.last_output
      state.files[0]
      state.data.key
      state.data.some.nested.key
    """
    if not expr.startswith("state."):
        return None
    path = expr[len("state.") :]

    cur: Any = state
    # Tokenize dot + [index]
    parts = path.split(".")
    for part in parts:
        m = re.fullmatch(r"([a-zA-Z_]\w*)(\[(\d+)\])?", part)
        if not m:
            return None
        key = m.group(1)
        idx = m.group(3)

        # JarvisState attributes vs dict keys
        if hasattr(cur, key):
            cur = getattr(cur, key)
        elif isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None

        if idx is not None:
            if isinstance(cur, list):
                i = int(idx)
                if i < 0 or i >= len(cur):
                    return None
                cur = cur[i]
            else:
                return None
    return cur


def render_templates(value: Any, state: JarvisState) -> Any:
    """
    Replace {{state.*}} variables inside strings (recursively for dict/list).
    If the entire string is exactly one template, we return the underlying type.
    """
    if isinstance(value, dict):
        return {k: render_templates(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [render_templates(v, state) for v in value]
    if not isinstance(value, str):
        return value

    matches = list(_STATE_VAR.finditer(value))
    if not matches:
        return value

    # Exact single template -> preserve type
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        resolved = _resolve_expr(matches[0].group(1), state)
        return resolved if resolved is not None else value

    # Otherwise, do string interpolation
    def repl(m: re.Match) -> str:
        resolved = _resolve_expr(m.group(1), state)
        return "" if resolved is None else str(resolved)

    return _STATE_VAR.sub(repl, value)

