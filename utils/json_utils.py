from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union


JSON = Dict[str, Any]


def try_parse_json(text: str) -> Tuple[bool, Union[JSON, List[Any], str]]:
    try:
        return True, json.loads(text)
    except Exception:
        return False, text


def extract_first_json_array(text: str) -> Optional[List[Any]]:
    """
    Planner models sometimes wrap JSON in extra text.
    This extracts the first top-level JSON array by bracket matching.
    """
    start = text.find("[")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                chunk = text[start : i + 1]
                ok, data = try_parse_json(chunk)
                if ok and isinstance(data, list):
                    return data
                return None
    return None

